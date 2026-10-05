# BMP-0000: Bitcoin Machine Protocol — Umbrella Architecture

| | |
|---|---|
| **Number** | BMP-0000 |
| **Title** | Bitcoin Machine Protocol — Architecture, Envelope, and Verification Model |
| **Status** | **Stable** (validated by two independent implementations — Python `poc/` + browser JS `docs/js/` — against published test vectors) |
| **Category** | Protocol Specification |
| **Created** | 2026-10-05 |
| **Requires** | None (root document) |

---

## 1. Abstract

The Bitcoin Machine Protocol (BMP) defines how cryptographically signed instructions are delivered to, verified by, and acted upon by autonomous machines, using the Bitcoin SV (BSV) blockchain as the trust and settlement layer — without requiring the machine to maintain an internet connection.

BMP separates three concerns:

1. **The Envelope** — a compact binary command format, signed by an authority key.
2. **Verification** — a tiered model from offline signature-checking to full SPV (Simplified Payment Verification) proof.
3. **Transports** — pluggable physical bearers (visual matrices, BLE, RFID, radio) that carry envelopes or full transactions to the machine.

This document specifies the envelope, the authority model, and the verification tiers. Each transport is specified in its own numbered document (see §7).

## 2. Motivation

Conventional machine control relies on centralized servers and IP networking. This creates single points of failure, recurring costs, and remote attack surfaces. BSV transactions are transport-agnostic signed byte strings; post-Genesis BSV carries large data payloads in `OP_FALSE OP_RETURN` outputs at sub-cent fees. A machine that can receive bytes over *any* physical medium and verify them locally gains:

- **Sovereignty** — no cloud account, SIM subscription, or API key required to receive orders.
- **Censorship resistance** — no central server to shut down; instructions can arrive over ambient radio, light, or physical contact.
- **An economic firewall** — when instructions are anchored on-chain (tiers L2/L3, §5), every command costs the sender a real network fee, making spam and command-flooding economically irrational.

## 3. Architecture

```
[ Authority ]                [ Transport ]              [ Machine ]
 (key holder)  ── envelope ─▶  (SV Code, BLE,  ── bytes ─▶  (edge agent:
  signs with   ── or full TX ─▶   RFID, radio)               verify → evaluate
  secp256k1)                                                  → actuate)
```

- **Authority**: any entity holding a secp256k1 private key registered to one or more `Target_ID`s (§4.2).
- **Transport**: a BMP-numbered bearer spec. Transports move bytes; they do not interpret them.
- **Machine**: an edge device running an agent harness that (a) receives bytes from a transport, (b) verifies per §5, (c) evaluates the instruction against local policy (battery, capability, bounty value), and (d) actuates.

Real-time control (motor balance at ≥1 kHz) is always local. BMP carries *macro-level intent*, never servo loops.

## 4. The BMP Envelope

### 4.1 Binary layout

All multi-byte integers are **big-endian**. Fixed header: 85 bytes.

| Offset | Size | Field | Description |
|---|---|---|---|
| `0x00` | 1 | `Version` | Envelope version. `0x01` in this document. |
| `0x01` | 4 | `Target_ID` | 32-bit identifier of the target machine or swarm topic. |
| `0x05` | 2 | `Action_Code` | Opcode defining the instruction class (§6). |
| `0x07` | 8 | `Params` | Action-specific fixed parameters (e.g., packed fixed-point X,Y). Interpretation is defined per Action_Code. |
| `0x0F` | 4 | `Nonce` | UNIX timestamp (seconds) in timestamp mode, or a strictly increasing counter in counter mode (§8.2). |
| `0x13` | 2 | `Payload_Length` | Length in bytes of `Payload_Data` (`uint16`; 0–65535). |
| `0x15` | 64 | `Signature` | ECDSA/secp256k1 compact signature `r ‖ s` over the digest in §4.3. |
| `0x55` | *n* | `Payload_Data` | Arbitrary instruction payload, exactly `Payload_Length` bytes. |

### 4.2 Authority model

Each `Target_ID` is bound to exactly one authority public key at any time. The binding is established:

- **Provisioning (current draft):** out-of-band, written to the machine's secure element at manufacture/deployment.
- **On-chain registry (future work):** a numbered BMP document will define an on-chain `Target_ID → pubkey` registry with key rotation. Until that document exists, rotation is out-of-band only.

A machine MUST reject any envelope whose signature does not verify against the authority key bound to the addressed `Target_ID`, and any envelope addressed to a `Target_ID` it does not own or subscribe to.

### 4.3 Signing and verification

```
digest    = SHA-256( Version ‖ Target_ID ‖ Action_Code ‖ Params
                     ‖ Nonce ‖ Payload_Length ‖ Payload_Data )
Signature = ECDSA-sign_secp256k1( authority_private_key, digest )
```

- Signature encoding: 64-byte compact `r ‖ s` (no DER, no recovery byte). Low-`s` normalized.
- Verification: standard ECDSA/secp256k1 verify of `Signature` against `digest` and the authority public key.
- Rationale: a single SHA-256 over the canonical serialization is sufficient because the fields are fixed-layout and unambiguous; no prefix/anti-malleability scheme is required at this layer. (On-chain anchoring provides its own signatures at tiers L2/L3.)

## 5. Verification tiers

A machine implements the highest tier its hardware allows, and MAY accept lower tiers per local policy. **L1 is the minimum bar for executing any physical action.**

| Tier | What is received | What is verified | Connectivity needed |
|---|---|---|---|
| **L1** | BMP Envelope | §4.3 signature against known authority key | None (fully offline) |
| **L2** | Raw BSV transaction containing the envelope in an `OP_FALSE OP_RETURN` output | Envelope signature **and** transaction structural validity (parses, inputs signed, envelope present) | None to *receive*; settlement checking deferred |
| **L3** | Transaction packaged with SPV evidence — BEEF (BRC-62) or Atomic BEEF (BRC-95), with BUMP merkle paths | Envelope signature, transaction validity, **and** merkle inclusion proof against locally held block headers | None to verify; headers obtained occasionally by any means |

**Alignment note:** BEEF/Atomic BEEF/BUMP references indicate *format alignment* with the named BSV standards, not a conformance claim. Canonical text: <https://bsv.brc.dev/>. If a conflict exists between this document and those standards, the standards win for tiers L2/L3.

**Design rule:** L1 is only acceptable over physically-local transports (visual, RFID/NFC, contact) where physical presence substitutes for the economic firewall. Broadcast transports (radio) SHOULD require L2+ so that flooding the frequency costs the attacker real fees.

## 6. Action_Code registry (core range)

`Action_Code` is a big-endian `uint16`. Codes `0x0000–0x00FF` are reserved for BMP core. Vendor-specific codes use `0x0100–0xFFFF`; their `Params`/`Payload_Data` semantics are vendor-defined.

| Code | Mnemonic | Params (8 bytes) | Payload_Data |
|---|---|---|---|
| `0x0000` | `NOP` | ignored | Presence/keep-alive; no action |
| `0x0001` | `HALT` | ignored | Stop all motion immediately |
| `0x0002` | `REPORT_STATUS` | ignored | Signed telemetry blob to log/return |
| `0x00A1` | `MOVE_TO` | two int32 fixed-point coords (X,Y), scale 10⁻⁶ | Optional path constraints |
| `0x00A2` | `MOVE_VECTOR` | int32 heading (millideg), int32 distance (mm) | Optional constraints |
| `0x00B1` | `CLAIM_BOUNTY` | uint64 bounty TX hint / outpoint prefix | Proof-of-work bundle per bounty terms |
| `0x00C1` | `SET_CONFIG` | uint32 config key, int32 value | Optional extended config |

Machines MUST ignore unknown core codes and MUST treat unknown vendor codes as opaque unless provisioned for them.

## 7. Transport registry

Each transport gets its own BMP-numbered specification. A transport spec defines framing, reassembly, and physical-layer detection only — it never alters envelope semantics.

| Transport spec | Bearer | Status |
|---|---|---|
| **SV-0001** | SV Code visual matrix (camera-readable animated binary grids) | **Draft** (companion document) |
| BMP-BLE *(reserved)* | Bluetooth Low Energy connectionless advertising | Not yet specified |
| BMP-RFID *(reserved)* | Dual-interface RFID (ST25DV-class) shared-memory tags | Not yet specified |
| BMP-LoRa *(reserved)* | LoRa / shortwave radio broadcast | Not yet specified |

## 8. Security considerations

### 8.1 Signature authority is everything

The envelope's security reduces to custody of the authority key. Authorities SHOULD use hardware security modules; machines SHOULD store authority public keys in secure elements (e.g., ATECC608-class).

### 8.2 Replay protection

- **Timestamp mode (default):** `Nonce` is UNIX seconds. Receivers reject envelopes with `|now − Nonce| > 300 s`, and reject reuse of a `Nonce` value already seen from the same authority within the window (cache ≥ last 1000 nonces per authority).
- **Counter mode (clock-less machines):** `Nonce` is a strictly monotonically increasing counter per authority. Receivers persist the highest accepted counter and reject anything ≤ it. The mode is chosen at provisioning and is per-`Target_ID`.

### 8.3 Economic firewall limits

The on-chain fee firewall (§2) only applies at tiers L2/L3. A raw L1 frame costs the sender nothing; therefore L1 MUST NOT be accepted from transports with long range or multi-hop propagation. Local policy SHOULD additionally rate-limit L1 actions.

### 8.4 Local policy is mandatory

Cryptographic validity is not a safety decision. Machines MUST apply local policy before actuation: battery floor, geofence, capability check, bounty-value-vs-energy evaluation, and an always-local `HALT` path that no envelope can disable.

### 8.5 Privacy

Envelopes addressed to a swarm `Target_ID` are readable by every subscriber of that transport. Payload confidentiality, where required, is achieved by encrypting `Payload_Data` to the target's public key (encryption profile: future BMP document); the fixed header remains plaintext for routing.

## 9. Extensibility

- New transports: new numbered BMP documents; registry row added here.
- New action codes: vendor range freely; core range only via revision of this document.
- New envelope versions: bump `Version`; parsers MUST reject unknown versions.

## 10. References

- BSV Blockchain BRC corpus — <https://bsv.brc.dev/> (BEEF: BRC-62; Atomic BEEF: BRC-95; BUMP merkle format)
- Bitcoin SV Protocol documentation — `OP_FALSE OP_RETURN` data carrier outputs
- SV-0001: SV Code Visual Matrix Protocol (companion, this repository)
- Luby, M. "LT Codes" (2002) — fountain coding used by SV-0001
