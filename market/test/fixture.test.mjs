import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { parseTransaction, verifySpend } from '../src/core.mjs';
test('public JSON is explicitly offline and raw listing/purchase/cancel independently replay',async()=>{
  const fixture=JSON.parse(await readFile(new URL('../fixtures/offline-legacy-sale.json',import.meta.url),'utf8'));
  assert.equal(fixture.chainVerified,false); assert.equal(fixture.paidTradingEnabled,false);
  assert.equal(fixture.newListingsSupported,false); assert.equal(fixture.walletExtensionTested,false);
  assert.equal(fixture.cancelIsAlternativeToPurchase,true);
  const transactions=new Map();
  for(const name of ['origin','listing','purchase','cancel']) {
    const v=fixture[name]; const tx=parseTransaction(v.rawHex,v.txid);
    for(const input of tx.inputs) input.sourceTransaction=transactions.get(input.sourceTXID);
    if(name!=='origin') for(let i=0;i<tx.inputs.length;i++) assert.equal(verifySpend(tx,i),true);
    transactions.set(v.txid,tx);
  }
  const rejectSecrets=value=>{
    if(!value||typeof value!=='object') return;
    for(const [k,v] of Object.entries(value)) {assert.ok(!/privatekey|wif|mnemonic|seedphrase/i.test(k));rejectSecrets(v);}
  };
  rejectSecrets(fixture);
});
