// Explicitly read-only CWI diagnostics. No wallet authentication request,
// key access, transaction creation, signatures, sending, storage or telemetry.
const methods=['getVersion','getNetwork','isAuthenticated','createAction','signAction','abortAction'];
async function bounded(call,ms){let timer;try{return await Promise.race([Promise.resolve().then(call),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('TIMEOUT')),ms);})]);}finally{clearTimeout(timer);}}
export async function inspectWallet(host,{approved=false,timeoutMs=5000}={}){
  if(approved!==true)throw Error('USER_GESTURE_REQUIRED');
  if(!Number.isInteger(timeoutMs)||timeoutMs<1||timeoutMs>10000)throw Error('INVALID_TIMEOUT');
  const base={schema:'sv-wallet-readonly-check-v1',checkedAt:new Date().toISOString(),readOnly:true,paidTradingEnabled:false,signingTested:false,broadcastTested:false,transactionOrderingTested:false,providerBrandVerified:false};
  let wallet;
  try{wallet=host?.CWI;}catch{return {...base,status:'provider-access-failed'};}
  if(!wallet)return {...base,status:'unavailable',note:'No CWI provider detected in this browser. This does not establish whether a wallet is installed elsewhere.'};
  const advertisedMethods={};
  try{for(const name of methods)advertisedMethods[name]=typeof wallet[name]==='function';}catch{return {...base,status:'provider-access-failed'};}
  const report={...base,status:'detected',advertisedMethods,checks:{}};
  // Serialize requests; no automatic authentication or retries after a timeout.
  for(const name of methods.slice(0,3)){
    if(!advertisedMethods[name]){report.checks[name]={status:'missing'};continue;}
    try{
      const value=await bounded(()=>wallet[name]({}),timeoutMs);
      if(name==='getNetwork'){
        if(!value||!['mainnet','testnet'].includes(value.network))throw Error('INVALID_RESULT');
        report.checks[name]={status:'ok',network:value.network};
      }else if(name==='getVersion'){
        if(!value||typeof value.version!=='string'||!value.version.length||value.version.length>64||/[^\x20-\x7e]/.test(value.version))throw Error('INVALID_RESULT');
        report.checks[name]={status:'ok',version:value.version};
      }else{
        if(!value||typeof value.authenticated!=='boolean')throw Error('INVALID_RESULT');
        report.checks[name]={status:'ok',authenticated:value.authenticated};
      }
    }catch(error){
      const code=error?.message==='TIMEOUT'?'timeout':error?.message==='INVALID_RESULT'?'invalid-result':'refused-or-failed';
      report.checks[name]={status:code};
      if(code==='timeout'){report.status='incomplete';return report;}
    }
  }
  report.status=Object.values(report.checks).every(x=>x.status==='ok')?'read-only-check-passed':'incomplete';
  report.note='Read-only provider assertions only. This does not prove Yours identity, wallet ownership, exact transaction layout, signing, or a successful trade.';
  return report;
}
