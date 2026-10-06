import {inspectWallet} from './wallet-check.mjs';
const check=document.querySelector('#check'),copy=document.querySelector('#copy'),status=document.querySelector('#status'),report=document.querySelector('#report');let busy=false,saved='';
check.addEventListener('click',async()=>{
  if(busy)return;busy=true;check.disabled=true;copy.disabled=true;saved='';status.textContent='Reading wallet capability assertions. No signing or payment request.';
  try{
    const result=await inspectWallet(window,{approved:true});saved=JSON.stringify(result,null,2);report.textContent=saved;document.querySelector('#details').open=true;
    const messages={'unavailable':'No CWI wallet detected in this browser. Open in the desktop browser where Yours is installed.','provider-access-failed':'The wallet interface could not be read. No transaction was requested.','incomplete':'The read-only check is incomplete. Inspect the report; no payment or signature was requested.','read-only-check-passed':'Read-only check passed. Transaction ordering, ownership and funded trading are still untested.'};
    status.textContent=messages[result.status]||'Check completed with limited information.';copy.disabled=false;
  }catch{status.textContent='Diagnostic could not complete. No transaction or signature was requested.';}
  finally{busy=false;check.disabled=false;}
});
copy.addEventListener('click',async()=>{if(!saved)return;try{await navigator.clipboard.writeText(saved);status.textContent='Report copied. Share it only if you choose; it contains no addresses, keys or wallet balances.';}catch{status.textContent='Clipboard unavailable. You can select the visible diagnostic report manually.';}});
