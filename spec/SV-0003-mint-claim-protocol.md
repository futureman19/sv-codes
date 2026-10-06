# SV-0003: Mint Claim Protocol

| | |
|---|---|
| **Number** | SV-0003 |
| **Title** | Mint Claim Protocol — One Poster, Personal Collectibles |
| **Status** | **Draft** |
| **Category** | Application Specification (Bitcoin Machine Protocol) |
| **Created** | 2026-10-06 |
| **Requires** | SV-0001, SV-0002, BMP-0000 |

---

## 1. Abstract

One master SV Code is an inert **claim token**, not a wallet or a collectible. Anyone may scan it to request a random remaining edition of the 100-piece SV-GENESIS collection. Supply and assignments live on the server; ownership lives on-chain. Each successful claimant receives a personal signed SV-0002 certificate and code. After exhaustion the same poster becomes a collection viewer: **MINT COMPLETE**. The poster never dies; it graduates.

## 2. Envelope binding

The envelope MUST use action `0xC1A1` (MINT_CLAIM), target `0x47454E31` (GEN1), and the registered genesis issuer. The demo issuer is derived by passing the hex SHA-256 of UTF-8 `sv genesis collection issuer key v1 (demo)` to `svcode.crypto.key_from_hex`, exactly as in `poc/make_genesis_001.py`. This publicly known demo key provides no production anti-forgery security. Production MUST use a private randomly generated issuer key and a distinct registered identity.

Unknown or invalid issuers remain display-only. Clients MUST bind the trusted issuer, action, collection, target, and approved HTTPS endpoint together before enabling network claims. A signed pointer is never executable code or permission to access an arbitrary endpoint.

## 3. Claim certificate

Canonical JSON follows SV-0002 §3: sorted keys, no insignificant whitespace, UTF-8, integer numbers. The encoded certificate MUST measure at most 227 bytes and fit one static frame.

```json
{"col":"sv-genesis","endpoint":"https://sv-mint.fly.dev","exp":0,"price":0,"supply":100,"v":3}
```

The example above measures **94 UTF-8 bytes** (canonical serialization), within the 227-byte limit.

`col` identifies the collection; `supply` is its immutable maximum; `price` MUST be 0 in v1; `endpoint` is the approved mint origin; `exp` is a block-height expiry, with 0 meaning never; `v` MUST be 3. Clients MUST reject unsupported nonzero prices. A nonzero expiry requires a verified current chain height before claiming; inability to establish height MUST disable the claim, not treat the token as unexpired.

## 4. Claim flow

1. Scan and verify the master envelope.
2. `GET /mint/{col}/status` returns `col`, `supply`, `remaining`, `commitment`, and public minted-edition records. Availability is advisory until the server atomically reserves a claim.
3. `POST /mint/{col}/claim` with JSON `{ "address": "<mainnet P2PKH address>" }` reserves the next random edition and mints directly to that address.
4. Success returns `{edition, seed, cert, txid}` plus a signed serialized BMP `envelope` (hex). `cert` is the final SV-0002 JSON object. The envelope carries exactly its canonical bytes with action `0xA47C` and target GEN1; it lets the browser encode a personal SV Code without receiving an issuer private key.
5. `GET /mint/{col}/edition/{edition}` returns a persisted accepted signed receipt, allowing recovery after a lost HTTP response without minting again. Pending or unknown editions return 404; the gallery may expose this public recovery path. A copied receipt is not proof of ownership.
6. The client MUST verify the returned envelope and certificate binding before displaying a successful collectible. Render the item card through SVReveal and encode the verified envelope into the personal code locally.

There is at most one successful claim per address per collection, enforced by a SQLite unique constraint. A duplicate returns HTTP 409. Exhaustion returns HTTP 409 with `error: sold_out`. Rate limiting returns 429. Transient upstream or funding failures return 502/503. An ambiguous broadcast MUST remain reserved and recoverable; the server MUST NOT reassign its edition or select different inputs until reconciliation establishes the original transaction's outcome. A repeat request may receive pending/recovery state but never a second mint.

An address-only request does not demonstrate ownership of that address and does not establish one-person-one-claim. Users MUST paste an address they control. Never paste wallet seeds or private keys. Preserve the one-satoshi collectible UTXO: a general-purpose wallet may otherwise spend it as ordinary funding.

## 5. Lazy mint-on-claim

Derive an edition's seed as `SHA-256(b"sv-genesis" || edition_bytes)[:3].hex()`, where `edition_bytes` is the ASCII base-10 representation without padding (editions 1 through 100). The encoding is normative to avoid cross-language ambiguity.

Build the canonical per-edition certificate with the published genesis reveal generator and derived traits; measure every edition against the 227-byte limit. First set `mint` to 64 zero characters and compute SHA-256 of those canonical bytes (SV-0002 §4.1). The mint transaction has:

- output 0: 1 satoshi to the claimant's validated P2PKH address;
- output 1: zero satoshis, `OP_FALSE OP_RETURN <ASCII SV2 || 32-byte pre-mint hash>`;
- optional output 2: funding-wallet change.

Use the proven faucet BSV sighash/signature flow. After building the transaction, fill its txid into the final certificate and sign its BMP envelope. A transaction acceptance response is not SPV confirmation. Owner-tier and confirmed Anchor-tier checks remain separate from signature validation.

## 6. Supply and crash safety

SQLite lives on a persistent Fly volume. `mints(col,supply,commitment,shuffle_json,opened_at)` fixes collection state. `claims(col,edition,address,txid,ts)` records assignments with uniqueness on `(col,edition)` and `(col,address)`; implementations MUST persist additional reservation/broadcast state and raw transaction bytes before broadcasting. Concurrent claims MUST serialize assignment and wallet spending, including across process restarts. Deploy a single writer against the volume unless implementing distributed coordination.

Rate limits MUST use `Fly-Client-IP`, never `req.client.host`. Requests without an authenticated edge-provided client identity MUST NOT share a pretend socket-peer identity. WoC calls MUST be serialized. Fresh funding change MUST be derived from the accepted parent transaction rather than a stale address index. Handle mempool conflicts conservatively: never retry with a new edition or fabricate success.

## 7. Fairness and exhaustion

At mint open, securely shuffle the list of integers 1 through 100 once. Publish `commitment = SHA-256(canonical_json(shuffle_list)).hex()` before accepting claims. Assign entries in list order under the claim lock. Publish each successful assignment's zero-based index so the reveal can be audited; do not reveal future assignments before sellout.

After all editions are successfully minted, publish the original `shuffle` list. An auditor checks its length, uniqueness, range, canonical hash, and every recorded assignment against its index. This detects changes to the committed order; it does not prove unbiased initial shuffling, resistance to operator self-claiming, or resistance to multiple addresses.

`remaining = 0` MUST disable claims and display **MINT COMPLETE**, with the collection gallery and ownership links. Pending final transactions are distinguishable from completed sellout: do not reveal future or unresolved assignment data prematurely. The original poster remains valid indefinitely unless explicitly expired.

## 8. Verification gates

Measure claim and all item certificates. Exercise concurrency, duplicate-address rejection, exhaustion, crash recovery, ambiguous broadcast handling, and reveal auditing. Decode master and minted personal artifacts through independent Python and JavaScript implementations (PNG, JPEG, camera-scene simulations, screenshot simulations). Re-run all seven existing JavaScript harnesses after any site-JavaScript changes. Before graduating SV-0002, publish a real transaction receipt and independent certificate/hash round-trip evidence.
