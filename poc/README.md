# SV Code Reference Implementation (PoC)

Python reference implementation of **SV-0001** (visual matrix) and **BMP-0000** (envelope + signatures). This is the code that graduated the specs' wire format from paper to proven.

## Quickstart

```bash
uv venv --python 3.12 .venv          # or: python -m venv .venv
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
.venv/Scripts/python.exe -m pytest tests/ -q     # 13 passing
```

## What's here

| Path | Purpose |
|---|---|
| `svcode/envelope.py` | BMP envelope: 85-byte header, secp256k1 sign/verify (RFC 6979 deterministic, low-s) |
| `svcode/stream.py` | Stream framing: length + CRC32 + 256-bit symbol padding |
| `svcode/fountain.py` | Luby Transform codec: Robust Soliton, SHA-256 counter-mode PRNG, GF(2) decoder |
| `svcode/frame.py` | 2,704-bit payload matrix packing (seed / content-type / K / symbols) |
| `svcode/render.py` | Bits → grid image with chromatic anchors (Pillow) |
| `svcode/decode.py` | OpenCV receiver pipeline: HSV masks → centroids → homography → binarize |
| `svcode/codec.py` | High-level `Encoder` / `Decoder` (fountain accumulation, CRC gate) |
| `encode.py` | Transmitter CLI: static PNG, frame sequence, or on-screen player |
| `scanner.py` | Webcam scanner CLI: decode → verify signature → print action |
| `make_vectors.py` | Regenerates `vectors/` (incl. the JS-parity dump via Node) |
| `vectors/` | **Golden test vectors** (SV-0001 §8) |

## Try it

Encode a signed message to a scannable PNG:

```bash
.venv/Scripts/python.exe encode.py "HELLO, MACHINE." --out hello.png
```

Play an animated stream on screen (point a phone/webcam at it):

```bash
.venv/Scripts/python.exe encode.py "Longer message that spills into fountain mode..." --play
```

Scan with a webcam — works against `encode.py --play` output **or the live website demo** at https://futureman19.github.io/sv-codes/ :

```bash
.venv/Scripts/python.exe scanner.py --demo-ok
# against a known authority:
.venv/Scripts/python.exe scanner.py --authority-pub 02ac1b5e6915999ebbc89be7405a9fa297b0c549583a9cd3aaab750c2abc5aaeb1
```

Note: the website demo transmits a **zeroed placeholder signature** (labeled on the page); the scanner reports it as `DEMO PLACEHOLDER`. Payloads encoded with `encode.py` carry real, verifiable secp256k1 signatures.

## What the test suite proves (`tests/test_roundtrip.py`, 13 tests)

- Envelope signatures verify; tampering, wrong keys, truncation all rejected
- Stream CRC32 catches corruption
- Frame pack/unpack roundtrip (2,704 bits, exact header fields)
- Fountain decodes with **50% of symbols randomly dropped**
- Full vision pipeline on clean renders (bit-exact)
- Vision pipeline on **perspective-skewed + noisy + blurred** renders (bit-exact)
- Golden vector signature is stable across runs (RFC 6979)
- **JS ↔ Python parity**: the website transmitter and this encoder emit bit-identical frames for the same envelope
