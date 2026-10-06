import test from 'node:test';import assert from 'node:assert/strict';import { Script } from '@bsv/sdk';import {OrdLockV2} from '@1sat/templates';
import { makeV2 } from './synthetic-v2.mjs';import {verifySpend,parseOutpoint} from '../src/core.mjs';import {assertV2,satFlow,validateV2Purchase,verifyV2Listing} from '../src/v2.mjs';
test('exact full V2 script reconstruction rejects decoder-tolerated trailing bytes',async()=>{
 const f=await makeV2();f.listing.outputs[2].lockingScript=Script.fromHex(f.listing.outputs[2].lockingScript.toHex()+'61');
 assert.ok(OrdLockV2.decode(f.listing.outputs[2].lockingScript));
 assert.throws(()=>assertV2(f.listing,{...f.terms,listing:f.listing.id('hex')+':2'}),/V2_COVENANT_MISMATCH/);
});
test('same-index payout enforced by real interpreter, not only app/template guard',async()=>{
 const f=await makeV2();f.purchase.outputs[1].satoshis++;
 assert.throws(()=>verifySpend(f.purchase,1));
 await assert.rejects(()=>OrdLockV2.purchaseListing().sign(f.purchase,1));
});
test('V2 covenant alone does NOT bind buyer: app guard remains necessary',async()=>{
 const f=await makeV2();f.purchase.outputs[2].lockingScript=f.purchase.outputs[1].lockingScript;
 assert.equal(verifySpend(f.purchase,1),true);
 await assert.rejects(()=>validateV2Purchase(f.purchase,f.listing,f.terms,f.options,f.evidence),/V2_OUTPUT_LAYOUT/);
 assert.throws(()=>verifySpend(f.purchase,0)); // ordinary ALL signer seals buyer too
});
for(const variant of ['payout','fee','front-amount','extra-asset'])test('BigInt sat-flow rejects ordinal into '+variant,async()=>{
 const f=await makeV2();
 if(variant==='payout')f.purchase.outputs[0].satoshis++;
 if(variant==='fee'){f.purchase.outputs=f.purchase.outputs.slice(0,2);assert.throws(()=>satFlow(f.purchase,1,1),/ORDINAL_SAT_FLOW/);return;}
 if(variant==='front-amount'){f.root.outputs[2].satoshis++;f.purchase.inputs[0].sourceTXID=f.root.id('hex');}
 if(variant==='extra-asset')f.purchase.inputs.splice(1,0,{...f.purchase.inputs[1],sourceTransaction:f.root,sourceTXID:f.root.id('hex'),sourceOutputIndex:1});
 assert.throws(()=>satFlow(f.purchase,variant==='extra-asset'?2:1,2));
});
test('nonzero current/listing vouts are exact; uint32 rejected instead of normalized',async()=>{
 const f=await makeV2();assert.equal(parseOutpoint('a'.repeat(64)+':4294967295').vout,4294967295);
 for(const v of ['4294967296','01','-1','1.0'])assert.throws(()=>parseOutpoint('a'.repeat(64)+':'+v));
 await assert.rejects(()=>verifyV2Listing(f.proof,{...f.terms,current:f.root.id('hex')+':0'},f.evidence),/CURRENT_MISMATCH/);
 await assert.rejects(()=>verifyV2Listing(f.proof,{...f.terms,origin:f.root.id('hex')+':0'},f.evidence),/ORIGIN_VALUE/);
});
test('missing classification, source proof, chain evidence all fail closed',async()=>{
 const f=await makeV2();await assert.rejects(()=>verifyV2Listing(f.proof,f.terms,{...f.evidence,verifyFunding:undefined}),/TRUSTED_EVIDENCE/);
 await assert.rejects(()=>verifyV2Listing(f.proof,f.terms,{...f.evidence,verifyTransaction:async()=>false}),/CHAIN_TRANSACTION_UNPROVEN/);
 await assert.rejects(()=>verifyV2Listing({...f.proof,originHex:f.proof.originHex+'00'},f.terms,f.evidence));
});
