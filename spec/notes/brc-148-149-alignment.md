# Alignment Note — BMP × lightwebinc/bsv-multicast (BRC-124..149)

*Working note, 2026-10-05. Not a normative spec. Analyzes Jeff Harris's
(Lightweb Inc., @LightBSV) BSV Layered Multicast stack — 17 BRCs merged in
[bsv-blockchain/BRCs](https://github.com/bsv-blockchain/BRCs) — and how the
Bitcoin Machine Protocol relates to it.*

## 1. The two systems in one paragraph each

**bsv-multicast** is a wide-area, operator-run distribution fabric: stateless
ingress proxies deterministically shard transactions by txid onto IPv6
multicast groups (BRC-129 addressing); listeners subscribe to shards and
subtrees; retry endpoints cache frames and repair gaps via NACKs (BRC-126);
large objects fragment/reassemble with hash-verified grids (BRC-130); blocks,
subtrees, headers, and anchor transactions get their own lanes; and the
16-bit shard space is partitioned into **object planes** (BRC-148) — domain
`0x0` = settlement (miner TX delivery, unchanged), domain `0x1` = **BEEF
plane** sharded by *overlay topic*, carrying BRC-62/95/96 objects in a
BRC-149 frame. Business model: sending is free, receivers subscribe (1bsv.net).

**BMP** is a machine-facing command protocol: a signed 85-byte-header envelope
(BMP-0000), transported over *infrastructure-free* physical bearers — animated
visual matrices (SV-0001) and connectionless BLE advertising (BMP-0001) — with
verification tiers L1 (signature, offline) → L2 (envelope anchored in a
fee-paying TX + prevout evidence, offline-verifiable, BMP-0002) → L3 (TX +
BEEF/SPV inclusion proof against locally held headers).

**Same insight, opposite ends of the wire:** send once, receive many, with
Bitcoin-native proof. His fabric replaces point-to-point fan-out *between
datacenters*; BMP replaces it *in the physical world*. Neither does the
other's job.

## 2. Layer mapping

| Layer | bsv-multicast | BMP |
|---|---|---|
| Object | raw/EF TXs, subtrees, blocks, BEEF | signed command envelopes (→ anchored TXs) |
| Wide-area transport | IPv6 multicast planes (BRC-129/148) | *(none — out of scope by design)* |
| Last-mile transport | unicast push to subscriber edges | SV-0001 light, BMP-BLE radio — no network at all |
| Loss recovery | NACK + cached re-multicast (BRC-126) | cyclic retransmission + fountain (no back-channel exists) |
| Addressing/filter | shard by txid; BEEF plane by topic hash | `Target_ID` field; receiver-side filtering |
| Proof carried | BEEF objects (BRC-62/95/96, BRC-74 BUMPs) | L2: prevout evidence (BEEF subset); L3: BEEF |
| Economics | receiver pays subscription; sends free | sender pays on-chain fee (spam firewall) |
| Authorization | miner-tier PoW gate for settlement lanes | ECDSA authority signature on every envelope |

## 3. The core fit: L2/L3 evidence *is* BEEF, and BEEF already has a plane

- BMP-0002's `L2_Message = Raw_TX ‖ Prevout_Evidence` is a strict **subset of
  a BRC-62 BEEF payload** (the spent outputs, without merkle paths).
- **L3 is precisely a BEEF object**: the anchored TX + its BRC-74 BUMP once
  mined — carried as BRC-62 (full ancestry), BRC-95 (atomic), or BRC-96
  (TXID-only). All three encodings are exactly what BRC-149's object frame
  transports, with the version word readable at a fixed offset.
- Therefore a BMP command, once anchored per BMP-0002 and mined, is a
  first-class citizen of his BEEF plane with **zero format changes on our
  side**. The wide-area distribution problem BMP deliberately does not solve
  is the problem his fabric exists to solve.

## 4. Proposed topic scheme (when a BMP gateway joins the BEEF plane)

BRC-148 shards the BEEF plane by `TopicID = SHA-256(topic name)`. Proposed
convention:

- `tm_bmp` — all BMP-anchored commands (firehose for gateways serving many targets)
- `tm_bmp_<target_id_hex>` — per-target channel; a gateway serving one machine
  or fleet subscribes only here, and **the fabric itself does the filtering**
  our receivers currently do alone

This is the elegant part: topic-sharding means a gateway's bandwidth tracks
its machines' traffic, not the network's — the same property his design gives
overlay hosts.

## 5. End-to-end path (wide-area command, fully verified at the machine)

```
authority ──signs envelope──▶ anchor TX (BMP-0002) ──broadcast──▶ mined
                                                                   │
                                           BEEF object (TX + BUMP) │
                                                                   ▼
                              BRC-149 submission record, topic tm_bmp_<target>
                                                                   │
                              multicast BEEF plane (domain 0x1) ◀──┘
                                   │  send once, worldwide
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
        gateway A            gateway B             gateway C
        (shard-listener      (…any subscribed       (…)
         + BMP transmitter)   gateway)
              │
              ▼  last mile, no internet required
        SV-0001 visual broadcast / BMP-BLE cyclic advertising
              │
              ▼
        machine: L1 envelope sig → L2 evidence (offline) →
                 L3 BUMP vs locally held headers (offline) → local policy → act
```

The machine never touches the internet. Every cryptographic check it performs
is offline; the BEEF object that traveled the fabric is the same byte string
it verifies at the edge.

## 6. Economics — two gates, two layers, no conflict

- **Sender gate (BMP):** the anchored command costs a real on-chain fee and
  commits specific outpoints (BMP-0002 freshness). Flooding the *physical*
  frequency costs the attacker money — this is BMP-0000 §8.3's firewall.
- **Receiver gate (his fabric):** delivery certainty is a paid subscription;
  sends are free at the network layer.
- They compose cleanly: the on-chain fee pays for *existence/settlement*;
  the subscription pays for *delivery*. A BMP deployment that wants wide-area
  reach subscribes its gateways; one operating purely locally (visual/BLE
  only) never touches his network at all.

## 7. What we borrow from BRC-126 / BRC-130

Reviewed in depth; concrete takeaways for BMP transports:

1. **Per-object content hash on every fragment (BRC-130).** Their fragments
   carry `ContentID = SHA256d(payload)` so receivers detect mixed/corrupt
   reassembly *before* decode. BMP-BLE already carries stream
   seq + generation (equivalent mixing protection); SV-0001 fountain symbols
   self-verify via the frame CRC32 + envelope signature. **Adopt:** state
   explicitly in BMP-0001 that receivers MUST drop fragments whose implied
   stream identity disagrees — already true, worth making normative.
2. **Implied-grid consistency rule (BRC-130 §Reassembly step 2).** All
   fragments of one object must imply the same fragment size and total;
   inconsistency → drop the whole object and count it, because "with hash
   verification optional, nothing downstream would catch it." **Adopt for
   BMP-BLE reassembly:** reject a fragment set whose `count`/padding math
   disagrees across fragments. Small receiver-hardening addition; test it.
3. **Receiver bookkeeping discipline:** slot caps, TTL eviction, silent-drop
   rules for malformed units, duplicate suppression by (id, index). Our
   reassemblers should document the same four behaviors (partially implicit
   today).
4. **Where a back-channel exists, NACK beats fountain.** His NACK+cache design
   is right for two-way IP; our cyclic retransmission/fountain is right for
   one-way light and advertising. The designs are consistent with each other —
   the medium dictates the recovery scheme. No change, but worth stating in
   BMP-0000's rationale.
5. **THROTTLED as an honest congestion signal (BRC-126).** If future BMP-BLE
   gateways coordinate (e.g., many transmitters one room), an honest
   "back off" beacon is the pattern to copy. Future work, not needed now.
6. **ADVERT beacons / tier+preference (BRC-126).** If BMP ever grows repair
   or rebroadcast gateways ("hear a stream, re-emit it"), beacon-based
   discovery with explicit TTL = 3× interval is the proven shape. Noted for
   BMP-LoRa/future radio docs.

## 8. Boundaries — what stays whose

**His:** wide-area transport, shard/topic addressing, retransmission
infrastructure, settlement-lane gating, the BEEF object plane.
**Ours:** command semantics (envelope, action codes, target binding), the
authority model, offline verification tiers, physical transports, machine
local policy (BMP-0000 §8.4).
**Shared surface:** the BEEF object is the hand-off. Both sides already speak
BRC-62/95/96 + BRC-74 — deliberately.

## 9. Adoption path

1. Nothing to change now: BMP-0002 is transport-agnostic; the evidence bundle
   is already a BEEF subset.
2. **BMP-0003 (future L3 doc):** adopt BRC-62/95 + BRC-74 verbatim for the
   proof package; reference BRC-149 as the RECOMMENDED wide-area carrier.
3. When 1bsv.net (or any BRC-148/149 fabric) is publicly subscribable: build
   a reference **BMP gateway** = shard-listener subscribed to
   `tm_bmp_<target>` topics + BMP-BLE/SV-0001 transmitter. That gateway is
   also the natural home of the HTLC bounty layer.
4. Optional, later: propose BMP-0000/SV-0001/BMP-0001/BMP-0002 as BRCs. His
   17 merged BRCs are proof the pipeline accepts exactly this kind of
   spec-first, implementation-backed work — and he is the obvious person to
   learn the process from (or approach directly; see session notes).

## 10. Honest deltas (so nobody over-reads the fit)

- His BEEF plane is a **live feed** — no history bootstrap; a machine joining
  a topic catches up via existing overlay sync. Offline-only machines that
  never sync headers still top out at L2. That is fine and by design.
- His fabric requires operator-run IPv6 multicast reachability; BMP's
  transports require nothing. Local-only deployments never depend on him.
- Topic naming is ours to propose; nothing in BRC-148/149 reserves `tm_bmp*`.
  If we ever publish on that plane, the convention above needs one line in a
  future BMP doc, not anyone's permission.

## References

- Repo: <https://github.com/lightwebinc/bsv-multicast> (DESIGN.md is the map)
- Canonical BRCs: 124 (frame), 126 (retransmission), 129 (addressing),
  130 (fragmentation), 139 (manifest), 148 (planes/BEEF), 149 (BEEF frame)
- Commercial service: <https://1bsv.net/guide.html>
- BMP side: spec/BMP-0000 §5 (tiers), spec/BMP-0002 (L2 evidence)
