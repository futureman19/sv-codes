// TEST ONLY. Seeded disposable keys are never returned/exported. Not chain receipts.
import { PrivateKey, Hash, Utils, Transaction, P2PKH, Script, UnlockingScript, Beef } from '@bsv/sdk';
import { OrdLock } from '@1sat/templates';
import { ORD_LOCK_PREFIX, ORD_LOCK_SUFFIX } from '@1sat/types';
const key = label => PrivateKey.fromHex(Utils.toHex(Hash.sha256(Utils.toArray('SV Codes OFFLINE disposable vector '+label,'utf8'))));
export async function makeFixture({wrongCancel=false}={}) {
  const owner=key('owner'), cancelKey=key('cancel'), pay=key('payout'), buyer=key('buyer'), fund=key('fund');
  const p2pkh=k=>new P2PKH().lock(k.toAddress());
  const root=new Transaction();
  root.addInput({sourceTXID:'00'.repeat(32),sourceOutputIndex:0xffffffff,unlockingScript:new UnlockingScript().writeBin([1,2,3]),sequence:0xffffffff});
  root.addOutput({satoshis:1,lockingScript:p2pkh(owner)});
  root.addOutput({satoshis:10000,lockingScript:p2pkh(fund)});
  root.addOutput({satoshis:10000,lockingScript:p2pkh(fund)});
  const terms={origin:root.id('hex')+':0',current:root.id('hex')+':0',price:1234,cancelAddress:cancelKey.toAddress(),payoutAddress:pay.toAddress()};
  // Reconstruction ONLY in test fixture. Current production OrdLock.lock is disabled.
  const params=new Script().writeBin(Utils.fromBase58Check(terms.cancelAddress).data).writeBin(OrdLock.buildOutput(terms.price,p2pkh(pay).toBinary()));
  const legacyScript=Script.fromHex(ORD_LOCK_PREFIX+params.toHex()+ORD_LOCK_SUFFIX);
  const listing=new Transaction();
  listing.addInput({sourceTransaction:root,sourceOutputIndex:0,unlockingScriptTemplate:new P2PKH().unlock(owner,'all',false),sequence:0xffffffff});
  listing.addInput({sourceTransaction:root,sourceOutputIndex:1,unlockingScriptTemplate:new P2PKH().unlock(fund,'all',false),sequence:0xffffffff});
  listing.addOutput({satoshis:1,lockingScript:legacyScript});
  listing.addOutput({satoshis:9800,lockingScript:p2pkh(fund)});
  await listing.sign(); terms.listing=listing.id('hex')+':0';
  async function close(cancel) {
    const tx=new Transaction();
    tx.addInput({sourceTransaction:listing,sourceOutputIndex:0,sequence:0xffffffff,unlockingScriptTemplate:cancel?OrdLock.cancelListing(wrongCancel?buyer:cancelKey,'all',false):OrdLock.purchaseListing()});
    tx.addInput({sourceTransaction:root,sourceOutputIndex:2,sequence:0xffffffff,unlockingScriptTemplate:new P2PKH().unlock(fund,'all',false)});
    tx.addOutput({satoshis:1,lockingScript:p2pkh(cancel?owner:buyer)});
    if(!cancel) tx.addOutput({satoshis:terms.price,lockingScript:p2pkh(pay)});
    tx.addOutput({satoshis:10000-(cancel?0:terms.price)-200,lockingScript:p2pkh(buyer)});
    await tx.sign(); return tx;
  }
  const purchase=await close(false), cancel=await close(true);
  const proof={originHex:root.toHex(),hops:[],listingHex:listing.toHex()};
  const evidence={verifyOrigin:async()=>true,verifyTransaction:async()=>true,verifyFunding:async()=>true,status:async()=>({outpoint:terms.listing,confirmed:'unspent',mempool:'unspent',checkedAt:Date.now()})};
  const beef=new Beef(); beef.mergeRawTx(root.toBinary()); beef.mergeRawTx(listing.toBinary());
  const draft=Transaction.fromHex(purchase.toHex());
  for(const input of draft.inputs) input.unlockingScript=new UnlockingScript();
  const resultBeef=new Beef(); resultBeef.mergeRawTx(root.toBinary()); resultBeef.mergeRawTx(listing.toBinary()); resultBeef.mergeRawTx(draft.toBinary());
  return {terms,root,listing,purchase,cancel,proof,evidence,buyerScript:p2pkh(buyer).toHex(),sourceBEEF:beef.toBinary(),signableBEEF:resultBeef.toBinaryAtomic(draft.id('hex'))};
}
