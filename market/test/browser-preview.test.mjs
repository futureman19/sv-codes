import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {parseTransaction,loadTransactions,traceAsset} from '../../docs/market-preview/verify.mjs';
const f=JSON.parse(fs.readFileSync(new URL('../fixtures/offline-legacy-sale.json',import.meta.url)));
test('independently hash actual public raw vectors and trace legacy satoshi',async()=>{const m=await loadTransactions(f);const r=traceAsset(m.get(f.purchase.txid),f.terms.listing,m,f.buyerScript);assert.equal(r.inputIndex,0);assert.equal(r.outputIndex,0);assert.equal(r.fee,200n);});
test('hash mismatch fails',async()=>{await assert.rejects(()=>loadTransactions({...f,purchase:{...f.purchase,txid:'0'.repeat(64)}}),/hash mismatch/);});
test('trailing bytes fail',()=>assert.throws(()=>parseTransaction(f.purchase.rawHex+'00'),/Trailing/));
test('missing funding source fails',async()=>{const m=await loadTransactions(f);const tx=m.get(f.purchase.txid);m.delete(f.origin.txid);assert.throws(()=>traceAsset(tx,f.terms.listing,m,f.buyerScript),/Missing source/);});
test('wrong buyer fails',async()=>{const m=await loadTransactions(f);assert.throws(()=>traceAsset(m.get(f.purchase.txid),f.terms.listing,m,'00'),/expected/);});
test('payout first cannot hide lost satoshi',async()=>{const m=await loadTransactions(f);const tx=m.get(f.purchase.txid);[tx.outputs[0],tx.outputs[1]]=[tx.outputs[1],tx.outputs[0]];assert.throws(()=>traceAsset(tx,f.terms.listing,m,f.buyerScript),/expected/);});

test('current V2 browser proof matches actual raw satoshi offsets',async()=>{const v=JSON.parse(fs.readFileSync(new URL('../fixtures/offline-v2-sale.json',import.meta.url)));const m=await loadTransactions(v),r=traceAsset(m.get(v.purchase.txid),v.terms.listing,m,v.buyerScript);assert.equal(r.inputIndex,1);assert.equal(r.outputIndex,2);assert.equal(r.offset,5000n);assert.equal(r.fee,200n);});
