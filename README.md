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
spec/     Protocol specifications (BMP-0000 + SV-0001 — Stable)
docs/     Project website (GitHub Pages): live transmitter + camera scanner;
          docs/j/ = sticker-campaign landing page with in-browser micro-wallet
poc/      Reference implementation: encoder, scanner, golden vectors,
          campaign sticker generator (make_sticker.py + verify_sticker.py)
faucet/   Sticker-campaign faucet (FastAPI on fly.io): pays sats to landing-page
          wallets; dependency-free TX builder verified vs ABC consensus vectors
```

**Live site:** <https://futureman19.github.io/sv-codes/> (includes a live in-browser SV Code transmitter implementing the SV-0001 draft wire format — verified against the spec's framing, fountain coding, and CRC32 checks).

## Specifications

| Document | Title | Status |
|---|---|---|
| [spec/BMP-0000](spec/BMP-0000-bitcoin-machine-protocol.md) | Bitcoin Machine Protocol — umbrella architecture, envelope schema, verification levels | **Stable** |
| [spec/SV-0001](spec/SV-0001-sv-code-visual-matrix.md) | SV Code Visual Matrix Protocol — grid geometry, fountain coding, receiver pipeline | **Stable** |
| [spec/BMP-0001](spec/BMP-0001-bmp-ble.md) | BMP-BLE — Bluetooth Low Energy connectionless transport | **Stable** |
| [spec/BMP-0002](spec/BMP-0002-l2-on-chain-anchoring.md) | On-Chain Anchoring (L2) — envelopes in fee-paying transactions, offline payment evidence | **Draft** |
| [spec/BMP-0003](spec/BMP-0003-l3-spv-inclusion.md) | SPV Inclusion (L3) — BEEF-packaged commands, BUMP merkle proofs vs local headers | **Draft** |

**Status labels:** *Draft* = proposed, not yet validated. *Stable* = two independent implementations (Python `poc/`, browser JS `docs/js/`) emit bit-identical frames and pass the golden test vectors in `poc/vectors/`. Where we align with existing BSV standards (BEEF / BRC-62, Atomic BEEF / BRC-95), that alignment is noted explicitly; no BRC conformance is claimed.

## Roadmap

1. **Protocol** ✓ — Umbrella spec + SV Code visual matrix spec.
2. **Website** ✓ — <https://futureman19.github.io/sv-codes/>, with a live in-browser SV Code transmitter implementing the draft wire format.
3. **PoC** ✓ — Python reference implementation (`poc/`): signed envelopes, fountain codec, OpenCV decoder, webcam scanner, and golden test vectors (`poc/vectors/`). 13 tests passing, including JS↔Python bit-exact encoder parity and decode under skew/noise/blur. Specs remain **Draft** pending a second independent decoder.

Later transports on the BMP registry (reserved, not yet specified): BLE advertising frames, dual-interface RFID (ST25DV), LoRa/shortwave radio.

## Naming

- **BMP** — Bitcoin Machine Protocol: the umbrella architecture (envelope, authority, verification, transport registry).
- **SV Code** — the visual matrix transport. Also reads naturally as *Sensor Vision* / *Spatial Vector* code.

## License

Specifications are released under [Open BSV License](https://bitcoinassociation.net/open-bsv-license/) terms for protocol text; reference code under MIT. (Finalize before first public release.)
