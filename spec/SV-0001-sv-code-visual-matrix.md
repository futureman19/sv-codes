# SV-0001: SV Code Visual Matrix Protocol

| | |
|---|---|
| **Number** | SV-0001 |
| **Title** | SV Code — Machine-Native Visual Matrix for Streaming BSV Payloads |
| **Status** | **Stable** (two independent encoders emit bit-identical frames; two independent decoders — Python `poc/` + browser JS `docs/js/` — pass the published test vectors) |
| **Category** | Transport Specification (Bitcoin Machine Protocol) |
| **Created** | 2026-10-05 |
| **Requires** | BMP-0000 ([bmp repo](https://github.com/futureman19/bmp)) |

---

## 1. Abstract

SV Code (Satoshi Vision Code) is a visual data-matrix format designed for **machine** reading: raw binary mapped pixel-for-pixel onto a square grid, framed by four chromatic corner anchors, and streamed as an animated frame sequence with rateless fountain-code recovery.

It exists because QR codes (ISO/IEC 18004) were designed in 1994 for human-oriented print scanning: character-encoding modes, format metadata, and Reed-Solomon overhead sized for smudged ink. A camera-equipped machine reading a screen needs none of that. SV Code strips the format to:

1. **One pixel = one bit.** No character encoding, no mode headers.
2. **Chromatic fiducials.** Four solid-color corners found by fast HSV color masking, not nested-square ratio detection.
3. **Rateless streaming.** A Luby Transform (LT) fountain code lets the receiver recover the payload from *any* sufficient subset of frames — no frame ordering, no acknowledgments, no retransmission protocol.

SV Code carries BMP content (§4): an L1 command envelope, a raw BSV transaction, or a BEEF-packaged SPV proof, per the verification tiers of BMP-0000 §5.

## 2. Grid geometry

All coordinates are `(row, col)`, origin top-left, zero-indexed. The grid is **64 × 64** cells. On screen, cells are rendered as square pixels scaled to the display; on print, minimum 2 mm cells.

```
        col 0    5  6                     57 58   63
 row 0    +--------+----------------------------+--------+
          | anchor |      quiet zone (white)    | anchor |
          |  CYAN  |                            |MAGENTA |
 row 5    +--------+----------------------------+--------+
 row 6    | quiet  |                            | quiet  |
          | zone   |     PAYLOAD MATRIX         | zone   |
          |        |     52 x 52 = 2,704 bits   |        |
 row 57   |        |                            |        |
 row 58   +--------+----------------------------+--------+
          | anchor |      quiet zone (white)    | anchor |
          | YELLOW |                            |  RED   |
 row 63   +--------+----------------------------+--------+
```

### 2.1 Anchors

Four solid **4 × 4** chromatic blocks:

| Anchor | Cells | Color | Hue (OpenCV 0–179) | Saturation | Value |
|---|---|---|---|---|---|
| Top-Left | (0–3, 0–3) | Cyan | 85–95 | ≥ 80% | ≥ 80% |
| Top-Right | (0–3, 60–63) | Magenta | 145–155 | ≥ 80% | ≥ 80% |
| Bottom-Left | (60–63, 0–3) | Yellow | 25–35 | ≥ 80% | ≥ 80% |
| Bottom-Right | (60–63, 60–63) | Red | 0–5 or 175–179 | ≥ 80% | ≥ 80% |

Anchor **identity is carried by color, not position**. The decoder resolves rotation/mirroring from which color sits where, so a grid is decodable at any camera orientation.

### 2.2 Quiet zone

All cells outside rows 6–57 / cols 6–57 that are not anchors are **white**. This 6-cell band isolates payload bits from anchor color bleed and gives the detector a clean boundary.

### 2.3 Payload matrix

Rows 6–57, cols 6–57 → **52 × 52 = 2,704 cells = 2,704 bits** per frame, row-major (bit 0 = cell (6,6), bit 2703 = cell (57,57)).

Encoding: `0` = white (RGB 255,255,255), `1` = black (RGB 0,0,0).

## 3. Frame format

The 2,704-bit payload matrix of each frame is laid out as:

| Bits | Size | Field | Description |
|---|---|---|---|
| 0–15 | 16 | `Seed` | uint16 BE fountain seed for this frame |
| 16–23 | 8 | `Content_Type` | `0x01` BMP envelope · `0x02` raw BSV TX · `0x03` BEEF package (BRC-62/95-aligned) · other values reserved |
| 24–39 | 16 | `K` | uint16 BE count of 256-bit source symbols in the stream |
| 40–2599 | 2560 | `Symbols` | Ten 256-bit LT-encoded symbols, slots `i = 0..9` |
| 2600–2703 | 104 | `Reserved` | Zero. Receivers MUST ignore. |

`K` is carried in every frame because the degree distribution and index selection are K-dependent: without it a receiver cannot reconstruct a symbol's source-index set. All frames of one stream carry identical `K` and `Content_Type`.

### 3.1 Streams

The fountain code protects a **stream**:

```
stream = uint32_BE Content_Length ‖ uint32_BE CRC32(content) ‖ content ‖ zero-padding
```

- `Content_Length`: byte length of `content` (excludes the 8 header bytes and padding).
- `CRC32`: IEEE 802.3 CRC of `content` — cheap integrity check that runs *before* any expensive cryptographic verification.
- Padding: zero bytes up to a multiple of 32 bytes (256 bits).

The stream is split into `K = ceil(stream_bits / 256)` **source symbols** of 256 bits.

### 3.2 Fountain encoding (Luby Transform)

For a frame with `Seed = s`, each symbol slot `i ∈ 0..9` is generated independently:

1. Derive a deterministic random byte stream from SHA-256 in counter mode:
   `R(s, i)` = concatenation over `j = 0, 1, 2, …` of `SHA-256( 0x53 0x56 0x31 ("SV1") ‖ uint16_BE s ‖ uint8 i ‖ uint32_BE j )`. Bytes are consumed sequentially, four at a time as big-endian uint32 draws.
2. Sample a degree `d` from the **Robust Soliton distribution** over `K` (parameters `c = 0.1`, `δ = 0.5`) by inverse-CDF on the first draw: `u = draw₀ / 2³²`. (Normative CDF locked by test vectors when the spec graduates.)
3. Select `d` distinct source-symbol indices by repeated draws taken mod `K`, re-drawing on collision.
4. XOR the selected source symbols → the 256-bit encoded symbol for slot `i`.

Decoding is standard LT belief propagation / Gaussian elimination over GF(2): the receiver reads `K` from the frame header, reconstructs each symbol's `(degree, index-set)` from `(Seed, slot)`, and collects tuples from any frames in any order until all `K` source symbols are solved; then it reassembles the stream, checks `Content_Length` and `CRC32`, and hands `content` to the BMP layer. Receivers key accumulation state by `K`; if full rank is reached but CRC32 fails (interleaved streams with equal `K`), the receiver discards that state and keeps collecting — the transmitter's loop guarantees a clean majority of one stream.

**Reception overhead:** expect full recovery after roughly `K × 1.05` symbols. Since each frame carries 10 symbols, a `K = 16` stream (≈ 500-byte content) typically completes in 2 frames.

### 3.3 Static mode (print)

For small payloads (`K ≤ 10`, i.e. content ≤ 312 bytes — enough for an 85-byte BMP envelope plus ~227 bytes of data), a single static frame suffices: `Seed = 0`, and slot `i` carries source symbol `i` directly (degree-1 identity encoding). Unused slots are zero. A printed SV Code is therefore decodable with no animation logic at all.

## 4. Content types

| `Content_Type` | Payload | BMP tier |
|---|---|---|
| `0x01` | BMP envelope (BMP-0000 §4) | L1 — signature only |
| `0x02` | Raw BSV transaction, envelope in `OP_FALSE OP_RETURN` | L2 |
| `0x03` | BEEF / Atomic BEEF package containing the transaction | L3 — full SPV |

Receivers MUST reject unknown content types. The choice of which tiers to accept is machine policy (BMP-0000 §8.4), not a property of this format.

## 5. Transmitter requirements

1. Render frames at a steady rate; **10–15 fps** recommended. Rateless coding makes the exact rate unimportant to correctness — only latency changes.
2. Frames MAY repeat seeds across loops; duplicate symbols are harmless (they decode to already-known equations).
3. Display surface SHOULD be emissive (LCD/OLED). Projected displays work if the camera can resolve single cells.
4. Minimum rendered cell size: the receiver must resolve ≥ 2 camera pixels per cell after perspective warp. In practice, a 64×64 grid occupying ≥ 25% of a 1080p frame decodes reliably.
5. Keep the full grid, including the quiet zone, visible. Occluding an anchor makes the frame undecodable (the fountain code cannot compensate for missing geometry).

## 6. Receiver pipeline

```
camera ─▶ HSV mask ─▶ 4 anchor centroids ─▶ homography warp
      ─▶ 64×64 canonical image ─▶ binarize ─▶ 2,704 bits
      ─▶ frame parse ─▶ LT solver ─▶ stream ─▶ CRC32 ─▶ BMP layer
```

Normative steps:

1. **Color masking.** Convert the frame to HSV (OpenCV hue scale 0–179). Produce four binary masks using the §2.1 ranges.
2. **Centroid extraction.** For each mask, compute the spatial centroid
   `(x̄, ȳ) = (M10/M00, M01/M00)`. Four valid anchors MUST be found; otherwise discard the camera frame.
3. **Homography.** Compute the 3×3 perspective transform mapping the detected centroids to canonical anchor centers `(2,2) (62,2) (2,62) (62,62)` — the 4×4 anchor blocks span cells 0–3 and 60–63, whose centers are cell coordinates 2.0 and 62.0 — with anchor identity resolved by color. Warp to a canonical 64×64 image (`cv2.getPerspectiveTransform` + `cv2.warpPerspective`).
4. **Binarization.** For each payload cell `(r,c)`, sample the canonical image at `(r+0.5, c+0.5)` — a 3×3 majority vote around the center is RECOMMENDED for robustness — and threshold: `< θ → 1` (black), `≥ θ → 0` (white). `θ` may be fixed (128) or Otsu-adaptive per frame.
5. **Frame parse.** Read §3 fields row-major from the payload matrix.
6. **Solve.** Feed symbols to the LT decoder. On completion, validate `Content_Length` + `CRC32`, then dispatch by `Content_Type` to BMP-0000 verification (signature / SPV per tier).

Receivers MUST treat any failed step as a dropped frame, never as a partial result. A receiver MUST NOT execute payload content before both integrity (CRC32) and the applicable BMP verification tier pass.

## 7. Security considerations

- **Integrity before crypto.** CRC32 catches corruption cheaply; the BMP envelope signature is the actual security boundary. Never act on CRC-only-valid content.
- **L1 over visual is safe-by-physics.** SV Code is a short-range, line-of-sight, physically-local transport, which is why BMP-0000 permits tier L1 over it: an attacker must physically present a forged grid to the camera, and forgery still fails signature verification.
- **Replay.** Envelope replay protection (nonce window / counter) is defined in BMP-0000 §8.2 and applies unchanged — a photographed screen replays a valid signature, so receivers MUST enforce the nonce rules.
- **Screen spoofing.** Nothing in this format proves *which screen* displayed a grid. If venue authenticity matters, bind it at the envelope layer (e.g., venue key in `Payload_Data`), not the visual layer.
- **Denial of service.** A bright strobing display can starve a receiver's camera. Local policy SHOULD rate-limit and SHOULD fall back to other transports if no valid stream completes within a timeout.

## 8. Test vectors

Published in `poc/vectors/`:

1. `vectors.json` — golden authority keypair (test-only private key intentionally included), a signed `0x00FF` VENDOR envelope ("HELLO, MACHINE.", nonce 1791504000), and a signed `0x00A1 MOVE_TO` envelope with JSON payload; envelope hex, signatures, CRC32, and K for each.
2. `static_frame.png` — vector 1 as a static-mode (seed 0) SV Code render.
3. `fountain/frame_*.png` — vector 2 as a six-frame fountain stream (seeds 1–6).
4. `js_frames.json` — vector-2 frames emitted by the independent JavaScript transmitter (`docs/js/svc.js`); the PoC suite asserts **bit-exact parity** between the JS and Python encoders.

Reference-implementation status: both vectors round-trip through clean renders, perspective-skewed/noisy/blurred renders, and 50% random symbol loss in **two independent decoders** — the Python reference (`poc/tests/`, 13 tests) and the browser JS decoder (`docs/js/decoder.js`, exercised against synthetic camera photos in `poc/fixtures/`); both verify both envelope signatures. Encoders are bit-exact across the two implementations. **Graduated to Stable 2026-10-05.**

## 9. References

- BMP-0000: Bitcoin Machine Protocol (this repository)
- ISO/IEC 18004 — QR Code (the legacy format this supersedes for machine use)
- Luby, M., "LT Codes," FOCS 2002 — fountain coding
- BRC-62 (BEEF), BRC-95 (Atomic BEEF), BUMP merkle format — <https://bsv.brc.dev/> (format alignment only; no conformance claim)
- Blockchain Commons UR / `bc-fountain` — prior art for animated air-gapped QR streaming (human-wallet oriented)
