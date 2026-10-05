# SV Codes

**Machine-native visual codes that stream Bitcoin SV transactions to robots, scanners, and edge devices — no internet required.**

SV Code (Satoshi Vision Code) is a visual data-matrix protocol built for machines, not humans. Where QR codes were designed in 1994 for human scanners and print media, SV Codes are raw binary pixel grids with chromatic corner anchors, streamed as animated frames with rateless fountain-code recovery. A camera-equipped device points at a screen (or printed grid) and reconstructs a cryptographically signed payload — a BSV transaction, a command envelope, or a full SPV proof package — without Wi-Fi, cellular, Bluetooth, or any network stack.

SV Code is the first transport of the **Bitcoin Machine Protocol (BMP)**, an open specification for using the BSV blockchain as an ambient, cryptographically verifiable instruction bus for autonomous machines.

## Why

- **Bitcoin transactions are transport-agnostic.** A signed transaction is just bytes. It can travel by radio, light, sound, magnetic ink, or a sheet of paper — and it remains cryptographically verifiable at the edge.
- **BSV scales to data.** Post-Genesis BSV carries large data payloads on-chain at sub-cent fees, so instructions, state, and proofs can live inside transactions instead of centralized APIs.
- **Machines shouldn't need cloud accounts.** A robot that verifies a signature and an SPV proof locally is immune to server outages, API deprecation, and DDoS. Fees on-chain make spam economically irrational.

## Repository layout

```
spec/     Protocol specifications (the product of Phase 1)
web/      Project website (Phase 2)
poc/      Reference implementation: SV Code encoder + scanner (Phase 3)
```

## Specifications

| Document | Title | Status |
|---|---|---|
| [spec/BMP-0000](spec/BMP-0000-bitcoin-machine-protocol.md) | Bitcoin Machine Protocol — umbrella architecture, envelope schema, verification levels | **Draft** |
| [spec/SV-0001](spec/SV-0001-sv-code-visual-matrix.md) | SV Code Visual Matrix Protocol — grid geometry, fountain coding, receiver pipeline | **Draft** |

**Status labels:** *Draft* = proposed, not yet validated by a reference implementation. *Stable* = validated by the PoC with published test vectors. Nothing here claims conformance to any BRC; where we align with existing BSV standards (BEEF / BRC-62, Atomic BEEF / BRC-95), that alignment is noted explicitly.

## Roadmap

1. **Protocol** ← you are here. Umbrella spec + SV Code visual matrix spec.
2. **Website** — public home for the specs, visual explainer, live encoder demo.
3. **PoC** — Python reference implementation: a transmitter that streams SV Codes on screen, and a receiver that decodes them from a webcam feed and verifies the payload signature. This graduates both specs from *Draft* to *Stable* and produces the test vectors.

Later transports on the BMP registry (reserved, not yet specified): BLE advertising frames, dual-interface RFID (ST25DV), LoRa/shortwave radio.

## Naming

- **BMP** — Bitcoin Machine Protocol: the umbrella architecture (envelope, authority, verification, transport registry).
- **SV Code** — the visual matrix transport. Also reads naturally as *Sensor Vision* / *Spatial Vector* code.

## License

Specifications are released under [Open BSV License](https://bitcoinassociation.net/open-bsv-license/) terms for protocol text; reference code under MIT. (Finalize before first public release.)
