# SV-0002: Sealed Collection Certificates

| | |
|---|---|
| **Number** | SV-0002 |
| **Title** | Sealed Collection Certificates — Visual Collectibles with On-Chain Ownership |
| **Status** | **Draft** (graduates to Stable when a second independent implementation passes §9 test vectors AND one real mint exists on-chain) |
| **Category** | Application Specification (Bitcoin Machine Protocol) |
| **Created** | 2026-10-06 |
| **Requires** | SV-0001 (visual matrix), BMP-0000 ([bmp repo](https://github.com/futureman19/bmp)) |

---

## 1. Abstract

A sealed collection is a series of collectibles whose **artwork is the SV Code itself**. There is no separate "image vs. token" split: the visual artifact people trade, display, and screenshot *is* the machine-readable certificate. Scanning a piece reveals what the item is — its identity, procedurally-defined appearance, traits, and edition — plus a pointer to its on-chain mint.

Ownership is **never** embedded in the image or in a transferable private key. Ownership lives on-chain as a 1-satoshi ordinal UTXO created at mint. Claiming a piece is a wallet-signed on-chain event; transferring it is an ordinary ordinal send. The image, the certificate, and the ownership ledger are three views of one fact.

Certificates are **game-agnostic**. Any number of games may recognize, render, and honor the same item simultaneously (§7), while ownership remains an exclusive on-chain fact enforced by the ordinal. This is what makes a sealed collection a *standard* rather than a game asset.

## 2. Design principles

1. **Identity ≠ ownership.** A piece's identity (what it is) is fixed forever in its signed certificate. Its ownership (who holds it) is a chain-state fact that changes with transfers. Conflating the two is what makes naive "key in the image" designs fail.
2. **No private key ever circulates.** The item has no keypair. It never acts; the *owner* acts, signing with their wallet key, and the chain determines which wallet speaks for the item. There is no secret to leak, copy, or transfer unsafely. The item's permanent identity is its **mint outpoint** — immutable, unique, and already on-chain.
3. **Forgery must be impossible, verification must be trivial.** Anyone can screenshot the piece. The screenshot scans to the *same* certificate pointing at the *same* mint outpoint — a copy that announces itself as a copy. Counterfeiting requires forging the issuer's ECDSA signature.
4. **Static-frame first.** Collectibles are scanned from stills, so the certificate MUST fit one static SV-0001 frame (§3.3): ≤ 227 bytes of envelope data.

## 3. Certificate schema

The certificate is **canonical JSON**: keys sorted lexicographically, no insignificant whitespace, UTF-8, integers unquoted, hex lowercase.

| Field | Type | Req | Description |
|---|---|---|---|
| `v` | int | ✓ | Schema version. `2` for this specification. |
| `col` | string | ✓ | Collection slug, e.g. `"grydbound-armory"`. Issuer-namespaced; the issuer's BMP `target_id` MUST match (§5). |
| `item` | string | ✓ | Item slug within the collection, e.g. `"emberlong-sword"`. |
| `ed` | int | ✓ | Edition number, 1-based. |
| `of` | int | ✓ | Edition supply (total for this item slug). |
| `seed` | string | ✓ | Hex generation seed (≥ 3 bytes). Drives the procedural reveal (§6). |
| `tr` | object | ✓ | Traits: flat string→string map. Budget-disciplined (§3.1). |
| `mint` | string | ✓ | 64-hex txid of the mint transaction creating the ordinal. The piece's permanent identity. |
| `n` | int | – | vout of the ordinal within the mint tx. Default `0`; omit when 0. |
| `art` | string | ✓ | First 8 bytes (16 hex) of SHA-256 of the canonical render (§6). Pins the reveal. |

Example (215 bytes):

```json
{"art":"e64fc8981b2e5437","col":"grydbound-armory","ed":23,"item":"emberlong-sword","mint":"a91f3c2e7b04d5f6a91f3c2e7b04d5f6a91f3c2e7b04d5f6a91f3c2e7b04d5f6a9","of":500,"seed":"a91f3c","tr":{"blade":"molten"},"v":2}
```

### 3.1 The 227-byte budget

The certificate is carried as BMP envelope data (§5) inside one static frame: 227 bytes maximum. This is a normative constraint, not a guideline — a collectible that needs streaming mode to scan is a defect. Issuers keep within budget by: short slugs, short trait values, omitting `n` when zero, one-line traits. If a design cannot fit, split reveal data off-chain and reference it via `art`, not by enlarging the cert. (Worked example: the §3 certificate with a second trait `{"guard":"obsidian"}` is 234 bytes — over budget; dropping it to one trait yields 215 bytes. Budget discipline is enforced by measuring, never by eyeballing.)

## 4. Ownership model

### 4.1 Mint

The issuer creates the ordinal: a transaction paying 1 satoshi to an issuer-controlled address, with an `OP_FALSE OP_RETURN` output containing `SV2 ‖ SHA-256(certificate_bytes)`. The txid of this transaction becomes `mint`. Minting SHOULD happen before or at public reveal; until mint exists, a certificate is a promise, not a piece.

### 4.2 Claim

A collector claims a piece in a single on-chain event:

1. The collector's wallet signs a binding message: `SV2CLAIM ‖ SHA-256(cert) ‖ collector_pubkey_hash`.
2. The mint outpoint is spent to the collector's address (the ordinal moves), in a transaction carrying `OP_RETURN: SV2 ‖ SHA-256(cert)`.

The claim transaction is the public, timestamped, wallet-signed binding the collector's signature ceremony implies — and it is simultaneously the first transfer. Nothing else is required.

### 4.3 Transfer

Transfer is an **ordinary ordinal send**: the current holder spends the ordinal UTXO to the new holder's address. The certificate does not change; the identity does not change; no re-signing, no issuer involvement, no new key handling. Verifiers resolve current ownership by tracing the UTXO chain from `mint:n` forward.

### 4.4 Why no key handover

Designs that bind ownership to a private key embedded in (or derivable from) the image are unsound: the seller retains knowledge of the key after sale, forever. SV-0002 avoids the entire class: there is no item key, the image contains no secret, and ownership is a chain fact that only the current UTXO holder can move.

## 5. Envelope binding

The certificate rides a BMP-0000 envelope with:

| Envelope field | Value |
|---|---|
| `action` | `0xA47C` — COLLECTION ITEM CERT |
| `target_id` | 4-byte collection namespace (e.g. `0x4E465431` "NFT1", `0x47525944` "GRYD") |
| `pubkey` | the issuer's signing key |
| `message` | the canonical certificate bytes (§3) |
| `nonce` | issuer-chosen; RECOMMENDED: mint-block-approximate unix time |

`col` and `target_id` are the same namespace in two encodings; verifiers MUST reject mismatches between the envelope `target_id` and the issuer registry mapping for `col`.

## 6. Reveal mechanics

Scanning produces the certificate; rendering produces the item's appearance:

- `item` selects the generator (per collection; generators are deterministic, published, and versioned).
- `seed` parameterizes the generator: same `(item, seed)` MUST produce the same canonical render everywhere.
- `art` pins the canonical render's hash, so marketplaces and explorers can detect off-spec renders.
- `tr` is the human-readable trait summary; it MUST be derivable from `(item, seed)` and is duplicated in the cert for instant display without rendering.

The SV Code artwork itself MAY embed any per-cell tone art (picture-in-matrix, per the Night Districts series) — such artwork is presentation and MUST NOT be required for decoding or verification.

## 7. Cross-game recognition

**Recognition is unlimited; ownership is exclusive.** This is the rule that makes a sealed collection a game standard rather than a game asset.

### 7.1 Recognition is free

A certificate contains no game-specific code. Any game MAY honor any SV-0002 certificate by:

1. Decoding the SV Code and verifying the issuer signature (Scan tier, §8).
2. Resolving the current owner by tracing `mint:n` (Owner tier, §8).
3. Rendering the item in its own engine from `(item, seed)` and mapping traits (§7.2).

No permission from the issuer is required, in either direction. Adopting this specification as an **issuer** consists of: choosing a 4-byte `target_id` namespace, signing certificates with the studio key, and publishing item generators. Honoring **foreign** collections consists of the three steps above and nothing else.

### 7.2 Trait and stat normalization

Honoring games map foreign traits onto their own item classes. Consumers MUST ignore trait keys they do not implement (§10) — a `molten` blade may read as fire damage in one engine and be purely cosmetic in another. `art` pins only the **issuer's** canonical render; honoring games derive their own renders from `(item, seed)` and are not bound by `art`. Numeric stats carried in traits are advisory: each game's balance is sovereign over its own world.

### 7.3 Simultaneity is a feature

The same item may be active in every honoring game at once — utility is recognition, not consumption. When the ordinal transfers, every honoring game reflects the new owner on its next Owner-tier check; there is no per-game transfer ceremony. Games SHOULD re-resolve ownership on item use and MUST NOT cache ownership across sessions.

### 7.4 Optional activation lock (informative)

Economies that cannot tolerate simultaneous utility (yield-bearing items, consumables) MAY require an on-chain activation lock: the owner spends the ordinal back to themselves with `OP_RETURN: SV2L ‖ game target_id ‖ SHA-256(cert)`. Honoring games treat the item as inactive unless the latest lock record names them (unlock: same pattern with `target_id` zero). This extension is deliberately excluded from the core spec — it adds friction to every transfer, and most collections SHOULD NOT use it.

## 8. Verification tiers for collectibles

| Tier | Check | Answers |
|---|---|---|
| Scan | SV-0001 decode + BMP signature verify (L1) | "Is this a genuine issuer certificate?" |
| Anchor | SPV-verify `mint` tx exists; its OP_RETURN hash matches `SHA-256(cert)` (L2) | "Is this certificate anchored on-chain?" |
| Owner | Trace `mint:n` UTXO to its current holder (indexer or node) | "Who owns it right now?" |

A screenshot of a piece passes Scan and Anchor for the *original* — and fails Owner for the screenshotter. That asymmetry is the product.

## 9. Test vectors

Vector 1 (schema conformance; mint is a placeholder pending first real mint):

```
canonical cert (215 bytes):
{"art":"e64fc8981b2e5437","col":"grydbound-armory","ed":23,"item":"emberlong-sword","mint":"a91f3c2e7b04d5f6a91f3c2e7b04d5f6a91f3c2e7b04d5f6a91f3c2e7b04d5f6a9","of":500,"seed":"a91f3c","tr":{"blade":"molten"},"v":2}

SHA-256(cert)  = 43c8eb35b0c58e2888c603bcedee9924935aa1cccd5d335aded5e35edac59a25
budget check   = 215 ≤ 227  PASS
round-trip     = parse → re-serialize canonically → byte-identical  PASS
```

Implementations MUST round-trip: parse → re-serialize canonically → byte-identical.

## 10. Reserved

- The 104-bit Reserved tail of the SV-0001 frame remains zero for collection frames.
- Trait value `tr.lock` is RESERVED for future launch-enforcement flags; consumers MUST ignore unknown trait keys.
