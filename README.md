# SV Codes

**Machine-native visual codes that stream Bitcoin SV payloads to robots, scanners, and edge devices — no internet required.**

SV Code (Satoshi Vision Code) is a visual data-matrix protocol built for machines, not humans. Where QR codes were designed in 1994 for human scanners and print media, SV Codes are raw binary pixel grids with chromatic corner anchors, streamed as animated frames with rateless fountain-code recovery. A camera-equipped device points at a screen (or printed grid) and reconstructs a cryptographically signed payload — a command envelope, a BSV transaction, or a full SPV proof package — without Wi-Fi, cellular, Bluetooth, or any network stack.

**Live site:** <https://futureman19.github.io/sv-codes/>

- **[Transmitter + camera scanner](https://futureman19.github.io/sv-codes/)** — broadcast an SV Code from one screen, scan it with another device's camera
- **[/verify/](https://futureman19.github.io/sv-codes/verify/)** — verify a real anchored command layer-by-layer in your browser (signature → fee payment → merkle inclusion + PoW), including a fresh-from-chain mode
- **[/ble/](https://futureman19.github.io/sv-codes/ble/)** — BMP-BLE receiver demo (Web Bluetooth)
- **[/j/](https://futureman19.github.io/sv-codes/j/)** — sticker-campaign landing page: scan a sticker, get a micro-wallet, claim real sats

## The protocol underneath: BMP

SV Codes is the flagship product of the **[Bitcoin Machine Protocol (BMP)](https://github.com/futureman19/bmp)** — the open, transport-agnostic specification for Bitcoin-verified machine commands, now developed in its own repository:

| Layer | Spec | What it proves | Status |
|---|---|---|---|
| Envelope + tiers | [BMP-0000](https://github.com/futureman19/bmp/blob/main/spec/BMP-0000-bitcoin-machine-protocol.md) | Who sent it (ECDSA) | **Stable** |
| BLE transport | [BMP-0001](https://github.com/futureman19/bmp/blob/main/spec/BMP-0001-bmp-ble.md) | Radio last-mile, no pairing | **Stable** |
| On-chain anchoring | [BMP-0002](https://github.com/futureman19/bmp/blob/main/spec/BMP-0002-l2-on-chain-anchoring.md) | It paid a real fee (offline evidence) | **Stable** |
| SPV inclusion | [BMP-0003](https://github.com/futureman19/bmp/blob/main/spec/BMP-0003-l3-spv-inclusion.md) | The ledger keeps it (BEEF + BUMP + PoW) | **Stable** |

This repo holds the visual transport spec, **[SV-0001](spec/SV-0001-sv-code-visual-matrix.md)** (**Stable**), plus everything product-facing.

## Repository layout

```
spec/SV-0001  Visual matrix spec (grid geometry, fountain coding, receiver pipeline)
docs/         Project website (GitHub Pages): transmitter, scanner, /verify/, /ble/,
              /j/ sticker landing with in-browser micro-wallet
poc/          Reference implementation: encoder, scanner, golden vectors,
              campaign sticker generator (make_sticker.py + verify_sticker.py)
faucet/       Sticker-campaign faucet (FastAPI on fly.io): pays sats to landing-page
              wallets; dependency-free TX builder verified vs ABC consensus vectors
```

`poc/svcode/{envelope,crypto,stream}.py` are the envelope/framing core the visual
pipeline encodes; the canonical protocol implementations (anchoring, SPV, BLE)
live in the [bmp repo](https://github.com/futureman19/bmp).

## Why

- **Bitcoin transactions are transport-agnostic.** A signed payload is just bytes. It can travel by light, radio, sound, or a sheet of paper — and it remains cryptographically verifiable at the edge.
- **BSV scales to data.** Post-Genesis BSV carries large data payloads on-chain at sub-cent fees, so instructions, state, and proofs can live inside transactions instead of centralized APIs.
- **Machines shouldn't need cloud accounts.** A device that verifies a signature and an SPV proof locally is immune to server outages, API deprecation, and DDoS. Fees on-chain make spam economically irrational.

## Status

SV-0001 is **Stable**: two independent encoders (Python + browser JS) emit bit-identical frames, and two independent decoders pass the golden vectors — including decode under skew/noise/blur (13/13 roundtrip tests). The sticker campaign is live on mainnet: real claims paid by the faucet, verified on-chain.

Roadmap: svcode.org domain wiring → printed sticker field test → SV-0002 mono print profile → ESP32 beacon-rover (BMP-BLE actuator).

## License

Specifications are released under [Open BSV License](https://bitcoinassociation.net/open-bsv-license/) terms for protocol text; reference code under MIT. (Finalize before first public release.)
