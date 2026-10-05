# BMP-0002 — On-Chain Anchoring (L2): Envelopes in Fee-Paying Transactions

| | |
|---|---|
| **Number** | BMP-0002 |
| **Title** | On-Chain Anchoring — BMP Envelopes Embedded in BSV Transactions |
| **Status** | **Draft** |
| **Category** | Protocol Specification (Bitcoin Machine Protocol) |
| **Created** | 2026-10-05 |
| **Requires** | BMP-0000 |

## 1. Abstract

BMP-0000 §5 defines three verification tiers. This document specifies the **L2 tier** normatively: how a BMP envelope is embedded in a standard BSV transaction, what evidence travels with it, and what a receiver MUST verify — **fully offline** — before treating the command as fee-backed.

L2 answers the spam question L1 cannot: a signature proves *authority*, but costs nothing to produce. An L2 command commits a real transaction fee and, crucially, **specific UTXOs** — and the same outpoints cannot honestly back two different commands.

## 2. The offline-verifiability problem

A raw transaction alone does **not** prove fee payment to an offline receiver: input signatures can only be checked against the *value and script of the outputs being spent* (the sighash commits to them), and fabricated outpoints cost nothing to invent. Therefore the L2 message is not merely a raw transaction — it is a transaction **plus the evidence needed to validate it offline**:

```
L2_Message = Raw_TX ‖ Prevout_Evidence
Prevout_Evidence = for each input: (outpoint, value_satoshis, scriptPubKey)
```

`Prevout_Evidence` is a strict subset of a BEEF (BRC-62) payload: the spent outputs only, without merkle paths. (L3 extends this document with inclusion proofs via BEEF / Atomic BEEF — future work.)

## 3. Transaction shape

The L2 transaction MUST be a standard, broadcastable BSV transaction:

1. **Inputs:** one or more P2PKH inputs spending the *fee-payer's* UTXOs. (P2PKH only in this version; other templates may be added by later documents.)
2. **Data output (mandatory, exactly one):** value `0`, script:
   ```
   OP_FALSE OP_RETURN <push: "BMP1" ‖ envelope_bytes>
   ```
   `"BMP1"` (4 ASCII bytes) is the protocol marker. `envelope_bytes` is a complete BMP-0000 §4 envelope (85-byte header + payload). Push encoding follows standard rules (direct ≤75 B, `PUSHDATA1` ≤255 B, `PUSHDATA2` above).
3. **Change output(s):** optional, any standard form.
4. **Fee:** `sum(inputs) − sum(outputs)` MUST be > 0 and SHOULD be ≥ 250 satoshis (relay-grade at 0.25 sat/byte for typical sizes).

The **fee-payer** (who signs the inputs) and the **authority** (who signs the envelope) MAY be the same key or different keys. The envelope signature is what authenticates the command; the input signatures are what authenticate the payment. A deployment may therefore delegate fee payment without delegating command authority.

## 4. Transmitter procedure

1. Build/sign the envelope per BMP-0000 §4.3 (RFC 6979, low-s, compact `r‖s`).
2. Assemble the transaction per §3, sign each input `SIGHASH_ALL|FORKID (0x41)`.
3. Emit `L2_Message` (§2). The message MAY be transported by any BMP bearer (SV-0001 frames, BMP-BLE, QR, raw bytes) — or broadcast directly to the BSV network. Anchoring on-chain is RECOMMENDED but not required for L2 semantics: the evidence verifies offline either way.

## 5. Receiver validation (normative, in order)

Given `L2_Message` and the receiver's provisioned authority keys:

1. **Parse** the transaction completely; reject on any structural error. Locate the data output: first output whose script begins `OP_FALSE OP_RETURN` and whose first push begins `"BMP1"`. Exactly one such output MUST exist.
2. **Envelope:** extract `envelope_bytes`; parse per BMP-0000 §4; reject on version/length errors.
3. **Authority:** verify the envelope signature against the authority key for the addressed `Target_ID`. Reject on failure. *(Cheap ECDSA on 85+N bytes — do this before the input checks.)*
4. **Payment evidence:** for each input, locate its outpoint in `Prevout_Evidence` (reject if missing). Check the prevout script is P2PKH, and:
   - the scriptSig's pubkey hashes to the prevout script's hash160,
   - recompute the `SIGHASH_ALL|FORKID` digest over the actual transaction using the evidenced value+script, and verify the input signature.
5. **Fee:** `sum(evidenced input values) − sum(outputs) > 0`.
6. **Freshness (anti-reuse):** receivers persist every `(txid, outpoint)` they accept. A *new* transaction (different txid) spending any outpoint already accepted from a *different* transaction is a double-spend attempt: **reject**. The same txid seen again is an idempotent duplicate: safe to ignore.
7. Only after 1–6 pass: act on the envelope.

Steps 1–6 are pure offline computation. An L2 command that also appears on-chain (confirmed or mempool) additionally gains the network's own double-spend arbitration — that is an *upgrade* in assurance, not a requirement.

## 6. Security considerations

- **Why the evidence bundle is honest:** input signatures commit (via the forkid sighash) to the evidenced values and scripts. A forger cannot substitute fake prevouts without invalidating the signatures — and producing valid signatures requires the payer's private key, not just authority over the command.
- **What L2 does not prove offline:** that the evidenced UTXOs exist/existed unspent, and that the transaction was or will be mined. Offline L2 proves *capability and exclusive commitment*: the payer provably controlled those coins at signing time, and the freshness rule makes large-scale reuse self-defeating. Full existence/inclusion proof is L3 (SPV).
- **Freshness state** SHOULD be persistent across restarts; losing it degrades L2 to replayable evidence. Replays of the *same* command are additionally bounded by the envelope `Nonce` (BMP-0000 §8.2).
- **Fee-payer key custody** is a payment concern only; compromise of a fee-payer key never forges commands (the authority key is separate). Deployments SHOULD keep the authority key in an HSM/secure element and treat fee-payer keys as hot, low-balance operational keys.

## 7. Reference implementation and status

The PoC implements this document exactly:

- `poc/svcode/tx.py` — transaction build/parse/sign (`SIGHASH_ALL|FORKID`), verified against Bitcoin ABC consensus vectors.
- `poc/svcode/anchor.py` — `build_l2_tx`, `extract_envelope`, `verify_l2` implementing §3–§5.
- `poc/tests/test_anchor.py` — build/parse/extract/verify, tamper rejection (wrong authority, forged evidence, zero fee, double-spend freshness), and end-to-end signature chains.
- **Live mainnet proof:** an L2 command signed by the published test authority and paid by the PoC faucet key is broadcast and re-verified from the public ledger (txid recorded in `poc/vectors/l2_live.json`).

This spec remains **Draft** until a second independent implementation passes the same tests.

## 8. References

- BMP-0000 — umbrella protocol (envelope §4, content types §5, replay §8.2)
- BRC-62 (BEEF), BRC-95 (Atomic BEEF) — alignment for the evidence bundle; no conformance claimed
- Bitcoin ABC `sighash` specification — the `SIGHASH_ALL|FORKID` digest used by BSV
