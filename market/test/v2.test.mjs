import test from 'node:test';
import assert from 'node:assert/strict';
import * as core from '../src/core.mjs';
import { OrdLockV2 } from '@1sat/templates';
import { makeV2 } from './synthetic-v2.mjs';
import * as v2 from '../src/v2.mjs';
test('V2 nonzero vouts, all real spends and cumulative sat flow',async()=>{
 const f=await makeV2();
 await v2.verifyV2Listing(f.proof,f.terms,f.evidence);
 const report=await v2.validateV2Purchase(f.purchase,f.listing,f.terms,f.options,f.evidence);
 assert.deepEqual(report,{inputTotal:'5501',outputTotal:'5301',fee:'200',assetInputIndex:1,receiveOutputIndex:2,assetOffset:'5000',receiveOffset:'5000',cushion:'3766'});
 for(const tx of [f.listing,f.purchase,f.cancel]) tx.inputs.forEach((_,i)=>assert.equal(core.verifySpend(tx,i),true));
 assert.equal(v2.satFlow(f.cancel,0,0).assetOffset,'0');
});
for(const field of ['price','payoutAddress','cancelAddress']) test('V2 rejects mutated '+field,async()=>{
 const f=await makeV2();const t={...f.terms,[field]:field==='price'?1235:f.terms[field==='payoutAddress'?'cancelAddress':'payoutAddress']};
 await assert.rejects(()=>v2.verifyV2Listing(f.proof,t,f.evidence));
});
for(const mutation of ['front','receive','order','extra-input','extra-output','fee','funding','unknown']) test('V2 rejects '+mutation,async()=>{
 const f=await makeV2();
 if(mutation==='front')f.options.frontOutpoint=f.root.id('hex')+':4';
 if(mutation==='receive')f.purchase.outputs[2].lockingScript=f.purchase.outputs[1].lockingScript;
 if(mutation==='order')[f.purchase.outputs[1],f.purchase.outputs[2]]=[f.purchase.outputs[2],f.purchase.outputs[1]];
 if(mutation==='extra-input')f.purchase.inputs.push({...f.purchase.inputs[0],sourceOutputIndex:4});
 if(mutation==='extra-output')f.purchase.outputs.push({...f.purchase.outputs[2]});
 if(mutation==='fee')f.purchase.outputs[3].satoshis--;
 if(mutation==='funding')f.evidence.verifyFunding=async()=>false;
 if(mutation==='unknown')f.evidence.status=async outpoint=>({outpoint,confirmed:'unspent',mempool:'unknown',checkedAt:Date.now()});
 await assert.rejects(()=>v2.validateV2Purchase(f.purchase,f.listing,f.terms,f.options,f.evidence));
});
test('wrong cancel key fails actual interpreter',async()=>{const f=await makeV2({wrongCancel:true});assert.throws(()=>core.verifySpend(f.cancel,0));});
test('supported V2 listing creation is explicitly offline only',()=>{
 const terms={price:1234,cancelAddress:'1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH',payoutAddress:'1cMh228HTCiwS8ZsaakH8A8wze1JR5ZsP'};
 const r=core.createListing({mode:'offline-v2',terms});
 assert.equal(r.paidTradingEnabled,false);
 assert.equal(r.lockingScript.toHex(),OrdLockV2.lock(terms.cancelAddress,terms.payoutAddress,terms.price).toHex());
 assert.throws(()=>core.createListing({terms}),/PAID_TRADING_DISABLED/);
});
