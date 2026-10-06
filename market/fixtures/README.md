# Public OFFLINE fixtures

`offline-v2-sale.json` is the headline supported V2 synthetic proof, generated with npm run fixture and independently replayed with npm run replay:v2. Top-level terms/buyerScript and origin/listing/purchase/cancel objects include txid/rawHex/interpreterInputs; origin supplies all required source outputs (sources is therefore empty). Sat-flow reports show exact BigInt prefixes and sums. Never fund these disposable addresses. No keys are exported.

Every listing, purchase and alternative-cancel input passes real SDK Spend. Origin seed is not validated or chain-proven. Purchase and cancel conflict. No real CWI, SPV, live availability or receipt claim. `offline-legacy-sale.json` remains compatibility-only, regenerated with npm run fixture:legacy.
