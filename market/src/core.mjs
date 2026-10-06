import { Transaction, P2PKH, Script, Spend, Utils } from '@bsv/sdk';
import { OrdLock, OrdLockV2 } from '@1sat/templates';
import { ORD_LOCK_PREFIX, ORD_LOCK_SUFFIX } from '@1sat/types';

export const MAX_SATOSHIS = 2100000000000000;
export const PAID_TRADING_ENABLED = false;
export function fail(code) { throw new Error(code); }
export function integer(n, min=0, max=MAX_SATOSHIS) {
  if (!Number.isSafeInteger(n) || n<min || n>max) fail('INTEGER_BOUNDARY');
  return n;
}
export function hex(value, maxBytes=1000000) {
  if(typeof value!=='string'||!value.length||value.length>maxBytes*2||! /^(?:[0-9a-f]{2})+$/.test(value)) fail('NONCANONICAL_HEX');
  return value;
}
export function parseOutpoint(s) {
  if(typeof s!=='string'||! /^[0-9a-f]{64}:(0|[1-9][0-9]{0,9})$/.test(s)) fail('OUTPOINT_FORMAT');
  const [txid,v]=s.split(':'); return {txid,vout:integer(Number(v),0,0xffffffff)};
}
export function parseTransaction(raw, txid) {
  hex(raw); if(txid!==undefined && !/^[0-9a-f]{64}$/.test(txid)) fail('TXID_FORMAT');
  const tx=Transaction.fromHex(raw);
  if(tx.toHex()!==raw) fail('NONCANONICAL_TRANSACTION');
  if(txid!==undefined && tx.id('hex')!==txid) fail('TXID_MISMATCH');
  if(!tx.inputs.length||!tx.outputs.length||tx.inputs.length>100||tx.outputs.length>100) fail('TX_BOUNDS');
  const seen=new Set();
  for(const i of tx.inputs) {
    const point=`${i.sourceTXID}:${i.sourceOutputIndex}`; parseOutpoint(point);
    if(seen.has(point)) fail('DUPLICATE_INPUT'); seen.add(point);
  }
  let sum=0n;
  for(const o of tx.outputs) { integer(o.satoshis); sum+=BigInt(o.satoshis); }
  if(sum>BigInt(MAX_SATOSHIS)) fail('TOTAL_VALUE_BOUNDARY');
  return tx;
}
export function addressScript(address) {
  const d=Utils.fromBase58Check(address);
  if(d.prefix.length!==1||d.prefix[0]!==0||d.data.length!==20||Utils.toBase58Check(d.data,[0])!==address) fail('MAINNET_P2PKH_ADDRESS');
  return new P2PKH().lock(address);
}
export function termsChecked(terms) {
  for(const k of ['origin','current','listing']) if(parseOutpoint(terms[k]).vout!==0) fail('ONLY_VOUT_ZERO');
  integer(terms.price,1); addressScript(terms.cancelAddress); addressScript(terms.payoutAddress);
  if(terms.cancelAddress===terms.payoutAddress) fail('SEPARATE_CANCEL_IDENTITY_REQUIRED');
  return terms;
}
export function createListing(request) {
  if(!request) fail('COVENANT_CAPABILITY_BLOCKED: explicit offline-v2 request required');
  if(request.mode!=='offline-v2') fail('PAID_TRADING_DISABLED');
  const t=request.terms;
  integer(t.price,1); addressScript(t.cancelAddress); addressScript(t.payoutAddress);
  if(t.cancelAddress===t.payoutAddress) fail('SEPARATE_CANCEL_IDENTITY_REQUIRED');
  return Object.freeze({supportedV2:true,paidTradingEnabled:false,lockingScript:OrdLockV2.lock(t.cancelAddress,t.payoutAddress,t.price)});
}
function canonicalLegacy(terms) {
  // Exact-match validation of EXISTING scripts only. Not a listing constructor API.
  const data=new Script().writeBin(Utils.fromBase58Check(terms.cancelAddress).data)
    .writeBin(OrdLock.buildOutput(terms.price,addressScript(terms.payoutAddress).toBinary()));
  return ORD_LOCK_PREFIX+data.toHex()+ORD_LOCK_SUFFIX;
}
export function assertLegacy(listing, terms) {
  termsChecked(terms);
  if(listing.id('hex')!==parseOutpoint(terms.listing).txid) fail('LISTING_TXID');
  if(listing.outputs[0]?.satoshis!==1 || listing.outputs[0]?.lockingScript.toHex()!==canonicalLegacy(terms)) fail('COVENANT_MISMATCH');
}
function inputPoint(input) { return `${input.sourceTXID??input.sourceTransaction?.id('hex')}:${input.sourceOutputIndex}`; }
function link(tx, prior) {
  if(inputPoint(tx.inputs[0])!==prior || tx.outputs[0]?.satoshis!==1) fail('LINEAGE_MISMATCH');
}
export async function requireUnspent(status, outpoint, now) {
  const s=await status(outpoint);
  now ??= Date.now();
  if(!s||s.outpoint!==outpoint) fail('STATUS_OUTPOINT_MISMATCH');
  for(const phase of ['confirmed','mempool']) {
    const state=s[phase];
    if(!['unspent','spent','unknown','not-found','timeout','not-yet-indexed'].includes(state)) fail('STATUS_MALFORMED');
    if(state!=='unspent') fail('UNSPENT_NOT_PROVEN:'+phase.toUpperCase()+'_'+state.toUpperCase().replaceAll('-','_'));
  }
  if(!Number.isSafeInteger(s.checkedAt)||s.checkedAt>now||now-s.checkedAt>15000) fail('STATUS_STALE');
}
export async function verifyLegacyListing(proofInput, termsInput, evidence) {
  // Freeze caller-controlled content before the first async trust boundary.
  const proof=structuredClone(proofInput), terms=termsChecked(structuredClone(termsInput));
  if(!evidence || typeof evidence.verifyOrigin!=='function'||typeof evidence.verifyTransaction!=='function'||typeof evidence.status!=='function') fail('TRUSTED_EVIDENCE_PROVIDER_REQUIRED');
  if(!Array.isArray(proof.hops)||proof.hops.length>32) fail('LINEAGE_BOUNDS');
  const origin=parseTransaction(proof.originHex,parseOutpoint(terms.origin).txid);
  if(origin.outputs[0]?.satoshis!==1) fail('ORIGIN_VALUE');
  const transactions=[origin]; let prior=terms.origin;
  for(const raw of proof.hops) {
    const hop=parseTransaction(raw); link(hop,prior);
    if(!/^76a914[0-9a-f]{40}88ac$/.test(hop.outputs[0].lockingScript.toHex())) fail('UNSUPPORTED_LINEAGE_SCRIPT');
    prior=hop.id('hex')+':0'; transactions.push(hop);
  }
  if(prior!==terms.current) fail('CURRENT_MISMATCH');
  const listing=parseTransaction(proof.listingHex,parseOutpoint(terms.listing).txid);
  link(listing,terms.current); assertLegacy(listing,terms); transactions.push(listing);
  if(await evidence.verifyOrigin({origin:terms.origin,raw:proof.originHex})!==true) fail('ORIGIN_CERTIFICATE_ANCHOR_UNPROVEN');
  for(const tx of transactions) if(await evidence.verifyTransaction({txid:tx.id('hex'),raw:tx.toHex()})!==true) fail('CHAIN_TRANSACTION_UNPROVEN');
  await requireUnspent(evidence.status,terms.listing);
  return Object.freeze({scope:'legacy-v1-transaction-and-status',paidTradingEnabled:false,terms:Object.freeze(terms),listingHex:listing.toHex()});
}
export function verifySpend(tx, i) {
  const input=tx.inputs[i], source=input?.sourceTransaction, output=source?.outputs[input.sourceOutputIndex];
  if(!output || (input.sourceTXID && input.sourceTXID!==source.id('hex'))) fail('SOURCE_MISMATCH');
  const spend=new Spend({sourceTXID:source.id('hex'),sourceOutputIndex:input.sourceOutputIndex,sourceSatoshis:output.satoshis,lockingScript:output.lockingScript,transactionVersion:tx.version,otherInputs:tx.inputs.filter((_,j)=>j!==i),outputs:tx.outputs,inputIndex:i,unlockingScript:input.unlockingScript,inputSequence:input.sequence??0xffffffff,lockTime:tx.lockTime});
  if(spend.validate()!==true) fail('SCRIPT_INVALID'); return true;
}
export function validatePurchase(tx, listing, terms, buyerScript, {maxFee,changeScript}) {
  assertLegacy(listing,terms); hex(buyerScript); hex(changeScript); integer(maxFee,0,100000);
  if(!/^76a914[0-9a-f]{40}88ac$/.test(buyerScript)) fail('BUYER_SCRIPT_UNSUPPORTED');
  if(inputPoint(tx.inputs[0])!==terms.listing || tx.inputs[0].sourceTransaction?.toHex()!==listing.toHex()) fail('WRONG_ITEM');
  if(tx.version!==1||tx.lockTime!==0 || tx.inputs.length<2||tx.inputs.length>20||tx.outputs.length<2||tx.outputs.length>3) fail('PURCHASE_LAYOUT');
  const [receive,pay,...change]=tx.outputs;
  if(receive.satoshis!==1||receive.lockingScript.toHex()!==buyerScript) fail('BUYER_OUTPUT');
  if(pay.satoshis!==terms.price||pay.lockingScript.toHex()!==addressScript(terms.payoutAddress).toHex()) fail('PAYOUT_MISMATCH');
  if(change.some(o=>o.lockingScript.toHex()!==changeScript)) fail('UNAPPROVED_CHANGE');
  let ins=0n, outs=0n; const seen=new Set();
  for(const [i,input] of tx.inputs.entries()) {
    const point=inputPoint(input); parseOutpoint(point); if(seen.has(point)) fail('DUPLICATE_INPUT'); seen.add(point);
    const source=input.sourceTransaction;
    if(!source || (input.sourceTXID && source.id('hex')!==input.sourceTXID)) fail('FUNDING_SOURCE');
    const prev=source.outputs[input.sourceOutputIndex]; if(!prev) fail('FUNDING_PREVOUT');
    integer(prev.satoshis,1); ins+=BigInt(prev.satoshis);
    if(i>0 && (!/^76a914[0-9a-f]{40}88ac$/.test(prev.lockingScript.toHex())||prev.satoshis===1)) fail('FUNDING_CLASSIFICATION_REQUIRED');
  }
  for(const o of tx.outputs) {integer(o.satoshis);outs+=BigInt(o.satoshis);}
  if(ins>BigInt(MAX_SATOSHIS)||outs>BigInt(MAX_SATOSHIS)||ins<outs||ins-outs>BigInt(maxFee)) fail('FEE_BOUNDARY');
  return true;
}
