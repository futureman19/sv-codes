// Read-only, explorer-attested evidence. Never SPV, wallet authentication, or trade approval.
import { createHash, createPublicKey, ECDH, verify } from 'node:crypto';
import { Utils } from '@bsv/sdk';
import { parseOutpoint, parseTransaction, hex, fail, MAX_SATOSHIS } from './core.mjs';
export const DEMO_ORIGIN='f8200f6f3573ba4e19fa8f94727fa6d76ca89b587dcaec0b67190efe745cbaa9:0';
export const ISSUERS=Object.freeze({GEN1:Object.freeze({publicKey:'023a6f32a0528c1b02899c3dbd28cd055fa64ca626271578da4b4261076407a11d',collection:'sv-genesis',demo:true})});
export const sha=b=>createHash('sha256').update(b).digest();
export const canonical=v=>JSON.stringify(v,(_,x)=>x&&typeof x==='object'&&!Array.isArray(x)?Object.fromEntries(Object.keys(x).sort().map(k=>[k,x[k]])):x);
const check=(v,c)=>{if(!v)fail(c);};
export function verifyCertificate(receipt,origin,raw){
 const p=parseOutpoint(origin),tx=parseTransaction(raw,p.txid),c=receipt.cert;
 check(p.vout===0&&tx.outputs[0]?.satoshis===1,'ORIGIN_VALUE');
 check(c&&Object.keys(c).sort().join(',')==='art,col,ed,item,mint,of,seed,tr,v','CERT_SCHEMA');
 check(c.v===2&&c.col==='sv-genesis'&&c.item==='genesis-blade'&&c.of===100&&Number.isInteger(c.ed)&&c.ed>=1&&c.ed<=100,'CERT_COLLECTION');
 check(/^[0-9a-f]{16}$/.test(c.art)&&c.seed===sha(Buffer.from('sv-genesis'+c.ed)).subarray(0,3).toString('hex'),'CERT_SEED');
 check(c.tr&&Object.keys(c.tr).sort().join(',')==='core,edge'&&Object.values(c.tr).every(v=>typeof v==='string'&&/^[a-z-]{1,32}$/.test(v)),'CERT_TRAITS');
 check(receipt.txid===p.txid&&c.mint===p.txid&&receipt.edition===c.ed&&receipt.seed===c.seed,'CERT_ORIGIN');
 const e=Buffer.from(hex(receipt.envelope,312),'hex'),payload=Buffer.from(canonical(c));
 check(payload.length<=227&&e.length===85+payload.length&&e[0]===1&&e.subarray(1,5).toString()==='GEN1'&&e.readUInt16BE(5)===0xa47c&&e.subarray(7,15).equals(Buffer.alloc(8))&&e.readUInt16BE(19)===payload.length&&e.subarray(85).equals(payload),'ENVELOPE_CANONICAL');
 const n=BigInt('0xfffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141'),r=BigInt('0x'+e.subarray(21,53).toString('hex')),s=BigInt('0x'+e.subarray(53,85).toString('hex'));
 check(r>0n&&r<n&&s>0n&&s<=n/2n,'SIGNATURE_RANGE');
 const pub=ECDH.convertKey(Buffer.from(ISSUERS.GEN1.publicKey,'hex'),'secp256k1',undefined,undefined,'uncompressed');
 const key=createPublicKey({key:Buffer.concat([Buffer.from('3056301006072a8648ce3d020106052b8104000a034200','hex'),pub]),format:'der',type:'spki'});
 check(verify('sha256',Buffer.concat([e.subarray(0,21),payload]),{key,dsaEncoding:'ieee-p1363'},e.subarray(21,85)),'CERT_SIGNATURE');
 const commitment=verifyPremintAnchor(c,tx);
 return {verified:true,issuer:'GEN1',demoIssuer:true,edition:c.ed,origin,commitment,signature:'ECDSA-secp256k1-low-S',paidTradingEnabled:false};
}
// Component check only: callers must also verify final signature and origin binding.
export function verifyPremintAnchor(cert,tx){
 const commitment=sha(Buffer.from(canonical({...cert,mint:'0'.repeat(64)}))).toString('hex');
 check(tx.outputs[1]?.satoshis===0&&tx.outputs[1].lockingScript.toHex()==='006a23535632'+commitment,'PREMINT_ANCHOR');
 return commitment;
}
const BASE='https://api.whatsonchain.com/v1/bsv/main';
const PATH=/^\/(?:tx\/[0-9a-f]{64}\/hex|tx\/hash\/[0-9a-f]{64}|tx\/[0-9a-f]{64}\/(?:0|[1-9][0-9]{0,9})\/spent|address\/[1-9A-HJ-NP-Za-km-z]{26,35}\/unspent\/all(?:\?page=[0-9]{1,4})?)$/;
export class WocClient {
 constructor({fetcher=fetch,timeout=10000,retries=2,maxRequests=160,maxPages=5,clock=Date.now,sleep=ms=>new Promise(r=>setTimeout(r,ms))}={}){
  check(Number.isInteger(retries)&&retries>=0&&retries<=3&&Number.isInteger(timeout)&&timeout>0&&timeout<=30000&&Number.isInteger(maxRequests)&&maxRequests>0&&maxRequests<=200&&Number.isInteger(maxPages)&&maxPages>0&&maxPages<=10,'TRANSPORT_BOUNDS');
  Object.assign(this,{fetcher,timeout,retries,maxRequests,maxPages,clock,sleep});this.count=0;this.tail=Promise.resolve();this.transactions=new Map();
 }
 request(path){check(PATH.test(path),'ENDPOINT_NOT_ALLOWED');const job=this.tail.then(()=>this._request(path));this.tail=job.catch(()=>{});return job;}
 async _request(path){
  for(let i=0;i<=this.retries;i++){
   check(++this.count<=this.maxRequests,'REQUEST_BUDGET');
   const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),this.timeout);
   let res,body;
   try{res=await this.fetcher(BASE+path,{method:'GET',redirect:'error',signal:controller.signal,headers:{accept:'application/json'}});body=await res.text();check(body.length<=2100000,'RESPONSE_BUDGET');}
   catch{fail('API_UNAVAILABLE');}finally{clearTimeout(timer);}
   if((res.status===429||res.status>=500)&&i<this.retries){await this.sleep(Math.min(2000,250*2**i));continue;}
   if(res.status===404||res.status===400)return {http:res.status,data:null};
   check(res.ok,'API_HTTP_'+res.status);
   try{return {http:res.status,data:JSON.parse(body)};}catch{return {http:res.status,data:body};}
  }
 }
 async transaction(txid){
  check(/^[0-9a-f]{64}$/.test(txid),'TXID_FORMAT');if(this.transactions.has(txid)&&this.clock()-this.transactions.get(txid).checkedAt<=15000)return this.transactions.get(txid);
  const raw=(await this.request('/tx/'+txid+'/hex')).data;check(typeof raw==='string','TRANSACTION_UNKNOWN');
  check(Buffer.from(sha(sha(Buffer.from(hex(raw),'hex')))).reverse().toString('hex')===txid,'RAW_HASH_MISMATCH');
  const tx=parseTransaction(raw,txid),m=(await this.request('/tx/hash/'+txid)).data;
  check(m?.txid===txid&&Number.isSafeInteger(m.confirmations)&&m.confirmations>0&&Number.isSafeInteger(m.blockheight)&&m.blockheight>0&&/^[0-9a-f]{64}$/.test(m.blockhash),'CONFIRMATION_UNKNOWN');
  const record={tx,raw,metadata:{txid,confirmations:m.confirmations,blockheight:m.blockheight,blockhash:m.blockhash},checkedAt:this.clock()};this.transactions.set(txid,record);return record;
 }
 async status(outpoint){
  const started=this.clock(),base={outpoint,checkedAt:started,confirmed:'unknown',mempool:'unknown',scope:'API-attested; not SPV'};
  try{
   const p=parseOutpoint(outpoint),{tx}=await this.transaction(p.txid),o=tx.outputs[p.vout];check(o,'PREVOUT_UNKNOWN');
   const spent=await this.request(`/tx/${p.txid}/${p.vout}/spent`);
   if(spent.http===200){
    check(/^[0-9a-f]{64}$/.test(spent.data?.txid),'SPENT_RESPONSE_UNKNOWN');
    const spender=await this.transaction(spent.data.txid);
    check(spender.tx.inputs.some(i=>i.sourceTXID===p.txid&&i.sourceOutputIndex===p.vout),'SPENDER_LINEAGE');
    check(this.clock()-started<=15000,'STATUS_STALE');
    return {...base,confirmed:'spent',mempool:'spent',spender:spent.data.txid};
   }
   check(spent.http===404,'SPENT_STATUS_UNKNOWN');
   const script=o.lockingScript.toHex();check(/^76a914[0-9a-f]{40}88ac$/.test(script),'STATUS_SCRIPT_UNSUPPORTED');
   const address=Utils.toBase58Check(Array.from(Buffer.from(script.slice(6,46),'hex')),[0]),scriptHash=Buffer.from(sha(Buffer.from(script,'hex'))).reverse().toString('hex');
   let path=`/address/${address}/unspent/all`,match=null;const seen=new Set();
   for(let page=0;;page++){
    check(page<this.maxPages&&!seen.has(path),'PAGINATION_BUDGET');seen.add(path);
    const {data:d}=await this.request(path);check(d&&d.address===address&&d.script===scriptHash&&Array.isArray(d.result)&&!d.error,'INDEXER_UNKNOWN');
    for(const row of d.result)if(row.tx_hash===p.txid&&row.tx_pos===p.vout){check(!match,'DUPLICATE_UTXO');match=row;}
    const next=d['next-page'];if(next===undefined||next===null||next==='')break;
    check(typeof next==='string','PAGINATION_UNKNOWN');path=next.startsWith(BASE)?next.slice(BASE.length):next;
    check(new RegExp('^/address/'+address+'/unspent/all\\?page=[0-9]{1,4}$').test(path),'PAGINATION_UNKNOWN');
   }
   check(this.clock()-started<=15000,'STATUS_STALE');
   check(match&&match.value===o.satoshis&&match.status==='confirmed'&&Number.isSafeInteger(match.height)&&match.height>0,'UTXO_NOT_PROVEN');
   if(match.isSpentInMempoolTx===true)return {...base,confirmed:'unspent',mempool:'spent'};
   check(match.isSpentInMempoolTx===false,'UTXO_NOT_PROVEN');
   return {...base,confirmed:'unspent',mempool:'unspent',address,scriptHash};
  }catch(e){return {...base,reason:e.message,availability:/^API_(UNAVAILABLE|HTTP_)/.test(e.message)?'unavailable':'unknown'};}
 }
}
// Track the exact sat, including movement into a multi-sat output. All direct parents
// are resolved and locally hashed; recursive ancestry/PoW/SPV is deliberately not claimed.
export async function mapSat(client,spender,prior,offset='0'){
 check(typeof offset==='string'&&/^(0|[1-9][0-9]{0,15})$/.test(offset),'SAT_OFFSET');
 const {tx}=await client.transaction(spender);const p=parseOutpoint(prior);let asset=-1,prefix=0n,total=0n;
 for(const [i,input] of tx.inputs.entries()){
  const parent=await client.transaction(input.sourceTXID),o=parent.tx.outputs[input.sourceOutputIndex];check(o,'PARENT_UNKNOWN');
  if(input.sourceTXID===p.txid&&input.sourceOutputIndex===p.vout){asset=i;prefix=total;check(BigInt(offset)>=0n&&BigInt(offset)<BigInt(o.satoshis),'SAT_OFFSET');}
  total+=BigInt(o.satoshis);
 }
 check(asset>=0&&total<=BigInt(MAX_SATOSHIS),'SPENDER_LINEAGE');let sum=0n,result;
 const target=prefix+BigInt(offset);
 for(const [vout,o] of tx.outputs.entries()){const end=sum+BigInt(o.satoshis);if(target>=sum&&target<end)result={outpoint:spender+':'+vout,offset:String(target-sum)};sum=end;}
 check(sum<=total,'VALUE_BOUNDARY');check(result,'SAT_LOST_TO_FEES');return {...result,inputIndex:asset,absoluteOffset:String(target)};
}
export async function traceOrigin(client,receipt,origin=DEMO_ORIGIN,{maxHops=32}={}){
 check(Number.isInteger(maxHops)&&maxHops>=0&&maxHops<=32,'HOP_BUDGET');
 const start=await client.transaction(parseOutpoint(origin).txid),certificate=verifyCertificate(receipt,origin,start.raw);
 // Resolve every mint input too; no ancestry/SPV inference from a raw tx alone.
 for(const input of start.tx.inputs){const parent=await client.transaction(input.sourceTXID);check(parent.tx.outputs[input.sourceOutputIndex],'PARENT_UNKNOWN');}
 let current=origin,offset='0',status;const hops=[],seen=new Set();
 for(;;){check(!seen.has(current),'LINEAGE_CYCLE');seen.add(current);status=await client.status(current);
  if(!status.spender)break;check(hops.length<maxHops,'HOP_BUDGET');const next=await mapSat(client,status.spender,current,offset);hops.push({from:current,...next});current=next.outpoint;offset=next.offset;
 }
 const {tx}=await client.transaction(parseOutpoint(current).txid),o=tx.outputs[parseOutpoint(current).vout],script=o.lockingScript.toHex();
 return {schema:'sv2-api-origin-evidence-1',scope:'API-attested WoC mainnet, locally verified certificate and raw tx hashes; NOT independent SPV',observedAt:new Date(client.clock()).toISOString(),origin,certificate,current:{availabilityProven:status.confirmed==='unspent'&&status.mempool==='unspent',outpoint:current,satOffset:offset,satoshis:o.satoshis,controllingScript:script,controllingAddress:/^76a914[0-9a-f]{40}88ac$/.test(script)?Utils.toBase58Check(Array.from(Buffer.from(script.slice(6,46),'hex')),[0]):null,keyPossessionProven:false,status},hops,transactions:[...client.transactions.values()].map(r=>({raw:r.raw,...r.metadata})),paidTradingEnabled:false,missingProofGates:['independent-SPV-and-reorg-policy','production-private-issuer','real-Yours-key-possession-and-capabilities','trusted-wallet-asset-free-funding-provenance','durable-reservations','separately-approved-funded-trade'],requests:client.count};
}
export function listingEvidence(client,receipt,{approvedFunding=[]}={}){
 // Caller is a separately trusted wallet classification boundary, NOT explorer data.
 const cert=structuredClone(receipt),approved=new Map(structuredClone(approvedFunding).filter(x=>x.walletApproved===true&&x.assetFree===true&&typeof x.provenance==='string'&&x.provenance.length>0).map(x=>[x.outpoint,x]));
 return {scope:'API-attested; not SPV',paidTradingEnabled:false,policy:{demoPaidTradesAllowed:false},
  verifyOrigin:async({origin,raw})=>{try{verifyCertificate(cert,origin,raw);return false;}catch{return false;}}, // GEN1 is display-only, cannot satisfy a paid listing gate.
  verifyTransaction:async({txid,raw})=>{try{return (await client.transaction(txid)).raw===raw;}catch{return false;}},
  verifyFunding:async({outpoint,raw})=>{try{const a=approved.get(outpoint);return !!a&&a.raw===raw&&parseTransaction(raw,parseOutpoint(outpoint).txid).outputs[parseOutpoint(outpoint).vout]!==undefined;}catch{return false;}},
  status:outpoint=>client.status(outpoint)};
}
