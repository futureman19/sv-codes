/* Run: node docs/js/tests/mint.test.js. Fixtures are synthetic signed test data, not chain receipts. */
'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), vm = require('node:vm');
const S = require('../svc.js'), D = require('../decoder.js'), M = require('../mint.js'), F = require('./mint-fixtures.json');
let count=0; function check(name, fn){ fn(); count++; console.log('ok - '+name); }
const scan = hex => ({env:S.parseEnvelope(S.hexToBytes(hex)),sig:'valid',issuer:M.ISSUER});
check('approved token signature independently verified',()=>assert(M.token(scan(F.token))));
for (const name of ['wrongIssuer','wrongTarget','wrongAction','wrongEndpoint','price','version','collection','supply','noncanonical']) check('reject '+name,()=>assert.equal(M.token(scan(F[name])),null));
for (const sig of ['invalid','demo','unverified']) check('reject scan '+sig,()=>assert.equal(M.token({...scan(F.token),sig}),null));
check('reject mismatched issuer registry',()=>assert.equal(M.token({...scan(F.token),issuer:'unknown'}),null));
check('valid response binds exact cert',()=>assert.deepEqual(M.verifyReply(F.reply).cert,F.reply.cert));
for (const field of ['seed','txid','edition']) check('reject changed '+field,()=>assert.throws(()=>M.verifyReply({...F.reply,[field]:field==='edition'?2:'0'.repeat(64)})));
check('reject changed canonical cert',()=>assert.throws(()=>M.verifyReply({...F.reply,cert:{...F.reply.cert,art:'<img onerror=alert(1)>'}})));
check('reject malformed hex',()=>assert.throws(()=>M.verifyReply({...F.reply,envelope:'zz'+F.reply.envelope.slice(2)})));
check('reject tampered signature',()=>assert.throws(()=>M.verifyReply({...F.reply,envelope:F.reply.envelope.slice(0,42)+'00'.repeat(64)+F.reply.envelope.slice(170)})));
check('Base58Check mainnet address',()=>{assert(M.validAddress('1BoatSLRHtKNngkdXEeobR76b53LETtpyT'));assert(!M.validAddress('1BoatSLRHtKNngkdXEeobR76b53LETtpyU'));assert(!M.validAddress('private key'));});
// Rasterize the unmodified shipping encoder into a real RGBA buffer, then recover with shipping image decoder.
const context = vm.createContext({SVC:S,setInterval,clearInterval,TextEncoder,Uint8Array,Date});
vm.runInContext(fs.readFileSync(require.resolve('../encoder.js'),'utf8')+'\nthis.encoder=SVEnc;',context);
const size=640, rgba=new Uint8Array(size*size*4);
const colors={'#ffffff':[255,255,255],'#000000':[0,0,0],'#00FFFF':[0,255,255],'#FF00FF':[255,0,255],'#FFFF00':[255,255,0],'#FF0000':[255,0,0]};
const ctx={fillStyle:'',fillRect(x,y,w,h){const color=colors[this.fillStyle];for(let r=Math.ceil(y);r<Math.min(size,y+h);r++)for(let c=Math.ceil(x);c<Math.min(size,x+w);c++){let i=(r*size+c)*4;rgba.set([...color,255],i);}}};
const canvas={width:size,height:size,getContext(){return ctx;}};
check('existing encoder -> RGBA -> decoder -> identical verified envelope',()=>{
 let stats;context.encoder.makeBroadcaster(canvas,s=>stats=s).start(M.verifyReply(F.reply).bytes);
 assert.match(stats.mode,/STATIC/);
 const result=new D.StreamScanner(M.ISSUER).feedBits(D.decodeImageData(rgba,size,size));
 assert.equal(result.sig,'valid'); assert.equal(S.bytesToHex(result.env.payload),S.bytesToHex(M.verifyReply(F.reply).bytes.slice(85)));
});
// Minimal DOM exercises actual async mount/event code; no HTML parser or injected markup is permitted.
class Element {constructor(tag){this.tag=tag;this.children=[];this.style={};this.classList={remove(){}};this.events={};this.value='';this.disabled=false;this.hidden=false;this.textContent='';}append(e){this.children.push(e);}replaceChildren(){this.children=[];}setAttribute(){}addEventListener(n,f){this.events[n]=f;}getContext(){return ctx;}toDataURL(){return 'data:image/png;base64,';}set innerHTML(v){throw Error('Untrusted HTML sink');}}
global.document={createElement:t=>new Element(t)};global.SVEnc=context.encoder;global.SVReveal={render(){return {};}};
const all = e => [e,...e.children.flatMap(all)];
const button=(r,s)=>all(r).find(e=>e.tag==='button'&&e.textContent===s);
const settle=()=>new Promise(r=>setImmediate(r));
let calls=[],queue=[];global.fetch=async(url,opts)=>{calls.push({url,opts});const d=queue.shift();if(d instanceof Error)throw d;return {ok:d.status<300,status:d.status,json:async()=>d.data};};
const status=(remaining=100,pending=0)=>({status:200,data:{col:'sv-genesis',supply:100,remaining,pending,minted:[]}});
async function ui(){
 for(const name of ['wrongIssuer','wrongEndpoint','price']) {const root=new Element('root');const n=calls.length;check('untrusted mount makes no fetch '+name,()=>{assert.equal(M.mount(root,scan(F[name])),null);assert.equal(calls.length,n);});}
 queue=[status()];let root=new Element('root'),dispose=M.mount(root,scan(F.expiry));await settle();check('nonzero expiry disables claim without verified height',()=>{const input=all(root).find(e=>e.tag==='input');input.value='1BoatSLRHtKNngkdXEeobR76b53LETtpyT';input.events.input();assert(button(root,'Claim free edition').disabled);});dispose();
 for(const response of [{status:409,data:{error:'sold_out'}},{status:409,data:{error:'duplicate'}},{status:429,data:{}},{status:503,data:{}},{status:202,data:{error:'pending'}},new Error('offline'),{status:200,data:F.reply}]){
  queue=[status()];root=new Element('root');dispose=M.mount(root,scan(F.token));await settle();const input=all(root).find(e=>e.tag==='input');input.value='1BoatSLRHtKNngkdXEeobR76b53LETtpyT';input.events.input();
  const claim=button(root,'Claim free edition');assert(!claim.disabled);queue=[response,status(response.status===409&&response.data.error==='sold_out'?0:99)];await claim.events.click();
  check('UI claim response '+(response.status||'network'),()=>{assert(input.disabled);assert(calls.every(c=>c.url.startsWith(M.ORIGIN+'/mint/sv-genesis/')));assert(calls.filter(c=>c.opts.method==='POST').every(c=>JSON.parse(c.opts.body).address===input.value));if(response.status===200){assert(button(root,'Show my code'));assert(claim.disabled);}else assert(!button(root,'Show my code'));});dispose();
 }
 queue=[status(0,1)];root=new Element('root');dispose=M.mount(root,scan(F.token));await settle();check('pending final mint distinct from sold out',()=>assert(all(root).some(e=>e.textContent.includes('recovery pending'))));dispose();
 queue=[status(0)];root=new Element('root');dispose=M.mount(root,scan(F.token));await settle();check('sold out disables claims and displays gallery',()=>{assert(button(root,'Claim free edition').disabled);assert(all(root).some(e=>e.textContent==='MINT COMPLETE'));assert(all(root).some(e=>e.textContent.includes('Collection gallery')));});dispose();
 for (const valid of [true,false]) {
  const state=status(99);state.data.minted=[{edition:F.reply.edition,txid:F.reply.txid}];queue=[state];
  root=new Element('root');dispose=M.mount(root,scan(F.token));await settle();
  queue=[{status:200,data:valid?F.reply:{...F.reply,txid:'0'.repeat(64)}}];
  await button(root,'View / recover code #'+F.reply.edition).events.click();
  check('public receipt recovery '+(valid?'verified':'tamper rejected'),()=>assert.equal(!!button(root,'Show my code'),valid));dispose();
 }
 console.log(count+' passed, 0 failed');
}
ui().catch(e=>{console.error(e);process.exitCode=1;});
