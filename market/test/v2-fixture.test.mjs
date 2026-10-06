import test from 'node:test';import assert from 'node:assert/strict';import {readFile} from 'node:fs/promises';
import {parseTransaction,verifySpend} from '../src/core.mjs';import {assertV2,satFlow,validateV2Purchase} from '../src/v2.mjs';
test('independent published V2 fixture replay, no fixture generator or private keys',async()=>{
 const f=JSON.parse(await readFile(new URL('../fixtures/offline-v2-sale.json',import.meta.url),'utf8'));
 assert.equal(f.paidTradingEnabled,false);assert.equal(f.liveChainAvailable,false);assert.equal(f.realWalletTested,false);
 const records=[f.origin,...f.sources,f.listing,f.purchase,f.cancel],txs=new Map(records.map(r=>[r.txid,parseTransaction(r.rawHex,r.txid)]));
 for(const r of [f.listing,f.purchase,f.cancel]){const t=txs.get(r.txid);for(const [i,input] of t.inputs.entries()){input.sourceTransaction=txs.get(input.sourceTXID);assert.equal(verifySpend(t,i),true);}assert.equal(r.interpreterInputs.length,t.inputs.length);}
 const listing=txs.get(f.listing.txid),purchase=txs.get(f.purchase.txid),cancel=txs.get(f.cancel.txid);assertV2(listing,f.terms);
 assert.deepEqual(satFlow(listing,1,2),f.satFlow.listing);assert.deepEqual(satFlow(cancel,0,0),f.satFlow.cancel);
 const evidence={verifyOrigin:async()=>true,verifyTransaction:async()=>true,verifyFunding:async({outpoint})=>[f.options.frontOutpoint,f.options.feeOutpoint].includes(outpoint),status:async outpoint=>({outpoint,confirmed:'unspent',mempool:'unspent',checkedAt:Date.now()})};
 assert.deepEqual(await validateV2Purchase(purchase,listing,f.terms,f.options,evidence),f.satFlow.purchase);
 assert.equal(purchase.outputs[2].lockingScript.toHex(),f.buyerScript);
});
