import test from 'node:test';
import assert from 'node:assert/strict';
import { Transaction, Beef } from '@bsv/sdk';
import { makeFixture } from './synthetic.mjs';
import * as api from '../src/cwi.mjs';
const setup=async()=>{
  const f=await makeFixture(); const calls=[];
  const wallet={waitForAuthentication:async()=>{calls.push('auth');return {authenticated:true};},createAction:async args=>{calls.push(args);return {signableTransaction:{tx:f.signableBEEF,reference:'b2ZmbGluZQ=='}};}};
  const request={mode:'offline-legacy-review',proof:f.proof,terms:f.terms,sourceBEEF:f.sourceBEEF,buyerScript:f.buyerScript,changeScript:f.buyerScript,maxFee:1000,approve:async()=>true};
  return {f,calls,wallet,request};
};
test('CWI preparation API exists',()=>assert.equal(typeof api.createYoursAdapter,'function'));
test('actual createAction boundary preserves sourceBEEF and fixed order, forces no-send/deferred options',async()=>{
  const {f,calls,wallet,request}=await setup();
  const adapter=api.createYoursAdapter({CWI:wallet},f.evidence);
  const result=await adapter.prepareLegacyPurchase(request);
  assert.deepEqual(calls[1].inputBEEF,f.sourceBEEF);
  assert.equal(calls[1].inputs[0].outpoint,f.terms.listing.replace(':','.'));
  assert.equal(calls[1].outputs[0].satoshis,1); assert.equal(calls[1].outputs[1].satoshis,f.terms.price);
  assert.deepEqual(calls[1].options,{signAndProcess:false,noSend:true,randomizeOutputs:false,acceptDelayedBroadcast:false,returnTXIDOnly:false});
  assert.equal(result.status,'prepared-not-signed-not-sent');
  assert.equal(result.paidTradingEnabled,false);
  assert.equal(typeof adapter.signAction,'undefined');
  await assert.rejects(adapter.prepareLegacyPurchase(request),/DOUBLE_SUBMIT/);
});
test('missing CWI and production mode are capability blockers',async()=>{
  const {f,wallet,request,calls}=await setup();
  assert.throws(()=>api.createYoursAdapter({},f.evidence),/CWI_UNAVAILABLE/);
  await assert.rejects(api.createYoursAdapter({CWI:wallet},f.evidence).prepareLegacyPurchase({...request,mode:'production'}),/PAID_TRADING_DISABLED/);
  assert.equal(calls.length,0);
});
test('approval refusal and uncertain chain status never reach wallet',async()=>{
  const {f,wallet,request,calls}=await setup();
  await assert.rejects(api.createYoursAdapter({CWI:wallet},f.evidence).prepareLegacyPurchase({...request,approve:async()=>false}),/APPROVAL/);
  await assert.rejects(api.createYoursAdapter({CWI:wallet},{...f.evidence,status:async()=>({outpoint:f.terms.listing,confirmed:'unspent',mempool:'unknown',checkedAt:Date.now()})}).prepareLegacyPurchase(request));
  assert.equal(calls.length,0);
});
test('double submission is blocked while approval is pending',async()=>{
  const {f,wallet,request,calls}=await setup(); let release;
  const adapter=api.createYoursAdapter({CWI:wallet},f.evidence);
  const pending=adapter.prepareLegacyPurchase({...request,approve:()=>new Promise(r=>release=r)});
  await assert.rejects(adapter.prepareLegacyPurchase(request),/DOUBLE_SUBMIT/);
  while(!release) await new Promise(r=>setImmediate(r)); release(true); await pending;
  assert.equal(calls.filter(x=>typeof x==='object').length,1);
});
for(const mutate of ['outputs','inputs','payout','fee','wrong-beef','txid-only']) test('wallet response fails closed: '+mutate,async()=>{
  const {f,wallet,request}=await setup();
  wallet.createAction=async()=>{
    if(mutate==='txid-only') return {txid:f.purchase.id('hex')};
    const tx=Transaction.fromHex(f.purchase.toHex());
    if(mutate==='outputs') [tx.outputs[0],tx.outputs[1]]=[tx.outputs[1],tx.outputs[0]];
    if(mutate==='inputs') tx.inputs.reverse();
    if(mutate==='payout') tx.outputs[1].satoshis--;
    if(mutate==='fee') tx.outputs[2].satoshis=1;
    const b=new Beef(); b.mergeRawTx(f.root.toBinary()); b.mergeRawTx(f.listing.toBinary()); b.mergeRawTx(tx.toBinary());
    return {signableTransaction:{tx:mutate==='wrong-beef'?[1,2,3]:b.toBinaryAtomic(tx.id('hex')),reference:'b2ZmbGluZQ=='}};
  };
  await assert.rejects(api.createYoursAdapter({CWI:wallet},f.evidence).prepareLegacyPurchase(request));
});
test('freeze request before approval; reject changed source BEEF before wallet',async()=>{
  const {f,wallet,request,calls}=await setup();
  request.approve=async()=>{request.terms.price=1;request.sourceBEEF.fill(0);return true;};
  await api.createYoursAdapter({CWI:wallet},f.evidence).prepareLegacyPurchase(request);
  assert.equal(calls[1].outputs[1].satoshis,1234); assert.notDeepEqual(calls[1].inputBEEF,request.sourceBEEF);
  const s=await setup();
  await assert.rejects(api.createYoursAdapter({CWI:s.wallet},s.f.evidence).prepareLegacyPurchase({...s.request,sourceBEEF:[1,2,3]}));
  assert.equal(s.calls.length,0);
});
test('invalid recipient and fee bounds stop before any wallet call',async()=>{
  for(const patch of [{buyerScript:'006a'},{buyerScript:'XYZ'},{maxFee:-1},{maxFee:NaN},{changeScript:'006a'}]) {
    const s=await setup();
    await assert.rejects(api.createYoursAdapter({CWI:s.wallet},s.f.evidence).prepareLegacyPurchase({...s.request,...patch}));
    assert.equal(s.calls.length,0);
  }
});
test('unclassified funding is never accepted as ordinary spendable funds',async()=>{
  const s=await setup();
  await assert.rejects(api.createYoursAdapter({CWI:s.wallet},{...s.f.evidence,verifyFunding:async()=>false}).prepareLegacyPurchase(s.request),/CLASSIFICATION/);
});
test('spent-state race during wallet prompt is rejected without signatures or processing',async()=>{
  const {f,wallet,request}=await setup(); let spent=false;
  const original=wallet.createAction; wallet.createAction=async a=>{spent=true;return original(a);};
  const evidence={...f.evidence,status:async()=>({outpoint:f.terms.listing,confirmed:'unspent',mempool:spent?'spent':'unspent',checkedAt:Date.now()})};
  await assert.rejects(api.createYoursAdapter({CWI:wallet},evidence).prepareLegacyPurchase(request),/UNSPENT/);
});
