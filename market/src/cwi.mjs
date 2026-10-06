import { Beef, Transaction, Script } from '@bsv/sdk';
import { OrdLock, OrdLockV2 } from '@1sat/templates';
import { verifyV2Listing, validateV2Purchase, purchasePlan, source } from './v2.mjs';
import { integer, hex, fail, verifyLegacyListing, parseTransaction, parseOutpoint, addressScript, requireUnspent, validatePurchase, verifySpend } from './core.mjs';

function bytes(input) {
  if(!(Array.isArray(input)||input instanceof Uint8Array)||input.length<4||input.length>2000000) fail('BEEF_BYTES_REQUIRED');
  const b=Array.from(input); if(b.some(v=>!Number.isInteger(v)||v<0||v>255)) fail('BEEF_BYTE_RANGE'); return b;
}
/** Only current window.CWI methods, only deferred preparation. No signing/broadcast API. */
export function createYoursAdapter(windowObject, evidence) {
  const wallet=windowObject?.CWI;
  if(!wallet||typeof wallet.waitForAuthentication!=='function'||typeof wallet.createAction!=='function') fail('CWI_UNAVAILABLE');
  const submitted=new Set();
  return Object.freeze({
    async prepareV2Purchase(request) {
      if(request.mode!=='offline-v2') fail('PAID_TRADING_DISABLED');
      const approve=request.approve;
      if(typeof approve!=='function') fail('APPROVAL_CALLBACK_REQUIRED');
      const r=structuredClone({...request,approve:undefined});
      if(!r.frontOutpoint||!r.sourceBEEF) fail('FRONT_FUNDING_CAPABILITY_BLOCKED: already-funded explicit sourceBEEF required; no automatic preparation');
      parseOutpoint(r.terms.listing);
      if(submitted.has(r.terms.listing)) fail('DOUBLE_SUBMIT');
      submitted.add(r.terms.listing);
      const sourceBEEF=bytes(r.sourceBEEF),beef=Beef.fromBinary(sourceBEEF);
      if(JSON.stringify(beef.toBinary())!==JSON.stringify(sourceBEEF))fail('NONCANONICAL_BEEF');
      const review=await verifyV2Listing(r.proof,r.terms,evidence);
      const listing=parseTransaction(review.listingHex);
      const points=[r.frontOutpoint,r.terms.listing,r.feeOutpoint];
      const draft=new Transaction();
      for(const p of points){const {txid,vout}=parseOutpoint(p),t=beef.findTxid(txid)?.tx;if(!t)fail('SOURCE_BEEF_MISMATCH');draft.addInput({sourceTransaction:t,sourceOutputIndex:vout,sequence:0xffffffff});}
      const script=listing.outputs[parseOutpoint(r.terms.listing).vout].lockingScript;
      const plan=purchasePlan(listing,r.terms,r,source(draft.inputs[0]).satoshis,source(draft.inputs[2]).satoshis);
      plan.outputs.forEach(o=>draft.addOutput(o));
      // Empty unlocks serialize canonically for validation; no wallet signatures requested.
      const { UnlockingScript }=await import('@bsv/sdk');draft.inputs.forEach(i=>i.unlockingScript=new UnlockingScript());
      await validateV2Purchase(draft,listing,r.terms,r,evidence);
      if(await approve(Object.freeze({terms:review.terms,...Object.fromEntries(['buyerScript','changeScript','frontOutpoint','feeOutpoint','expectedFee','maxFee'].map(k=>[k,r[k]])),scope:'offline V2 preparation only; no signing or broadcast'}))!==true)fail('USER_APPROVAL_REQUIRED');
      if((await wallet.waitForAuthentication({}))?.authenticated!==true)fail('WALLET_AUTHENTICATION_REFUSED');
      const reserve=OrdLockV2.estimatePurchaseUnlockLength(script);
      const response=await wallet.createAction({description:'Review offline V2 collectible purchase',version:1,lockTime:0,inputBEEF:[...sourceBEEF],inputs:points.map((p,i)=>({outpoint:p.replace(':','.'),inputDescription:i===1?'V2 collectible':'Explicit already-funded ordinary input',unlockingScriptLength:i===1?reserve:108,sequenceNumber:0xffffffff})),outputs:plan.outputs.map((o,i)=>({lockingScript:o.lockingScript.toHex(),satoshis:o.satoshis,outputDescription:['Funding cushion','Exact seller payout','Buyer collectible','Exact fee funding change'][i]})),options:{signAndProcess:false,noSend:true,randomizeOutputs:false,acceptDelayedBroadcast:false,returnTXIDOnly:false}});
      let tx,report;
      try{
        if(response?.txid||response?.tx||!response?.signableTransaction?.reference||!response?.signableTransaction?.tx)fail('deferred AtomicBEEF required');
        tx=Transaction.fromAtomicBEEF(bytes(response.signableTransaction.tx));
        report=await validateV2Purchase(tx,listing,r.terms,r,evidence);
        // Verify every explicit source against supplied BEEF, not just its output value.
        tx.inputs.forEach((input,i)=>{if(input.sourceTransaction.toHex()!==draft.inputs[i].sourceTransaction.toHex())fail('SOURCE_BEEF_MISMATCH');});
        tx.inputs[1].unlockingScript=await OrdLockV2.purchaseListing(undefined,undefined,{deliveries:[{vout:2,lockingScript:Script.fromHex(r.buyerScript)}]}).sign(tx,1);
        if(tx.inputs[1].unlockingScript.toBinary().length>reserve)fail('UNLOCK_RESERVATION_EXCEEDED');
        verifySpend(tx,1);
      }catch(e){fail('WALLET_CAPABILITY_BLOCKED: exact V2 layout required; '+e.message);}
      await requireUnspent(evidence.status,r.terms.listing);
      return Object.freeze({status:'prepared-not-signed-not-sent',supportedV2:true,paidTradingEnabled:false,reference:response.signableTransaction.reference,transactionHex:tx.toHex(),sourceBEEF:Object.freeze([...sourceBEEF]),report:Object.freeze(report),scope:'mock-tested CWI boundary; funding signatures and real wallet/chain availability unproven'});
    },
    async prepareLegacyPurchase(request) {
      if(request.mode!=='offline-legacy-review') fail('PAID_TRADING_DISABLED');
      const approve=request.approve;
      if(typeof approve!=='function') fail('APPROVAL_CALLBACK_REQUIRED');
      const r=structuredClone({...request,approve:undefined});
      integer(r.maxFee,0,100000);
      for(const script of [r.buyerScript,r.changeScript]) {
        hex(script,25);
        if(!/^76a914[0-9a-f]{40}88ac$/.test(script)) fail('RECIPIENT_SCRIPT_UNSUPPORTED');
      }
      parseOutpoint(r.terms.listing);
      if(submitted.has(r.terms.listing)) fail('DOUBLE_SUBMIT');
      // Failures retain the guard: ambiguous wallet state requires deliberate reconciliation.
      submitted.add(r.terms.listing);
      const sourceBEEF=bytes(r.sourceBEEF);
      const beef=Beef.fromBinary(sourceBEEF);
      if(JSON.stringify(beef.toBinary())!==JSON.stringify(sourceBEEF)) fail('NONCANONICAL_BEEF');
      const review=await verifyLegacyListing(r.proof,r.terms,evidence);
      const listing=parseTransaction(review.listingHex,parseOutpoint(r.terms.listing).txid);
      if(beef.findTxid(listing.id('hex'))?.tx?.toHex()!==review.listingHex) fail('SOURCE_BEEF_MISMATCH');
      const approved=await approve(Object.freeze({terms:review.terms,buyerScript:r.buyerScript,changeScript:r.changeScript,maxFee:r.maxFee,scope:'offline legacy preparation only; no signatures or broadcast'}));
      if(approved!==true) fail('USER_APPROVAL_REQUIRED');
      await requireUnspent(evidence.status,r.terms.listing);
      if((await wallet.waitForAuthentication({}))?.authenticated!==true) fail('WALLET_AUTHENTICATION_REFUSED');
      const args={
        description:'Review legacy collectible purchase',version:1,lockTime:0,
        inputBEEF:[...sourceBEEF],
        inputs:[{outpoint:r.terms.listing.replace(':','.'),inputDescription:'Legacy sale collectible',unlockingScriptLength:5000,sequenceNumber:0xffffffff}],
        outputs:[{lockingScript:r.buyerScript,satoshis:1,outputDescription:'Buyer collectible receive'},
          {lockingScript:addressScript(r.terms.payoutAddress).toHex(),satoshis:r.terms.price,outputDescription:'Exact seller payment'}],
        options:{signAndProcess:false,noSend:true,randomizeOutputs:false,acceptDelayedBroadcast:false,returnTXIDOnly:false}
      };
      const response=await wallet.createAction(args);
      if(response?.txid||response?.tx||!response?.signableTransaction?.reference||!response?.signableTransaction?.tx) fail('WALLET_CAPABILITY_BLOCKED: deferred AtomicBEEF required');
      const tx=Transaction.fromAtomicBEEF(bytes(response.signableTransaction.tx));
      // Re-parse raw bytes too, enforcing bounded integer and duplicate-input checks.
      parseTransaction(tx.toHex());
      try { validatePurchase(tx,listing,r.terms,r.buyerScript,{maxFee:r.maxFee,changeScript:r.changeScript}); }
      catch(e) { fail('WALLET_CAPABILITY_BLOCKED: exact ordered layout required; '+e.message); }
      // Never treat an ordinary-looking P2PKH as sufficient asset classification.
      if(typeof evidence.verifyFunding!=='function') fail('FUNDING_CLASSIFICATION_REQUIRED');
      for(const input of tx.inputs.slice(1)) {
        const point=`${input.sourceTXID??input.sourceTransaction.id('hex')}:${input.sourceOutputIndex}`;
        if(await evidence.verifyFunding({outpoint:point,raw:input.sourceTransaction.toHex()})!==true) fail('FUNDING_CLASSIFICATION_REQUIRED');
      }
      // Purchase covenant needs no secret signature. Verify against the exact returned outputs.
      tx.inputs[0].unlockingScript=await OrdLock.purchaseListing().sign(tx,0);
      if(tx.inputs[0].unlockingScript.toBinary().length>5000) fail('UNLOCK_RESERVATION_EXCEEDED');
      verifySpend(tx,0);
      await requireUnspent(evidence.status,r.terms.listing);
      return Object.freeze({status:'prepared-not-signed-not-sent',paidTradingEnabled:false,reference:response.signableTransaction.reference,transactionHex:tx.toHex(),sourceBEEF:Object.freeze([...sourceBEEF]),scope:'covenant verified; funding signatures, SPV and wallet delivery not proven'});
    }
  });
}
