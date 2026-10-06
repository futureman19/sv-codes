# Read-only SV2 evidence (API-attested, not SPV)

Run from `market/`:

```
npm run live:origin
npm run live:origin -- f8200f6f3573ba4e19fa8f94727fa6d76ca89b587dcaec0b67190efe745cbaa9:0 --save
npm test
```

The only CLI origin is the exact, fixed edition-52 demo origin. Its final receipt is read from `docs/nft/genesis/genesis-052-receipt.json` (never modified). No payload URLs are followed. `--save` overwrites `market/evidence/genesis-052-api.json` with public evidence, including exact raw transactions, observed time, confirmations/block metadata, controlling script/address, and explicit missing gates. Saved status is a historical snapshot, **not a reusable unspent authorization**. No keys, wallet auth, createAction, signatures, funding or broadcasts are requested.

## What is verified locally

- BMP v1, GEN1 target, A47C action, zero params, exact payload length and UTF-8 canonical JSON bytes; strict collection/edition/seed/schema and final receipt mint binding.
- Real compact ECDSA/secp256k1 signature, low-S/range checks. The pinned GEN1 registry public key matches `docs/js/mint.js`. The demo derivation is publicly known, so this is display authenticity only, not production anti-forgery security.
- Final raw transaction has the requested locally double-SHA256/reversed txid, canonical parser round-trip and bounded inputs/outputs. Origin is output zero, exactly one satoshi.
- Anchor output one is exactly zero-valued `OP_FALSE OP_RETURN push35("SV2" || SHA256(canonical(cert with mint=64 zeros)))`. Hashing the final mint-containing certificate would create a circular commitment and is rejected.
- Following a spender resolves **every direct parent** by exact raw hash. BigInt cumulative input/output offsets locate the exact sat, including an offset inside a multi-sat output. A moved sat is not automatically a market-compatible one-sat collectible. Fee loss, missing parent, invalid totals, wrong spender, cycles and budgets stop verification. Direct parents of the mint are resolved too; recursive full-chain validation is not claimed.

## API trust and availability

Only serialized GETs to fixed WoC mainnet transaction raw/metadata/spent and locally derived P2PKH-address unspent endpoints are permitted. Redirects and arbitrary pagination origins are rejected. Default bounds: 10-second request timeout; two retries for 429/5xx (bounded backoff); 160 attempts; five index pages; 32 hops; 1 MB raw transaction parser limit; 2.1 MB response-text limit. Overrides have hard upper bounds. Requests/timeouts include body reads. No unlimited polling.

A transaction needs positive confirmed metadata with matching txid, block height and block hash. This is an explorer assertion, **not Merkle inclusion, header PoW, chainwork, or independent SPV**. Unconfirmed transactions and unconfirmed spender traversal are intentionally unsupported/fail closed. The spent endpoint is checked against the alleged spender's locally hashed raw inputs and confirmed API metadata. A 404 alone never proves unspent; a 400/unknown response never proves availability.

Unspent evidence additionally needs the exact txid/vout/value in the full paginated index, correct address/reversed script hash, confirmed row, and explicit `isSpentInMempoolTx:false`. Index errors, omitted flags, duplicate rows, missing outputs, pagination loops/unknown cursors, stale views and unavailable network calls return unknown. `isSpentInMempoolTx:true` blocks availability. Status takes its timestamp at the start and rejects a view taking over 15 seconds; cached transaction metadata expires after 15 seconds. Fresh retrieval is not a guarantee the server itself has a fresh/complete mempool. Different API requests are not an atomic snapshot; reorgs, index lag and post-check spend races remain.

`current.availabilityProven` means only the scoped API-attested observation. If false, `current.outpoint` is the last traced candidate, not a claim that the sat remains there. The controlling script/address identifies the lock, **not the user's possession of its key**. Non-P2PKH availability is unsupported and unknown.

## Existing V2 evidence callbacks

`listingEvidence(client, receipt, {approvedFunding})` implements the four existing callback shapes. `verifyTransaction` binds raw bytes to confirmed API metadata; `status` is fresh and fail closed. `verifyOrigin` deliberately returns false for GEN1 even after a valid certificate/anchor check: **demo paid trades are forbidden**. Use `verifyCertificate` / `traceOrigin` for display evidence. No production issuer is silently invented or accepted.

`verifyFunding` defaults false. Entries must come from a separately trusted wallet classification boundary and contain exact `{outpoint, raw, walletApproved:true, assetFree:true, provenance:<nonempty trusted reference>}`. The raw transaction must locally match the outpoint txid and contain that output. This is explicitly injected classification, not a claim that explorer data, P2PKH shape, amount > 1, or absence of an inscription proves asset-free funding. Do not build this set from untrusted UI/API assertions. Existing V2 validation additionally checks supported P2PKH layout/amount and fresh unspent state.

## Still missing before any paid trade

Independent SPV/header/reorg policy; privately controlled production collection identity; real Yours extension capability and key-possession evidence; trusted wallet asset-excluding coin classification; durable reservations/reconciliation; and separately approved bounded funded sale/cancel. No wallet step or funded trade has been exercised by this read-only verifier. Existing real-interpreter offline sale/cancel tests remain separate from this live explorer proof.
