# Supported OrdLockV2 — bounded offline proof

**Paid trading is disabled. No user funds, wallet signatures or broadcast.** V1 fixtures remain compatibility tests only.

## Design resolution

The old draft input0→output0 rule was our restriction, not a user requirement. Supported V2 binds listing input i to seller payout output i. The approved replacement checks exact cumulative satoshi flow. Current upstream lock/planPurchase/purchaseListing/cancelListing and real SDK Spend are executed. No deprecated constructor or dependency downgrade is used.

The covenant binds payment, NOT buyer delivery. A test proves changing the buyer can leave the covenant valid while our application guard and ordinary ALL funding signatures reject it.

## Run

`npm ci --ignore-scripts`, `npm test`, `npm run fixture`, `npm run replay:v2`.

Pinned SDK 2.8.11, templates 0.0.43, types 0.0.52. No @1sat/actions dependency or execution: its front preparation can broadcast.

## Exact public fixture

`fixtures/offline-v2-sale.json` contains synthetic public raw transactions and all parents, no exported private keys. NEVER fund these disposable deterministic addresses. The synthetic origin seed is unvalidated; every listing/purchase/alternative-cancel input passes actual SDK Spend.

|Transaction|Inputs in order|Outputs in order|Input/output totals; fee|
|---|---|---|---|
|Listing|2,000 ordinary; origin 1 sat (origin vout 1)|2,000 ordinary; 0; V2 1 sat (listing vout 2)|2,001 / 2,001; 0|
|Purchase|5,000 front; listing 1 sat; 500 fee funding|3,766 cushion; 1,234 payout; buyer 1 sat; 300 change|5,501 / 5,301; 200|
|Alternative cancel|listing 1 sat; 500 ordinary|owner 1 sat; 300 change|501 / 301; 200|

Purchase listing input 1, payout output 1, buyer output 2. Input prefix 5,000 equals output prefix 3,766 + 1,234 = 5,000. Our flow arithmetic uses BigInt; reports use decimal strings. Upstream planner numbers are bounded safe integers. Cancel and purchase conflict; they are not sequential chain events. Zero listing fee is synthetic script evidence, not miner acceptance evidence.

## V2 APIs

- `core.createListing({mode:'offline-v2',terms:{price,payoutAddress,cancelAddress}})` returns `{supportedV2:true,paidTradingEnabled:false,lockingScript}` using real V2.lock. A script constructor, not a funded listing service. Other modes fail.
- `v2.assertV2(listing,terms)` compares exact entire reconstructed bytes. Decoder-tolerated trailing metadata is rejected.
- `v2.verifyV2Listing(proof,terms,evidence)` checks origin→current→listing prefix flow, required parents, ALL lineage/listing scripts and ordinary funding classification. Origin/current/listing accept arbitrary strict canonical uint32 vouts with actual existing outputs.
- `terms={origin,current,listing,price,payoutAddress,cancelAddress}`. Price is bounded positive safe integer; canonical mainnet P2PKH payout/cancel addresses must differ.
- `proof={originHex,hops:[{raw,outpoint}],listingHex,sourceHexes:[raw...]}`. Hops chronological, max32; source parents max100. Intermediate asset scripts P2PKH only; broader resale covenant history remains unsupported.
- `v2.satFlow(tx,inputIndex,outputIndex)` requires attached hash-matching parents, exact 1-sat endpoints, equal BigInt prefixes, bounded sums and no duplicate inputs. Alone it does not classify funding or prove availability.
- `v2.validateV2Purchase(tx,listing,terms,options,evidence)` enforces one explicit front input, listing, one trailing fee input; cushion/filler, payout, receive, change outputs. No extras. Options `{frontOutpoint,feeOutpoint,buyerScript,changeScript,expectedFee,maxFee}`. Fee is exact; funding must be classified asset-free and fresh/unspent.
- `core.verifySpend(tx,index)` runs actual SDK interpreter. Layout validation alone does NOT validate signatures. Completed fixtures/replay explicitly check every input.

Legacy APIs retain previous vout-zero compatibility restrictions; they are not V2 APIs. Shared parsers enforce canonical outpoints/raw bytes, hashes, integer bounds, counts and duplicates.

## CWI preparation boundary

`createYoursAdapter(window,evidence).prepareV2Purchase({mode:'offline-v2',proof,terms,sourceBEEF,...options,approve})` uses window.CWI. Already-funded explicit front AND fee sources must exist in sourceBEEF. Missing front returns FRONT_FUNDING_CAPABILITY_BLOCKED. No automatic preparation or coin-selection fallback.

Only waitForAuthentication and createAction are called, preserving explicit input/output order and inputBEEF bytes. Options: signAndProcess:false, noSend:true, randomizeOutputs:false, acceptDelayedBroadcast:false, returnTXIDOnly:false. Approval sees frozen exact terms, recipients, sources and fees. Per-adapter reservation survives failed/uncertain attempts but is not durable across processes/tabs.

Returned deferred AtomicBEEF is checked for exact parents, order, amounts, fees, classification and sat flow. Incompatible/processed/txid-only returns stop with WALLET_CAPABILITY_BLOCKED. Real V2 purchase template generates the non-secret covenant unlock; that input is interpreted. Fresh status recheck precedes `prepared-not-signed-not-sent` return.

No signAction/createSignature/cancel wallet signer/broadcast methods. Funding signatures are not requested or proven by preparation. **Tests mock the actual CWI method boundary; no real wallet evidence exists.** A wallet ignoring no-send options is outside the proven boundary.

## Trusted evidence contract — not built-in SPV

Application code must provide `verifyOrigin({origin,raw})`, `verifyTransaction({txid,raw})`, `verifyFunding({outpoint,raw})` returning exactly true only after independent certificate/anchor, chain proof, or authorized asset-excluding funding checks respectively. `status(outpoint)` must return `{outpoint,confirmed:'unspent',mempool:'unspent',checkedAt:Date.now()}`. Unknown/spent/not-found/stale (>15s)/future/mismatched results fail closed. Historical consumed lineage funding is classified, not required currently unspent. Listing and purchase funding are fresh-checked; races remain after checks.

`live-evidence.mjs` now implements a bounded **API-attested, not SPV** read-only provider and real GEN1 certificate/anchor verification; see [LIVE-EVIDENCE.md](LIVE-EVIDENCE.md). The live CLI never calls the CWI adapter. Demo GEN1 deliberately returns false from the paid-listing `verifyOrigin` callback even when its display certificate is valid. Funding remains false without a separately trusted wallet-approved asset-free provenance set. Synthetic tests remain labeled; hashes/BEEF alone do not establish confirmation or availability.

Tests cover term/script mutation, front amount, receive/order, extra assets/funding, asset-to-payout/fee, exact fee drift, unknown state, wrong cancel key and CWI returned-layout rejection. Independent published-fixture replay imports no key generator and repeats hashing, parsing, flow and all-input interpretation.

Production remains blocked on certificate/anchor/chain/funding providers, real wallet layout/no-send/signature evidence, durable reservation/reconciliation, and separately reviewed explicit-approval signing/send. Public paid checkout stays off. The static `/market-preview/` page independently parses the public V2 fixture and traces the collectible satoshi without wallet access. Run `npm test` for the combined core and browser-verifier tests. The preview does not execute covenant scripts in the browser or claim chain settlement.
