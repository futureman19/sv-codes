// Synthetic disposable keys stay inside this function. NEVER fund these addresses.
import { PrivateKey, Hash, Utils, Transaction, P2PKH, UnlockingScript, Beef } from '@bsv/sdk';
import { OrdLockV2 } from '@1sat/templates';
import { createListing } from '../src/core.mjs';
export async function makeV2({wrongCancel=false}={}) {
 const key=s=>PrivateKey.fromHex(Utils.toHex(Hash.sha256(Utils.toArray('OFFLINE ONLY SV0004 V2 '+s,'utf8'))));
 const owner=key('owner'),cancelKey=key('cancel'),pay=key('pay'),buyer=key('buyer'),fund=key('fund');
 const lock=k=>new P2PKH().lock(k.toAddress());
 const root=new Transaction();root.addInput({sourceTXID:'00'.repeat(32),sourceOutputIndex:0xffffffff,unlockingScript:new UnlockingScript().writeBin([4,2]),sequence:0xffffffff});
 for(const [s,k] of [[2000,fund],[1,owner],[5000,fund],[500,fund],[3000,fund]]) root.addOutput({satoshis:s,lockingScript:lock(k)});
 const terms={origin:root.id('hex')+':1',current:root.id('hex')+':1',price:1234,cancelAddress:cancelKey.toAddress(),payoutAddress:pay.toAddress()};
 const listing=new Transaction();
 for(const [v,k] of [[0,fund],[1,owner]]) listing.addInput({sourceTransaction:root,sourceOutputIndex:v,sequence:0xffffffff,unlockingScriptTemplate:new P2PKH().unlock(k,'all',false)});
 listing.addOutput({satoshis:2000,lockingScript:lock(fund)});listing.addOutput({satoshis:0,lockingScript:lock(fund)});
 listing.addOutput({satoshis:1,lockingScript:createListing({mode:'offline-v2',terms}).lockingScript});
 await listing.sign();terms.listing=listing.id('hex')+':2';
 const buyerScript=lock(buyer).toHex(),changeScript=lock(fund).toHex();
 const plan=OrdLockV2.planPurchase({frontSatoshis:[5000],listings:[listing.outputs[2].lockingScript],receives:[{satoshis:1,lockingScript:lock(buyer)}],cushionScript:lock(fund)});
 const purchase=new Transaction();
 purchase.addInput({sourceTransaction:root,sourceOutputIndex:2,sequence:0xffffffff,unlockingScriptTemplate:new P2PKH().unlock(fund,'all',false)});
 purchase.addInput({sourceTransaction:listing,sourceOutputIndex:2,sequence:0xffffffff,unlockingScriptTemplate:OrdLockV2.purchaseListing(undefined,undefined,{deliveries:[{vout:2,lockingScript:lock(buyer)}]})});
 purchase.addInput({sourceTransaction:root,sourceOutputIndex:3,sequence:0xffffffff,unlockingScriptTemplate:new P2PKH().unlock(fund,'all',false)});
 plan.outputs.forEach(o=>purchase.addOutput(o));purchase.addOutput({satoshis:300,lockingScript:lock(fund)});await purchase.sign();
 const cancel=new Transaction();cancel.addInput({sourceTransaction:listing,sourceOutputIndex:2,sequence:0xffffffff,unlockingScriptTemplate:OrdLockV2.cancelListing(wrongCancel?buyer:cancelKey,'all',false)});
 cancel.addInput({sourceTransaction:root,sourceOutputIndex:3,sequence:0xffffffff,unlockingScriptTemplate:new P2PKH().unlock(fund,'all',false)});
 cancel.addOutput({satoshis:1,lockingScript:lock(owner)});cancel.addOutput({satoshis:300,lockingScript:lock(fund)});await cancel.sign();
 const proof={originHex:root.toHex(),hops:[],listingHex:listing.toHex(),sourceHexes:[root.toHex()]};
 const ordinary=new Set([0,2,3,4].map(v=>root.id('hex')+':'+v));
 const evidence={verifyOrigin:async()=>true,verifyTransaction:async()=>true,verifyFunding:async({outpoint})=>ordinary.has(outpoint),status:async outpoint=>({outpoint,confirmed:'unspent',mempool:'unspent',checkedAt:Date.now()})};
 const beef=new Beef();beef.mergeRawTx(root.toBinary());beef.mergeRawTx(listing.toBinary());
 const options={frontOutpoint:root.id('hex')+':2',feeOutpoint:root.id('hex')+':3',buyerScript,changeScript,expectedFee:200,maxFee:200};
 function atomic(tx=purchase){const b=new Beef();b.mergeRawTx(root.toBinary());b.mergeRawTx(listing.toBinary());const d=Transaction.fromHex(tx.toHex());d.inputs.forEach(i=>i.unlockingScript=new UnlockingScript());b.mergeRawTx(d.toBinary());return b.toBinaryAtomic(d.id('hex'));}
 return {root,terms,listing,purchase,cancel,proof,evidence,options,sourceBEEF:beef.toBinary(),atomic};
}
