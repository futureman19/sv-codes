import test from 'node:test';
import assert from 'node:assert/strict';
import { Transaction, P2PKH } from '@bsv/sdk';
import { OrdLock, OrdLockV2 } from '@1sat/templates';
import { makeFixture } from './synthetic.mjs';
import * as core from '../src/core.mjs';

test('core exports strict bounded verification API', () => {
  for (const name of ['parseOutpoint','parseTransaction','verifyLegacyListing','verifySpend','validatePurchase','createListing','MAX_SATOSHIS']) assert.ok(core[name], name);
});
test('current template prohibits v1 listing creation; never silently substitute V2', async () => {
  const f = await makeFixture();
  assert.throws(() => OrdLock.lock(f.terms.cancelAddress, f.terms.payoutAddress, 1234), /deprecated/);
  assert.throws(() => core.createListing(f.terms), /PAID_TRADING_DISABLED/);
  assert.notEqual(OrdLockV2.lock(f.terms.cancelAddress, f.terms.payoutAddress, 1234).toHex(), f.listing.outputs[0].lockingScript.toHex());
});
test('synthetic legacy listing, purchase and alternate cancel execute actual SDK interpreter, all inputs', async () => {
  const f = await makeFixture();
  for (const tx of [f.listing, f.purchase, f.cancel]) for (let i=0;i<tx.inputs.length;i++) assert.equal(core.verifySpend(tx,i), true);
  assert.equal(core.validatePurchase(f.purchase, f.listing, f.terms, f.buyerScript, {maxFee:1000, changeScript:f.buyerScript}), true);
});
test('strict raw parser binds txid and rejects appended data and noncanonical outpoints', async () => {
  const f = await makeFixture();
  assert.equal(core.parseTransaction(f.listing.toHex(), f.listing.id('hex')).id('hex'), f.listing.id('hex'));
  assert.throws(() => core.parseTransaction(f.listing.toHex()+'00', f.listing.id('hex')));
  assert.throws(() => core.parseTransaction(f.listing.toHex(), '00'.repeat(32)));
  for(const s of ['A'.repeat(64)+':0','00'.repeat(32)+':00','00'.repeat(32)+':4294967296','x', f.terms.listing.replace(':','.')]) assert.throws(() => core.parseOutpoint(s));
});
test('legacy proof binds origin/current/list, exact payout, price, cancel and canonical script', async () => {
  const f=await makeFixture();
  assert.equal((await core.verifyLegacyListing(f.proof, f.terms, f.evidence)).scope, 'legacy-v1-transaction-and-status');
  for (const patch of [{price:1235},{price:1233},{price:0},{price:1.2},{price:Number.MAX_SAFE_INTEGER},{price:NaN},{payoutAddress:f.terms.cancelAddress},{cancelAddress:f.terms.payoutAddress},{current:'00'.repeat(32)+':0'},{origin:'00'.repeat(32)+':0'},{listing:'00'.repeat(32)+':0'}]) {
    await assert.rejects(core.verifyLegacyListing(f.proof,{...f.terms,...patch},f.evidence));
  }
  const tampered=Transaction.fromHex(f.listing.toHex());
  tampered.outputs[0].lockingScript.writeOpCode(97);
  await assert.rejects(core.verifyLegacyListing({...f.proof,listingHex:tampered.toHex()},{...f.terms,listing:tampered.id('hex')+':0'},f.evidence), /COVENANT/);
});
test('proof fails closed without independently verified origin or fresh confirmed+mempool unspent status', async () => {
  const f=await makeFixture();
  for(const state of ['spent','unknown','not-found','timeout']) {
    await assert.rejects(core.verifyLegacyListing(f.proof,f.terms,{...f.evidence,status:async()=>({...await f.evidence.status(),mempool:state})}),new RegExp('MEMPOOL_'+state.toUpperCase().replaceAll('-','_')));
  }
  await assert.rejects(core.verifyLegacyListing(f.proof,f.terms,{...f.evidence,verifyOrigin:async()=>false}));
  await assert.rejects(core.verifyLegacyListing(f.proof,f.terms,{...f.evidence,status:async()=>({...await f.evidence.status(),checkedAt:0})}));
  await assert.rejects(core.verifyLegacyListing(f.proof,f.terms,{...f.evidence,status:async()=>({...await f.evidence.status(),outpoint:f.terms.origin})}));
});
for (const mutation of ['price','payout','reorder','wrong-item','recipient','one-sat']) test('adversarial purchase rejected: '+mutation, async () => {
  const f=await makeFixture(); const tx=f.purchase;
  if(mutation==='price') tx.outputs[1].satoshis++;
  if(mutation==='payout') tx.outputs[1].lockingScript=new P2PKH().lock(f.terms.cancelAddress);
  if(mutation==='reorder') [tx.outputs[0],tx.outputs[1]]=[tx.outputs[1],tx.outputs[0]];
  if(mutation==='wrong-item') tx.inputs[0].sourceTXID='00'.repeat(32);
  if(mutation==='recipient') tx.outputs[0].lockingScript=new P2PKH().lock(f.terms.cancelAddress);
  if(mutation==='one-sat') tx.outputs[0].satoshis=2;
  // Fresh covenant unlock: payout/ordering failures aren't merely stale signatures.
  tx.inputs[0].unlockingScript=await OrdLock.purchaseListing().sign(tx,0);
  assert.throws(()=>core.validatePurchase(tx,f.listing,f.terms,f.buyerScript,{maxFee:1000,changeScript:f.buyerScript}));
  if(['price','payout','reorder'].includes(mutation)) assert.throws(()=>core.verifySpend(tx,0));
});
test('integer boundary accepts maximum exact satoshis and rejects overflow before encoding',()=>{
  assert.equal(core.integer(core.MAX_SATOSHIS),core.MAX_SATOSHIS);
  for(const n of [core.MAX_SATOSHIS+1,Number.MAX_SAFE_INTEGER+1,Infinity,-1,0.5,'1']) assert.throws(()=>core.integer(n),/BOUNDARY/);
});
test('missing provider, denied transaction evidence and lineage overflow fail closed',async()=>{
  const f=await makeFixture();
  await assert.rejects(core.verifyLegacyListing(f.proof,f.terms,undefined),/PROVIDER/);
  await assert.rejects(core.verifyLegacyListing(f.proof,f.terms,{...f.evidence,verifyTransaction:async()=>false}),/CHAIN_TRANSACTION/);
  await assert.rejects(core.verifyLegacyListing({...f.proof,hops:Array(33).fill(f.root.toHex())},f.terms,f.evidence),/BOUNDS/);
  await assert.rejects(core.verifyLegacyListing({...f.proof,hops:[f.listing.toHex()]},f.terms,f.evidence));
});
test('duplicate funding and excess fee are rejected',async()=>{
  const f=await makeFixture(); const tx=f.purchase;
  tx.inputs.push(tx.inputs[1]);
  assert.throws(()=>core.validatePurchase(tx,f.listing,f.terms,f.buyerScript,{maxFee:1000,changeScript:f.buyerScript}),/DUPLICATE/);
  tx.inputs.pop(); tx.outputs[2].satoshis=1;
  assert.throws(()=>core.validatePurchase(tx,f.listing,f.terms,f.buyerScript,{maxFee:1000,changeScript:f.buyerScript}),/FEE/);
});
test('wrong cancel signer fails actual interpreter', async()=>{
  const f=await makeFixture({wrongCancel:true}); assert.throws(()=>core.verifySpend(f.cancel,0));
});
