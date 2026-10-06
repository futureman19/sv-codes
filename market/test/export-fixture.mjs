import { writeFile } from 'node:fs/promises';
import { makeFixture } from './synthetic.mjs';
import { verifySpend } from '../src/core.mjs';
const f=await makeFixture();
const describe=tx=>({txid:tx.id('hex'),rawHex:tx.toHex(),inputs:tx.inputs.map(i=>`${i.sourceTXID??i.sourceTransaction.id('hex')}:${i.sourceOutputIndex}`),outputs:tx.outputs.map(o=>({satoshis:o.satoshis,lockingScript:o.lockingScript.toHex()})),interpreterInputs:tx.inputs.map((_,i)=>verifySpend(tx,i))});
const fixture={schema:'sv-codes-offline-legacy-sale-vector-v1',warning:'SYNTHETIC OFFLINE TEST VECTORS — NOT CHAIN RECEIPTS. Never fund these addresses. Legacy v1 creation is deprecated; public paid trading disabled.',paidTradingEnabled:false,newListingsSupported:false,chainVerified:false,walletExtensionTested:false,cancelIsAlternativeToPurchase:true,dependencies:{templates:'0.0.43',sdk:'2.8.11',types:'0.0.52'},terms:f.terms,buyerScript:f.buyerScript,origin:{txid:f.root.id('hex'),rawHex:f.root.toHex(),proof:'synthetic unproven seed; origin input not interpreter-verified'},listing:describe(f.listing),purchase:describe(f.purchase),cancel:describe(f.cancel)};
// The synthetic origin is an unproven seed, not a valid spend. Do not run its inputs.
await writeFile(new URL('../fixtures/offline-legacy-sale.json',import.meta.url),JSON.stringify(fixture,null,2)+'\n');
console.log('Wrote public offline fixture; listing/purchase/cancel inputs passed SDK Spend. No chain or wallet claims.');
