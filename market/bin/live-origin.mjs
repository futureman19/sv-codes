import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { WocClient, traceOrigin, DEMO_ORIGIN } from '../src/live-evidence.mjs';
const args=process.argv.slice(2);
if(args.some(a=>a!=='--save'&&a!==DEMO_ORIGIN)||args.length>2)throw new Error('Usage: npm run live:origin -- [fixed edition-52 origin] [--save]');
const receipt=JSON.parse(await readFile(new URL('../../docs/nft/genesis/genesis-052-receipt.json',import.meta.url),'utf8'));
try{
 const report=await traceOrigin(new WocClient(),receipt);
 const json=JSON.stringify(report,null,2)+'\n';
 if(args.includes('--save')){await mkdir(new URL('../evidence/',import.meta.url),{recursive:true});await writeFile(new URL('../evidence/genesis-052-api.json',import.meta.url),json);}
 console.log(json);
}catch(e){console.log(JSON.stringify({schema:'sv2-api-origin-evidence-1',origin:DEMO_ORIGIN,scope:'API-attested; not SPV',paidTradingEnabled:false,availability:'unavailable',reason:e.message},null,2));process.exitCode=1;}
