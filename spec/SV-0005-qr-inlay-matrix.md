# SV-0005 — QR-Inlay Visual Matrix (Draft)

| Field | Value |
|---|---|
| Number | SV-0005 |
| Title | QR-Inlay Visual Matrix |
| Status | Draft |
| Depends | SV-0001 (visual matrix), BMP-0000 (envelope) |
| Reference implementation | `poc/svcode/inlay.py` + `poc/tests/test_inlay.py` |

## 1. Overview

SV-0005 defines an extended SV matrix that reserves its center cells for an
ordinary QR code. Any phone camera reads the QR natively (the onboarding
bridge); an SV-capable scanner reads the signed fountain payload carried in
every remaining cell. One physical artifact, two independent machine layers:

- **Layer 1 (unsigned):** the QR — typically an HTTPS URL to a landing page.
- **Layer 2 (signed):** the SV frame — a standard BMP envelope, verifiable
  offline, exactly as in SV-0001.

The QR is a *Trojan horse*: it recruits the scanner. Only Layer 2 is
authenticated (§8).

## 2. Grid Geometry

- Grid: **96 × 96 cells**. Quiet border: 6 cells. Inner matrix: **84 × 84**
  cells (7,056 cells) at rows/cols 6–89.
- Anchors: four 4×4 pure-hue blocks at the corners, identical hues and HSV
  ranges to SV-0001 §2.1 (TL cyan, TR magenta, BL yellow, BR red).
- Inlay: a centered square of `INLAY × INLAY` inner cells, reserved for the
  QR. Payload MUST NOT be written to inlay cells.

### 2.1 Canonical layout (NORMATIVE for this edition)

| Parameter | Value |
|---|---|
| QR payload | issuer HTTPS URL, e.g. `HTTPS://SVCODE.ORG` (uppercase keeps QR in compact alphanumeric mode) |
| QR error correction | H (30%) recommended; M minimum |
| QR quiet zone | ≥ 2 modules (2 canonical; the SV matrix substitutes for the full 4-module margin) |
| QR_SCALE | 1 SV cell per QR module |
| Resulting inlay | QR v2 (25 modules) + 2-module border = 29 cells → `INLAY = 29`, origin inner cell (27, 27) |
| Usable payload cells | 7,056 − 841 = **6,215** |
| Slots `N` | ⌊(6,215 − 40) / 256⌋ = **24** |

Decoders MUST accept the canonical layout by table lookup and MAY detect the
white inlay plate directly to support future layouts.

## 3. Frame Format

Bit-level frame = SV-0001 §3 header (`seed:16 | ctype:8 | k:16`) followed by
`N` 256-bit slots, mapped row-major over the usable cells (inlay cells
skipped), zero-padded to the usable-cell count.

`N = ⌊(usable − 40) / 256⌋` (canonical: 24). `K` is declared in the header as
in SV-0001; degree/index reconstruction is deterministic from `(seed, slot)`.

## 4. QR Inlay Requirements

- The QR symbol is rendered at QR_SCALE SV cells per module (canonical 1),
  pure black modules on the matrix field (lightest) tone.
- The inlay region is the QR image INCLUDING its quiet zone; the SV matrix
  resumes immediately outside it.
- The QR SHOULD decode under: 250 px total-grid images, 3° rotation, Gaussian
  blur (3×3), and ±14/255 sensor noise. (Reference gate:
  `test_inlay.py::test_qr_layer_reads` + phone-sim in `make_inlay_mock.py`.)
- Payload SHOULD be a single HTTPS URL. Per-artifact analytics parameters are
  allowed if the QR version still fits the canonical inlay.

## 5. Encoding Rules (NORMATIVE)

1. Content is framed exactly as SV-0001 §3.1 (stream = length ‖ CRC32 ‖
   content ‖ pad; 32-byte symbols).
2. **Inlay frames MUST broadcast with `seed ≥ 1` even when `K ≤ N`.**
   Identity mode (`seed = 0`) renders slots `≥ K` as blank cells, producing a
   visibly sparse matrix; fountain mode fills every slot with real encoded
   data — uniform density AND erasure robustness: the frame decodes from any
   sufficient subset of its `N` slots (reference proof: every second slot
   erased, signature still VALID).
3. `K ≤ N`. For BMP envelope content (ctype 0x01) the canonical layout holds
   envelopes up to ≈ 675 payload bytes.

## 6. Decoder Conformance

1. Locate the four hue anchors (SV-0001 §6.1, unchanged — the finder is
   grid-agnostic).
2. Grid size: infer cell pitch from the 4×4 anchor block size, or warp and
   try {64, 96}. Warp to the canonical 96-grid image.
3. Per-cell value = mean of the central 50% block of each usable cell.
4. **Threshold = midpoint of the per-cell mean extremes (NORMATIVE).** Otsu
   on near-bimodal fields collapses onto the black rail (every dark cell
   reads 0) and MUST NOT be used.
5. Read the frame from the first `(40 + 256·N)` usable cells, skipping inlay
   cells; feed slots to the LT solver; validate stream CRC32; parse and
   verify the envelope per BMP-0000.

## 7. Why Not a 64×64 Inlay

A center inlay big enough to scan (≥ 29×29 cells) destroys 7 of the 10
SV-0001 slots, leaving `K ≤ 3` — a ~96-byte stream that cannot hold the
85-byte envelope header plus any meaningful payload. The 96×96 grid leaves
24 clean slots, exceeding today's entire static budget.

## 8. Security & Interop Notes

- **The QR layer is unsigned.** Verifiers MUST treat only the SV layer as
  authentic. Scanners SHOULD display the SV-verified issuer and MUST NOT
  auto-open QR URLs on behalf of the user beyond normal camera behavior.
- A swapped QR sticker placed over an SV-0005 artifact changes only Layer 1;
  Layer 2 verification is unaffected.
- Legacy (SV-0001-only) decoders sampling a 96-grid as 64 cells will read
  noise and fail CRC — a safe rejection, not a misdecode.
- The four anchors remain the only chromatic contract; the QR contributes no
  hue within anchor HSV bands (it is black/white by definition).
