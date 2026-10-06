# SV-0004: Fixed-Price Atomic Sales

| | |
|---|---|
| **Number** | SV-0004 |
| **Title** | Fixed-Price Atomic Sales for Sealed Collectibles |
| **Status** | **Draft — implementation and wallet acceptance pending** |
| **Category** | Application Specification (Bitcoin Machine Protocol) |
| **Requires** | SV-0002; supported BSV covenant and BRC-100 wallet |

## 1. Scope

A seller offers one SV-0002 collectible at a fixed integer-satoshi price. A buyer-authorized transaction pays the seller and transfers the collectible atomically. SV Codes never receives wallet private keys or holds users' funding balances. Version one targets the current OrdLockV2 covenant template and one tested wallet integration, not arbitrary scripts, auctions, royalties, partial fills, or cross-chain exchanges.

This draft does not authorize spending an existing demo collectible or enable public paid checkout. The publicly documented SV-GENESIS issuer key is unsuitable for paid production issuance. A production collection requires a distinct private issuer key and registered identity. Existing demo certificates remain explicitly demo artifacts; changing the issuer does not retroactively secure them.

## 2. Identity and ownership

The certificate identifies an origin `mint:n` (default `n=0`). Current and listing output indexes may differ from the mint output index. A listing concerns a independently resolved current outpoint descending from that origin, not an address balance, copied artwork, signature badge, or unverified owner field.

SV-GENESIS mints are one-satoshi P2PKH outputs with a separate SV2 certificate-hash anchor. Their existence alone does not establish compatibility with third-party inscription marketplaces or indexers. SV Codes MUST verify its own origin and transfer lineage instead of treating an inscription search result as authoritative.

The listing pointer is public metadata. Publishing or copying it conveys no ownership and gives no permission to use a wallet. An off-chain seller signature alone is not proof of a valid on-chain sale lock.

## 3. Transaction invariants

### 3.1 Listing transaction

- One explicitly identified input spends the verified current collectible output, exactly one satoshi. Its ordinal satoshi offset must be preserved.
- Other inputs are seller-authorized ordinary funding outputs; exclude other collectibles.
- The advertised listing output carries exactly one satoshi in the supported sale covenant, at the same cumulative satoshi offset as the collectible input.
- The covenant fixes the exact seller payout script and price, with a separately identified cancellation authority.
- Remaining outputs contain only explicitly reviewed funding change or supported metadata.

The buyer-facing listing MUST bind origin, current outpoint, listing outpoint, exact canonical covenant bytes, integer price, payout destination, and cancellation identity. A decoded cancellation key MUST NOT be confused with the payout recipient.

### 3.2 Purchase transaction

- Ordinary front funding precedes the exact listing input, as required by the supported OrdLockV2 purchase planner.
- The covenant-enforced seller payout appears at the same output index as the listing input index, at the exact advertised price and script.
- The buyer receives a separate exactly-one-satoshi output after the required cushion/payout outputs. Verify cumulative satoshi offsets, not a fixed input-zero/output-zero assumption.
- Further inputs are buyer-authorized ordinary funding outputs; change and fees are explicit and bounded.
- The completed transaction satisfies `sum(inputs) = sum(outputs) + fee` and passes script verification for the sale input and all funding inputs.

No intermediate transaction may pay the seller without also delivering the collectible. A transaction that merely pays a seller address somewhere is insufficient evidence of a purchase.

Do not use a naive input-0 `SIGHASH_SINGLE` offer that binds payout at output 0: doing so routes the collectible's first satoshi to the seller payment instead of the buyer. Current OrdLockV2 deliberately places front funding before the asset and enforces same-index payout. The application MUST prove that the asset satoshi maps exactly to the buyer's one-satoshi output under that layout. Never restore the disabled legacy V1 listing constructor or downgrade dependencies to avoid this check.

For listing input index `i`, compute `asset_offset = sum(previous_output_satoshis(inputs[0:i]))`. For proposed buyer output index `j`, require `sum(output_satoshis(outputs[0:j])) == asset_offset` and `outputs[j].satoshis == 1`. Use exact integer arithmetic and resolve every preceding prevout. The asset must not fall into a seller payout, change, or transaction fee. Apply this same rule to each lineage hop; output indexes are not identity.

### 3.3 Cancellation

Cancellation spends the listing UTXO using the covenant's cancellation authority and returns the collectible at output 0 to the seller-approved holding script. It does not require a buyer. A purchase and cancellation race for the same output; only one can be accepted. UI state must follow independently verified chain state rather than a local cancelled flag.

## 4. Listing verification and freshness

Before displaying an actionable listing, independently resolve and verify:

1. Strictly formatted outpoints, raw transaction bytes, and locally computed txids.
2. The advertised origin's final signed certificate and zeroed-mint SV2 anchor.
3. Each supported lineage hop from origin to current outpoint.
4. The listing spends that current outpoint and its advertised output has the exact supported OrdLockV2 covenant and one-satoshi value, with exact satoshi-offset preservation. The simple listing constructor may use input0/output0, but purchase ancestry MUST support the validated V2 layout.
5. Decoded and re-encoded covenant bytes match exactly; reject embedded, extended, truncated, or merely pattern-matching scripts.
6. Price, payout script, cancellation authority, and displayed item all match the frozen review data.
7. The listing is unspent in both confirmed and relevant mempool state.

Unknown, timeout, malformed upstream response, not-yet-indexed, and confirmed spent are distinct results. None of the first four is proof that an output is unspent. Do not publish an actionable listing or call a wallet on uncertain evidence.

Snapshot source transaction/BEEF bytes before approval and bind the wallet preparation to those exact bytes. Recheck live spend state immediately before signing; acknowledge that a chain race can still occur afterward. Discovery indexes and listing mirrors are caches, not settlement authorities.

## 5. Wallet contract

Initial integration targets the current Yours-injected BRC-100 `window.CWI` interface, subject to installed SDK/API verification. Extension presence is not account authorization. Authentication, preparation, signing, and broadcast require explicit user interaction at their respective boundaries.

Preparation defaults to unsigned/not-processed/not-sent. All required front-funding source transactions must already exist and be explicitly supplied. The current actions package may broadcast a separate funding transaction before its final purchase step; therefore it MUST NOT be invoked inside the no-send preparation path. A missing suitable funding input is a capability failure, not permission to create a preparatory payment. Validate returned transaction ordering, inputs, scripts, price, fee, and change before allowing any signature or processing step. If the wallet reorders outputs or cannot express the reviewed covenant spend, abort; do not silently downgrade to a payment-only transaction or use deprecated wallet methods.

Never request a WIF, mnemonic, or private key from a collector. The identity key, cancellation authority, collectible holding key, and funding key are separate domains unless the wallet explicitly proves a documented relationship.

## 6. UX and failure behavior

Scan reveals the item card. A verified listing may add a price and Buy control; an absent listing remains an item viewer. Unknown issuers and public-demo collections cannot enter production paid checkout. Show unavailable, stale, pending wallet approval, cancelled, rejected, and broadcast outcome unknown distinctly.

Freeze the reviewed offer while the wallet dialog is open. Prevent double submission. An ambiguous broadcast is reconciled using its original locally calculated txid; never automatically rebuild and resend a payment. A returned txid is not by itself proof of the intended trade or confirmation.

## 7. Verification gates

- Actual script-interpreter execution for listing spend, atomic purchase, and seller cancellation using explicitly synthetic vectors.
- Negative vectors for wrong price, payout, cancellation authority, item/origin, tampered covenant, output ordering, malformed outpoints, spent/unknown state, and duplicate submission.
- Read-only production probes of the exact upstream paths and response schemas used by chain verification.
- BRC-100 preparation-boundary integration with exact frozen transaction evidence and explicit no-send behavior; distinguish mocked wallet testing from a real extension test.
- One separately authorized, bounded funded-wallet trade, with before/after ownership and complete output verification, before claiming a live end-to-end purchase.
- All seven existing JS harnesses rerun after any changes under docs/js. Paid UI must remain disabled until production issuance and funded wallet gates are satisfied.

Synthetic transactions are not chain receipts. Interpreter success is not wallet interoperability. Wallet preparation is not a funded trade. Each gate must be reported separately.
