# Master poster verification

Build from the repository root:

```
poc/.venv/Scripts/python.exe poc/make_mint_master.py
```

The generator uses a fixed nonce of zero for reproducible signed claim-pointer bytes. It has no network calls and does not alter existing genesis-001 assets. It imports the existing issuer and artwork helpers without invoking the collectible generator's main function.

## Actual local receipts

- Canonical claim certificate: **94 bytes**, budget 227; one static frame.
- Version 3, action `0xC1A1`, target `0x47454E31` (GEN1).
- Endpoint `https://sv-mint.fly.dev`; price 0; expiry 0; supply 100.
- Python PNG and JPEG quality 80: signature VALID, certificate MATCH, serialized envelope MATCH, **zero bit errors**.
- PNG SHA-256: `fee9f5c3e74de52cb84c230c2ada5ac012568c38bd34737bb2cabe646686faae`
- JPEG SHA-256: `58523aad68e840818c5d55fc926f4028a5f86c440a1451720c86bafc269e2e5e`
- Independent site JavaScript decoder: **24 passed, 0 failed** across 11 images, with zero bit errors for every image:
  - Original PNG, JPEG q80, JPEG q60.
  - Simulated 1170×2532 screenshots with 340px and 500px posters.
  - 500px poster in a 960×720 scene at −5°, −3°, 0°, +3°, +5°, blur 0.65, seeded ±14 channel noise.
  - Hard camera scene: 3° rotation, blur 1, soft glare, 45% blue-channel reduction.
- All rotations apply to a padded scene, not to an isolated image that clips the anchor corners.
- Initial 10px minimum ink failed the hard camera case with 26 bit errors. Master-only 14px minimum ink fixed it; existing collectible renderer remains unchanged.

Machine-readable Python receipts and signed envelope are in `mint-master-cert.json`.

## Local QA sources and receipts (active telegram2 profile)

```
C:/Users/futur/.hermes/profiles/telegram2/cache/scratch/mint_master_sim.py
C:/Users/futur/.hermes/profiles/telegram2/cache/scratch/svctest_mint_master.js
C:/Users/futur/.hermes/profiles/telegram2/cache/scratch/mint-master-qa/manifest.json
C:/Users/futur/.hermes/profiles/telegram2/cache/scratch/mint-master-qa/js-receipts.json
```

Run the simulation script with the repository's `poc/.venv/Scripts/python.exe`, then run the harness with Node. Fixtures and decoded RGBA buffers remain in scratch, not in the deployed assets.

## Page inspection

Local file rendered in browser. Desktop visual inspection found all four anchors visible and no text overlaps. A 390px iframe exercised the responsive breakpoint: single 335px content column, scroll width 375px (no horizontal overflow), image loaded at natural width 1024, image border radius zero, scanner link `/#broadcast`. Scrolled mobile visual inspection confirmed all four anchors intact.

Screenshots in `C:/Users/futur/.hermes/profiles/telegram2/cache/screenshots/`:

- Desktop: `browser_screenshot_7a4ee73d877f47de97fa607f3ae5d056.png`
- Mobile above-fold: `browser_screenshot_1d1cba7ab3a146f4801c426167252263.png`
- Mobile poster: `browser_screenshot_4356f72c66f7455baeab8919d89c93db.png`

These are local artifact/decoder checks, not a live mint or deployment receipt. The page deliberately does not claim live availability. Final hosted-page/scanner/service integration verification remains with the coordinating agent. No deployment, commit, push, or wallet transaction performed.
