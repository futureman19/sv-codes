# BMP-0003 — SPV Inclusion Proof (L3): Anchored Commands with Merkle Evidence

| | |
|---|---|
| **Number** | BMP-0003 |
| **Title** | L3 — BEEF-Packaged Anchored Commands with SPV Inclusion Proof |
| **Status** | **Draft** |
| **Category** | Protocol Specification (Bitcoin Machine Protocol) |
| **Created** | 2026-10-05 |
| **Requires** | BMP-0000, BMP-0002 |

## 1. Abstract

BMP-0002 (L2) proves a command's fee was *committed* and its inputs *exclusively
assigned* — offline. What L2 cannot prove offline is that the evidenced UTXOs
ever existed or that the anchoring transaction entered the ledger. This document
specifies **L3**, which closes both gaps: the anchored command travels inside a
standard **BEEF** container ([BRC-62](https://bsv-blockchain.github.io/) /
[BRC-95] / [BRC-96]) whose ancestry carries **BUMP** merkle paths ([BRC-74]),
and the receiver verifies inclusion against locally held block headers — still
fully offline at verification time.

## 2. The L3 message

```
L3_Message = BEEF_object
```

where `BEEF_object` is a BRC-62 v1 (`0100BEEF`) stream — or a BRC-95 Atomic
BEEF or BRC-96 TXID-only equivalent — containing:

1. the **subject transaction**: the BMP-0002 anchored command TX (last in the
   container, per BRC-62 topological ordering), and
2. **ancestor transactions** covering every input of the subject, and
3. a **BUMP** for every included transaction that is mined (BRC-74).

When transported over BMP bearers, `Content_Type 0x03` (BMP-0000 §5) denotes a
BEEF payload. For wide-area distribution, the BRC-148/149 multicast BEEF plane
is the RECOMMENDED carrier (see `spec/notes/brc-148-149-alignment.md`); the
object is identical either way.

**Key property:** the prevout *evidence bundle* of BMP-0002 §2 needs no
separate encoding at L3 — it is **derived** by parsing the ancestor
transactions inside the BEEF.

## 3. Receiver validation (normative, in order)

Given an `L3_Message`, provisioned authority keys, the receiver's header store,
and its freshness log:

1. **Parse** the BEEF; reject on structural error. The subject is the last
   transaction.
2. **BMP-0002 validation of the subject.** For each subject input, locate the
   ancestor by outpoint in the BEEF (reject if absent); take the evidenced
   value and scriptPubKey from the ancestor's referenced output. Then apply
   BMP-0002 §5 steps 1–6 unchanged (parse, extract `"BMP1"` envelope, authority
   signature, per-input signature verification against evidenced prevouts,
   fee > 0, outpoint freshness).
3. **Merkle inclusion.** For every transaction carrying a BUMP:
   a. Locate its txid in BUMP level 0 (reject if absent).
   b. Compute the merkle root per BRC-74 (duplicate-flag handling included).
   c. Reject unless that root equals the `merkleRoot` field of a header in the
      receiver's store. The BUMP's `blockHeight` identifies the candidate
      header; the root equality is the proof (headers are indexed by root —
      BRC-62 §"Assumption").
4. **Header trust.** Every header used in step 3 MUST itself pass local
   validation: 80 bytes, proof-of-work (`SHA256d(header) ≤ target(bits)`), and
   linkage into the receiver's known chain. Headers arrive by any means —
   provisioning, occasional gateway sync, or broadcast over BMP transports as
   ordinary content.
5. **Burial depth (policy).** Receivers SHOULD require `tip_height −
   BUMP.blockHeight + 1 ≥ min_depth`; `min_depth = 1` for low-value commands,
   higher for physical actuation of consequence (local policy, BMP-0000 §8.4).
6. Only after 1–5 pass: act on the envelope.

**Script evaluation:** for the P2PKH-only template of BMP-0002 §3, step 2's
per-input signature + pubkey-hash checks *are* the script evaluation. Exotic
input templates would require a full script engine and are out of scope for
this document.

## 4. What L3 proves that L2 cannot

| Claim | L2 (offline) | L3 (offline at verify time) |
|---|---|---|
| Envelope authorized by authority | ✓ | ✓ |
| Inputs' values/scripts as evidenced | ✓ (signature-committed) | ✓ |
| Fee committed; outpoints exclusively assigned | ✓ | ✓ |
| **UTXOs actually existed** | — | ✓ (ancestors proven mined) |
| **Network double-spend arbitration** | — | ✓ (inclusion in longest chain) |

## 5. Security considerations

- **Header store is the trust root.** An attacker who can feed a machine a
  fraudulent header *chain* with valid PoW has spent real hash power; the
  chainwork comparison in the receiver's store is the defense. Machines SHOULD
  pin their tip provisioning to multiple independent sources.
- **L3 without headers degrades safely:** nothing verifies, the command waits
  — it never partially executes.
- **Freshness still applies:** L3 inclusion proves the spend happened; the
  BMP-0002 §5.6 log additionally prevents one anchored TX from being
  re-presented as *new* commands, and prevents conflicting anchored commands
  from both executing.
- **BEEF is evidence, not authority:** the BEEF wrapper authenticates
  *settlement*; the *command* is still only authenticated by the envelope
  signature. A perfectly valid BEEF carrying an envelope signed by a
  non-authority key MUST be rejected at step 2.

## 6. Reference implementation and status

The PoC implements this document exactly:

- `poc/svcode/spv.py` — BRC-74 BUMP parser/root walk, BRC-62 v1 parser, header
  PoW verification, and `verify_l3` (§3 pipeline).
- `poc/l3_live.py` — builds a BEEF around the live mainnet L2 command
  (`txid 4a6f612be1f8984ee13da679c1c5f7698f4d118304ca51ea98e895c4a977b3d1`,
  block 969795) from public ledger data and verifies it end-to-end.
- `poc/vectors/l3_live.json` — the frozen proof vector (BEEF, both block
  headers, heights, tip).
- `poc/tests/test_spv.py` — 9 tests: live-vector pass, BUMP/BEEF structure,
  real-header PoW, corrupt-BUMP / corrupt-header / missing-header / wrong-
  authority / insufficient-depth rejection, L3 freshness enforcement.

This spec remains **Draft** until a second independent implementation passes
the same tests.

## 7. References

- BMP-0000 §5 (tiers), BMP-0002 (L2 anchoring)
- BRC-62 (BEEF), BRC-95 (Atomic BEEF), BRC-96 (BEEF V2), BRC-74 (BUMP)
- BRC-148/149 + `spec/notes/brc-148-149-alignment.md` (wide-area carriage)
