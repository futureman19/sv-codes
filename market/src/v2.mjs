import { Script } from '@bsv/sdk';
import { OrdLockV2 } from '@1sat/templates';
import { integer, hex, fail, parseOutpoint, parseTransaction, createListing, requireUnspent, verifySpend, MAX_SATOSHIS } from './core.mjs';
export const point=i=>`${i.sourceTXID??i.sourceTransaction?.id('hex')}:${i.sourceOutputIndex}`;
export function source(i){
 const p=parseOutpoint(point(i)),t=i.sourceTransaction;
 if(!t||t.id('hex')!==p.txid||!t.outputs[p.vout])fail('SOURCE_MISMATCH');
 integer(t.outputs[p.vout].satoshis);return t.outputs[p.vout];
}
export function satFlow(tx,inputIndex,outputIndex){
 parseTransaction(tx.toHex());integer(inputIndex,0,tx.inputs.length-1);integer(outputIndex,0,tx.outputs.length-1);
 const values=tx.inputs.map(i=>BigInt(source(i).satoshis));
 const outputs=tx.outputs.map(o=>BigInt(integer(o.satoshis)));
 const ins=values.reduce((a,b)=>a+b,0n),outs=outputs.reduce((a,b)=>a+b,0n);
 if(ins>BigInt(MAX_SATOSHIS)||outs>ins)fail('VALUE_BOUNDARY');
 const offset=values.slice(0,inputIndex).reduce((a,b)=>a+b,0n),receive=outputs.slice(0,outputIndex).reduce((a,b)=>a+b,0n);
 if(values[inputIndex]!==1n||outputs[outputIndex]!==1n||offset!==receive)fail('ORDINAL_SAT_FLOW');
 return {inputTotal:String(ins),outputTotal:String(outs),fee:String(ins-outs),assetInputIndex:inputIndex,receiveOutputIndex:outputIndex,assetOffset:String(offset),receiveOffset:String(receive)};
}
export function assertV2(listing,terms){
 for(const k of ['origin','current','listing'])parseOutpoint(terms[k]);
 const p=parseOutpoint(terms.listing),o=listing.outputs[p.vout];
 const expected=createListing({mode:'offline-v2',terms}).lockingScript.toHex();
 if(listing.id('hex')!==p.txid||o?.satoshis!==1||o.lockingScript.toHex()!==expected)fail('V2_COVENANT_MISMATCH');
 return o;
}
function provider(e){for(const k of ['verifyOrigin','verifyTransaction','verifyFunding','status'])if(typeof e?.[k]!=='function')fail('TRUSTED_EVIDENCE_PROVIDER_REQUIRED');}
export async function funding(tx,assetIndex,e,{status=true}={}){
 provider(e);
 for(const [i,input] of tx.inputs.entries()){
  const o=source(input);if(i===assetIndex)continue;
  if(o.satoshis<=1||!/^76a914[0-9a-f]{40}88ac$/.test(o.lockingScript.toHex())||await e.verifyFunding({outpoint:point(input),raw:input.sourceTransaction.toHex()})!==true)fail('FUNDING_CLASSIFICATION_REQUIRED');
  if(status)await requireUnspent(e.status,point(input));
 }
}
export async function verifyV2Listing(proofInput,termsInput,e){
 const proof=structuredClone(proofInput),terms=structuredClone(termsInput);provider(e);
 for(const k of ['origin','current','listing'])parseOutpoint(terms[k]);
 if(!Array.isArray(proof.hops)||proof.hops.length>32||!Array.isArray(proof.sourceHexes)||proof.sourceHexes.length>100)fail('LINEAGE_BOUNDS');
 const origin=parseTransaction(proof.originHex,parseOutpoint(terms.origin).txid);
 if(origin.outputs[parseOutpoint(terms.origin).vout]?.satoshis!==1)fail('ORIGIN_VALUE');
 const sources=new Map(proof.sourceHexes.map(raw=>{const t=parseTransaction(raw);return [t.id('hex'),t];}));sources.set(origin.id('hex'),origin);
 if(await e.verifyOrigin({origin:terms.origin,raw:proof.originHex})!==true)fail('ORIGIN_CERTIFICATE_ANCHOR_UNPROVEN');
 let prior=terms.origin;
 const steps=[...proof.hops,{raw:proof.listingHex,outpoint:terms.listing}];
 for(const [j,step] of steps.entries()){
  if(j===steps.length-1&&prior!==terms.current)fail('CURRENT_MISMATCH');
  const p=parseOutpoint(step.outpoint),tx=parseTransaction(step.raw,p.txid);
  for(const input of tx.inputs){input.sourceTransaction=sources.get(input.sourceTXID);source(input);}
  const index=tx.inputs.findIndex(i=>point(i)===prior);if(index<0)fail('LINEAGE_MISMATCH');
  satFlow(tx,index,p.vout);
  if(j===steps.length-1)assertV2(tx,terms);
  else if(!/^76a914[0-9a-f]{40}88ac$/.test(tx.outputs[p.vout].lockingScript.toHex()))fail('UNSUPPORTED_LINEAGE_SCRIPT');
  await funding(tx,index,e,{status:false});
  tx.inputs.forEach((_,i)=>verifySpend(tx,i));
  sources.set(p.txid,tx);prior=step.outpoint;
 }
 for(const tx of sources.values())if(await e.verifyTransaction({txid:tx.id('hex'),raw:tx.toHex()})!==true)fail('CHAIN_TRANSACTION_UNPROVEN');
 await requireUnspent(e.status,terms.listing);
 return Object.freeze({supportedV2:true,paidTradingEnabled:false,terms:Object.freeze(terms),listingHex:proof.listingHex,scope:'offline-v2; external evidence is a trust boundary, not built-in SPV'});
}
export function purchasePlan(listing,terms,options,frontSatoshis,feeSatoshis){
 assertV2(listing,terms);
 for(const s of [options.buyerScript,options.changeScript]){hex(s,25);if(!/^76a914[0-9a-f]{40}88ac$/.test(s))fail('RECIPIENT_SCRIPT_UNSUPPORTED');}
 integer(options.expectedFee,0,100000);integer(options.maxFee,0,100000);
 integer(frontSatoshis,terms.price);integer(feeSatoshis,1);
 if(options.expectedFee>options.maxFee||feeSatoshis<=options.expectedFee)fail('FEE_BOUNDARY');
 const plan=OrdLockV2.planPurchase({frontSatoshis:[frontSatoshis],listings:[listing.outputs[parseOutpoint(terms.listing).vout].lockingScript],receives:[{satoshis:1,lockingScript:Script.fromHex(options.buyerScript)}],cushionScript:Script.fromHex(options.changeScript)});
 return {...plan,outputs:[...plan.outputs,{satoshis:feeSatoshis-options.expectedFee,lockingScript:Script.fromHex(options.changeScript)}]};
}
export async function validateV2Purchase(tx,listing,terms,options,e){
 provider(e);assertV2(listing,terms);parseTransaction(tx.toHex());
 if(!options.frontOutpoint)fail('FRONT_FUNDING_CAPABILITY_BLOCKED');
 const points=[options.frontOutpoint,terms.listing,options.feeOutpoint];points.forEach(parseOutpoint);
 if(tx.version!==1||tx.lockTime!==0||tx.inputs.length!==3||tx.outputs.length!==4||tx.inputs.some((i,n)=>point(i)!==points[n]||i.sequence!==0xffffffff))fail('V2_PURCHASE_LAYOUT');
 if(tx.inputs[1].sourceTransaction?.toHex()!==listing.toHex())fail('SOURCE_MISMATCH');
 const plan=purchasePlan(listing,terms,options,source(tx.inputs[0]).satoshis,source(tx.inputs[2]).satoshis);
 if(tx.outputs.some((o,i)=>o.satoshis!==plan.outputs[i].satoshis||o.lockingScript.toHex()!==plan.outputs[i].lockingScript.toHex()))fail('V2_OUTPUT_LAYOUT');
 const report=satFlow(tx,1,2);if(report.fee!==String(options.expectedFee))fail('FEE_DRIFT');
 await funding(tx,1,e);await requireUnspent(e.status,terms.listing);
 return {...report,cushion:String(plan.cushion)};
}
