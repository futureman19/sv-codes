// Read-only transaction/satoshi-flow verifier. No wallet or network calls.
export function parseTransaction(hex) {
  if(typeof hex!=='string'||hex.length>2000000||!/^([0-9a-f]{2})+$/.test(hex))throw Error('Invalid transaction hex');
  const b=Uint8Array.from(hex.match(/../g),x=>parseInt(x,16));let pos=0;
  const take=n=>{if(!Number.isSafeInteger(n)||n<0||pos+n>b.length)throw Error('Truncated transaction');const v=b.slice(pos,pos+n);pos+=n;return v;};
  const num=n=>take(n).reduceRight((a,x)=>a*256n+BigInt(x),0n);
  const vi=()=>{const first=Number(num(1));if(first<253)return first;const n=num(first===253?2:first===254?4:8);if(n>100000n||n<BigInt(first===253?253:first===254?65536:4294967296))throw Error('Invalid compact size');return Number(n);};
  const hx=a=>Array.from(a,x=>x.toString(16).padStart(2,'0')).join('');
  const version=Number(num(4)), inputs=[], outputs=[];const ni=vi();if(!ni||ni>100)throw Error('Input count out of range');
  for(let i=0;i<ni;i++){const txid=hx(take(32).reverse()),vout=Number(num(4)),script=hx(take(vi())),sequence=Number(num(4));inputs.push({txid,vout,script,sequence,outpoint:txid+':'+vout});}
  if(new Set(inputs.map(x=>x.outpoint)).size!==inputs.length)throw Error('Duplicate input');
  const no=vi();if(!no||no>100)throw Error('Output count out of range');
  for(let i=0;i<no;i++){const satoshis=num(8);if(satoshis>2100000000000000n)throw Error('Invalid amount');outputs.push({satoshis,script:hx(take(vi()))});}
  const locktime=Number(num(4));if(pos!==b.length)throw Error('Trailing bytes');
  return {version,inputs,outputs,locktime,bytes:b};
}
export async function transactionId(tx){const hash=await crypto.subtle.digest('SHA-256',await crypto.subtle.digest('SHA-256',tx.bytes));return Array.from(new Uint8Array(hash).reverse(),x=>x.toString(16).padStart(2,'0')).join('');}
export async function loadTransactions(fixture){
  const found=[],seen=new Set();let visits=0;
  function walk(v){if(++visits>10000)throw Error('Fixture too large');if(!v||typeof v!=='object')return;if(typeof v.rawHex==='string'&&!seen.has(v.rawHex)){seen.add(v.rawHex);found.push(v);}for(const x of Object.values(v))if(x&&typeof x==='object')walk(x);}
  walk(fixture);if(!found.length||found.length>100)throw Error('No bounded transaction set');const map=new Map();
  for(const r of found){const tx=parseTransaction(r.rawHex),id=await transactionId(tx);if(r.txid&&r.txid!==id)throw Error('Transaction hash mismatch');map.set(id,{...tx,id});}
  return map;
}
export function traceAsset(tx, listingOutpoint, sources, expectedScript){
  const inputIndex=tx.inputs.findIndex(x=>x.outpoint===listingOutpoint);if(inputIndex<0)throw Error('Listing input missing');
  let total=0n,offset=0n;const inputAmounts=[];
  for(let i=0;i<tx.inputs.length;i++){const input=tx.inputs[i],src=sources.get(input.txid)?.outputs[input.vout];if(!src)throw Error('Missing source transaction');inputAmounts.push(src.satoshis);if(i<inputIndex)offset+=src.satoshis;if(i===inputIndex&&src.satoshis!==1n)throw Error('Collectible input is not one satoshi');total+=src.satoshis;}
  let start=0n,outputIndex=-1;
  for(let i=0;i<tx.outputs.length;i++){const o=tx.outputs[i];if(offset>=start&&offset<start+o.satoshis){if(o.satoshis!==1n||start!==offset||o.script!==expectedScript)throw Error('Collectible satoshi does not reach the expected one-satoshi output');outputIndex=i;}start+=o.satoshis;}
  if(outputIndex<0)throw Error('Collectible satoshi falls into fees');const fee=total-start;if(fee<0n)throw Error('Outputs exceed inputs');return {inputIndex,outputIndex,offset,fee,total,inputAmounts};
}
