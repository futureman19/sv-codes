import {loadTransactions,traceAsset} from './verify.mjs';
const $=id=>document.getElementById(id), state=$('status');
function status(text,kind=''){state.textContent=text;state.className=kind;}
function row(parent,label,value,asset){const el=document.createElement('div');el.className='row'+(asset?' asset':'');const a=document.createElement('span'),b=document.createElement('strong');a.textContent=label;b.textContent=value+' sat';el.append(a,b);parent.append(el);}
try{
  const response=await fetch('./fixture.json',{cache:'no-store'});if(!response.ok)throw Error('Fixture unavailable');
  const f=await response.json();if(f.schema!=='sv0004-offline-v2-sale-1'||f.paidTradingEnabled!==false||f.liveChainAvailable!==false||f.realWalletTested!==false)throw Error('Fixture scope missing');
  const sources=await loadTransactions(f), tx=sources.get(f.purchase.txid);if(!tx)throw Error('Purchase missing');
  const route=traceAsset(tx,f.terms.listing,sources,f.buyerScript);
  if(route.inputIndex===0)throw Error('Expected supported V2 purchase layout');
  if(tx.outputs[route.inputIndex].satoshis!==BigInt(f.terms.price))throw Error('Fixed seller payout mismatch');
  $('price').textContent=Number(f.terms.price).toLocaleString()+' sats';
  function draw(t,r){$('inputs').replaceChildren();$('outputs').replaceChildren();
    t.inputs.forEach((input,i)=>row($('inputs'),'#'+i+' · '+(i===r.inputIndex?'Collectible':i<r.inputIndex?'Front funding':'Fee funding'),r.inputAmounts[i],i===r.inputIndex));
    t.outputs.forEach((output,i)=>row($('outputs'),'#'+i+' · '+(i===r.outputIndex?'Buyer collectible':i===r.inputIndex?'Seller payout':'Funding cushion / change'),output.satoshis,i===r.outputIndex));
  }
  draw(tx,route);status('Ready. Verify the raw transaction’s satoshi route.');
  $('receipt').textContent='Synthetic purchase txid: '+tx.id;
  $('verify').disabled=false;$('tamper').disabled=false;
  $('verify').addEventListener('click',()=>{try{const r=traceAsset(tx,f.terms.listing,sources,f.buyerScript);draw(tx,r);status('Route verified: input #'+r.inputIndex+' → buyer output #'+r.outputIndex+'. Exact satoshi offset '+r.offset+'; fee '+r.fee+' sats. No funds moved.','good');}catch(e){status('Verification refused: '+e.message,'bad');}});
  $('tamper').addEventListener('click',()=>{const changed={...tx,outputs:tx.outputs.map(x=>({...x}))};changed.outputs[route.outputIndex].script='00';try{traceAsset(changed,f.terms.listing,sources,f.buyerScript);status('Unexpected result. Stop and inspect the verifier.','bad');}catch{status('Rejected: changing the buyer’s receiving script breaks the collectible-delivery check. Original fixture is unchanged.','bad');}});
}catch(e){$('price').textContent='Proof unavailable';status('Proof unavailable: '+e.message+'. Live Buy remains disabled.','bad');}
