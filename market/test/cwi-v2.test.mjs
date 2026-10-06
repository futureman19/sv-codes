import test from 'node:test';import assert from 'node:assert/strict';
import { createYoursAdapter } from '../src/cwi.mjs';import { makeV2 } from './synthetic-v2.mjs';
for(const mode of ['ok','reorder','fee','extra','missing-front','missing-beef','unknown','processed'])test('mock CWI V2 boundary '+mode,async()=>{
 const f=await makeV2();let calls=0;
 const wallet={waitForAuthentication:async()=>({authenticated:true}),createAction:async a=>{
 calls++;assert.deepEqual(a.inputBEEF,f.sourceBEEF);assert.deepEqual(a.options,{signAndProcess:false,noSend:true,randomizeOutputs:false,acceptDelayedBroadcast:false,returnTXIDOnly:false});
 assert.equal(a.inputs[0].outpoint,f.options.frontOutpoint.replace(':','.'));assert.equal(a.outputs[1].satoshis,1234);
 if(mode==='reorder')[f.purchase.inputs[0],f.purchase.inputs[1]]=[f.purchase.inputs[1],f.purchase.inputs[0]];
 if(mode==='fee')f.purchase.outputs[3].satoshis--;
 if(mode==='extra')f.purchase.outputs.push({...f.purchase.outputs[2]});
 if(mode==='processed')return {txid:f.purchase.id('hex')};
 return {signableTransaction:{reference:'MOCK-ONLY',tx:f.atomic()}};
 },signAction:()=>assert.fail('no signAction'),createSignature:()=>assert.fail('no signature'),broadcast:()=>assert.fail('no broadcast')};
 const request={mode:'offline-v2',terms:f.terms,proof:f.proof,...f.options,sourceBEEF:f.sourceBEEF,approve:async()=>true};
 if(mode==='missing-front')delete request.frontOutpoint;
 if(mode==='missing-beef')delete request.sourceBEEF;
 if(mode==='unknown')f.evidence.status=async outpoint=>({outpoint,confirmed:'unknown',mempool:'unspent',checkedAt:Date.now()});
 const run=()=>createYoursAdapter({CWI:wallet},f.evidence).prepareV2Purchase(request);
 if(mode==='ok'){const r=await run();assert.equal(r.paidTradingEnabled,false);assert.equal(r.status,'prepared-not-signed-not-sent');assert.equal(r.report.assetOffset,'5000');}
 else await assert.rejects(run,mode.startsWith('missing-')?/FRONT_FUNDING_CAPABILITY_BLOCKED/:mode==='unknown'?/UNSPENT_NOT_PROVEN/:/WALLET_CAPABILITY_BLOCKED/);
 if(['missing-front','missing-beef','unknown'].includes(mode))assert.equal(calls,0);
});
