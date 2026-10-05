# BMP-0001 — BMP-BLE: Bluetooth Low Energy Transport for the Bitcoin Machine Protocol

| | |
|---|---|
| **Number** | BMP-0001 |
| **Title** | BMP-BLE — Bluetooth Low Energy Connectionless Transport |
| **Status** | **Stable** (two independent receivers — Python `poc/svcode/ble.py` and browser JS `docs/js/ble.js` — emit bit-identical fragments and pass the reference vectors in `poc/vectors/ble_vectors.json`) |
| **Category** | Transport Specification (Bitcoin Machine Protocol) |
| **Created** | 2026-10-05 |
| **Requires** | BMP-0000 |

## 1. Abstract

BMP-BLE carries BMP envelopes (BMP-0000 §4) over **connectionless Bluetooth Low Energy advertising**. Any BLE receiver in radio range — a robot, a phone, an ESP32 — can receive a signed command or transaction **without pairing, bonding, connecting, or any account**. Radio range substitutes for physical presence, which is exactly the condition under which BMP-0000 §4.3 permits signature-only (L1) verification.

This document defines framing, reassembly, and physical-layer detection only. It never alters envelope semantics (BMP-0000 §7).

## 2. Channel model

The transmitter is a BLE **non-connectable advertiser** (`ADV_NONCONN_IND`). Receivers are **observers** (passive or active scanning). There is no GATT service, no connection, no handshake: the transmitter cyclically broadcasts the complete fragment set, and receivers reconstruct the stream from whichever copies they hear.

This is the radio analog of SV-0001's any-order fountain property: duplicates are idempotent, losses self-heal on the next advertising cycle.

### 2.1 Why no BLE-level security

Pairing, bonding, and LE Secure Connections are **not used**. Justifications:

1. The payload is self-authenticating — the envelope's ECDSA signature is verified at the BMP layer regardless of bearer.
2. Connection-oriented security would break the zero-configuration broadcast model (one transmitter, unlimited anonymous receivers).
3. BLE link encryption would provide confidentiality only; BMP envelopes are not confidential by design (they are commands, not secrets). Deployments needing confidentiality encrypt `Payload_Data` at the application layer, above this spec.

### 2.2 Verification tiers

L1 (signature-only) is the natural tier for BMP-BLE: the adversary who can inject radio frames is physically present, and presence is the L1 substitution principle. L2/L3 envelopes (raw transaction / BEEF) travel identically — this spec is payload-type agnostic.

## 3. Advertising payload format

All BMP-BLE data rides in a **Manufacturer Specific Data** AD structure (AD type `0xFF`) with Company Identifier `0xFFFF` (reserved for internal/testing use). A deployment MAY register its own company ID; receivers MUST accept any company ID when the magic bytes match.

MSD payload layout (after the 2-byte company ID):

```
Bytes  Field        Size  Description
0-1    Magic        2     ASCII "SV" (0x53 0x56)
2      Stream_Seq   1     Generation counter, incremented each time the
                          transmitted stream CHANGES. Receivers MUST discard
                          fragments whose Stream_Seq differs from the set
                          they are currently assembling.
3      Frag_Index   1     Fragment number within the set (0-based)
4      Frag_Count   1     Total fragments in the set (1-255)
5..    Frag_Data    n     Stream fragment bytes (n = MTU for the profile)
```

The **stream** being fragmented is exactly the SV-0001 §3.1 stream framing:

```
uint32_BE Content_Length ‖ uint32_BE CRC32(content) ‖ content ‖ zero-pad
```

`content` is a BMP envelope (Content_Type `0x01`), a raw BSV transaction (`0x02`), or BEEF (`0x03`) per BMP-0000 §5. (The Content_Type travels inside the envelope/format layer; BMP-BLE itself is agnostic to it.)

### 3.1 Profiles and MTU

| Profile | Bearer | Frag_Data size (MTU) | Notes |
|---|---|---|---|
| **LE-Legacy** | 31-byte legacy advertising PDUs | **19 bytes** | Universal: every BLE device since 4.0 can receive. Full legacy adv payload = `Flags (3B) ‖ MSD header (4B) ‖ MSD data (24B)`. |
| **LE-Extended** | Bluetooth 5 extended advertising | **251 bytes** | Single-fragment delivery for streams ≤ 251 bytes (a bare envelope with up to ~158 payload bytes). |

Transmitters MUST advertise exactly one profile for a given stream. Receivers MUST implement LE-Legacy; LE-Extended is optional (requires BT5 controller support).

### 3.2 Legacy on-air reference layout (LE-Legacy, 31 bytes)

```
[0]    0x02        AD structure 1 length
[1]    0x01        AD type: Flags
[2]    0x06        LE General Discoverable, BR/EDR not supported
[3]    0x1B        AD structure 2 length (27 bytes follow)
[4]    0xFF        AD type: Manufacturer Specific Data
[5-6]  0xFF 0xFF   Company ID (little-endian on air: FF FF)
[7-8]  "S" "V"     magic
[9]    Stream_Seq
[10]   Frag_Index
[11]   Frag_Count
[12-30] Frag_Data (19 bytes, zero-padded on the final fragment)
```

## 4. Transmitter behavior

1. Build the stream (§3) from the content.
2. Fragment into `Frag_Count = ceil(len(stream)/MTU)` PDUs; zero-pad the final fragment's `Frag_Data` to MTU.
3. Assign/keep `Stream_Seq`: increment (mod 256) whenever the stream content changes.
4. Advertise the full set **cyclically**: fragments in rotating order (start index rotates each cycle to decorrelate burst loss), advertising interval 100–500 ms while actively commanding. Interval MAY be relaxed for battery after N minutes of an unchanged stream.
5. A transmitter SHOULD keep cycling the set for as long as it wants the command receivable; there is no acknowledgement at this layer.

## 5. Receiver behavior

1. Scan (observer role). Filter: AD type `0xFF`, magic `"SV"`, `0 < Frag_Count`, `Frag_Index < Frag_Count`, structure lengths self-consistent. Malformed fragments are **silently dropped**.
2. On first fragment of a `(Stream_Seq)` generation: start a set buffer. On `Stream_Seq` change: discard any incomplete previous generation and start fresh.
3. **Poisoned-generation rule (normative):** within a generation, a fragment whose `Frag_Count` or `Frag_Data` length disagrees with the generation's established values poisons the **entire** generation — the receiver MUST discard ALL buffered fragments of it, not merely the offending fragment. Rationale (adopted from BRC-130 §Reassembly): an inconsistent fragment implies two different objects sharing one `Stream_Seq` (e.g. transmitter restart with sequence reuse), and partial retention risks assembling an object no layer downstream is obligated to catch. The drop is self-healing: the buffer re-arms on the next fragment and the cyclic retransmission completes a later cycle.
4. **Duplicate fragments** (same index, consistent fields) MUST be silently ignored (overwrite semantics). Receivers hold exactly one generation buffer — `O(one stream)`, so no TTL eviction is required; a partial generation simply completes on whichever cycle delivers its missing fragments.
5. When all `Frag_Count` indices are present: concatenate `Frag_Data`, truncate to `8 + Content_Length` padded to 32 bytes per stream framing, and verify:
   - `Content_Length` sane (≤ 65535 + 85) and buffer long enough,
   - CRC32 over content matches,
   - **then** BMP-layer verification (BMP-0000 §4.3): signature check against provisioned authority keys before acting.
6. CRC or parse failure: discard the whole generation and wait for the next cycle — never attempt partial interpretation.
7. Receivers MUST tolerate duplicates, reordering, and arbitrary interleaving with other advertisers.

Integrity is checked cheaply (CRC32) before expensively (ECDSA), mirroring SV-0001 §6.

## 6. Parameters and performance (informative)

A bare envelope (85 bytes) frames to a 96-byte stream → **5 legacy fragments** (19-byte MTU). At a 200 ms interval cycling 5 PDUs, a receiver with a 50% duty-cycle scan reconstructs the command in well under 2 seconds. An envelope with 100 payload bytes (193-byte stream, padded 224) → 12 fragments. LE-Extended carries the bare-envelope stream in a **single** PDU.

Radio range is deployment-defined (BLE class 1 ≈ 50–100 m line of sight); the physical-presence assumption of L1 scales with transmit power, and authorities SHOULD size it to the machine's operating area.

## 7. Reference implementation and test vectors

The PoC (`poc/svcode/ble.py`) implements §3–§5 exactly and is exercised by `poc/tests/test_ble.py`:

- Roundtrip fragment/reassemble of a signed envelope (both profiles).
- Reassembly under 40% per-cycle fragment loss and random ordering, across multiple advertising cycles.
- Generation change mid-assembly (old fragments discarded).
- Malformed PDU rejection (bad magic, bad counts, truncated structures).
- **Poisoned-generation rule (§5.3):** inconsistent-count and inconsistent-length fragments each discard the entire buffered generation; stream self-heals on a later cycle (both implementations).
- Duplicate fragments are harmless (overwrite semantics).
- Exact on-air byte layout of §3.2 (pack + parse a full 31-byte legacy PDU).
- End-to-end: envelope → sign → stream → fragment → loss/shuffle cycles → reassemble → CRC32 → parse → signature verify.

This spec is **Stable** as of 2026-10-05: the JS receiver (`docs/js/ble.js`, driving the Web Bluetooth demo at `docs/ble/`) passes all of the above against the Python-generated vectors, with byte-identical fragment output.

## 8. References

- BMP-0000 — Bitcoin Machine Protocol (envelope, verification tiers, transport registry)
- SV-0001 — SV Code Visual Matrix (stream framing §3.1 reused verbatim)
- Bluetooth Core Specification v5.x, Vol 6 Part B (advertising PDUs), Vol 3 Part C §11 (AD structures)
