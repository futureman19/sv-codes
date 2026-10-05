"""L3 live proof — build a BRC-62 BEEF around our real on-chain L2 command
(txid 4a6f612b…) and run the full BMP-0003 verification pipeline against it.

Fetches: subject raw tx + BUMP + block header, parent raw tx + BUMP + block
header, chain tip. Saves everything into poc/vectors/l3_live.json so the
offline test suite can replay the proof forever.
"""
from __future__ import annotations

import json
import pathlib
import urllib.request

from svcode import spv

ROOT = pathlib.Path(__file__).parent
VECTORS = json.loads((ROOT / "vectors" / "vectors.json").read_text())
AUTH_PUB = VECTORS["authority_pubkey_compressed"]

WOC = "https://api.whatsonchain.com/v1/bsv/main"
SUBJECT = "4a6f612be1f8984ee13da679c1c5f7698f4d118304ca51ea98e895c4a977b3d1"
PARENT = "ef5d1734f7af787296465da79971c50f11f31ace326c88ecbc8543019a1d8cbc"


def get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "svc-l3-demo"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def get_json(url):
    return json.loads(get(url))


def fetch_bump(txid: str) -> bytes:
    body = get(f"{WOC}/tx/{txid}/proof/bump").strip().strip('"')
    return bytes.fromhex(body)


def fetch_header(blockhash: str) -> tuple[bytes, int]:
    j = get_json(f"{WOC}/block/{blockhash}/header")
    raw = (
        int(j["version"]).to_bytes(4, "little")
        + bytes.fromhex(j["previousblockhash"])[::-1]
        + bytes.fromhex(j["merkleroot"])[::-1]
        + int(j["time"]).to_bytes(4, "little")
        + int(j["bits"], 16).to_bytes(4, "little")
        + int(j["nonce"]).to_bytes(4, "little")
    )
    return raw, int(j["height"])


def main() -> None:
    print("[1] fetching chain data…")
    subj_raw = bytes.fromhex(get(f"{WOC}/tx/{SUBJECT}/hex").strip())
    subj_bump = fetch_bump(SUBJECT)
    subj_meta = get_json(f"{WOC}/tx/{SUBJECT}")
    parent_raw = bytes.fromhex(get(f"{WOC}/tx/{PARENT}/hex").strip())
    parent_bump = fetch_bump(PARENT)
    parent_meta = get_json(f"{WOC}/tx/{PARENT}")
    subj_hdr, subj_h = fetch_header(subj_meta["blockhash"])
    parent_hdr, parent_h = fetch_header(parent_meta["blockhash"])
    tip = get_json(f"{WOC}/chain/info")["blocks"]
    print(f"    subject in block {subj_h}, parent in block {parent_h}, tip {tip}")

    print("[2] assembling BEEF (BRC-62 v1)…")
    beef = (
        spv.BEEF_V1
        + spv.ser_varint(2) + parent_bump + subj_bump
        + spv.ser_varint(2)
        + parent_raw + b"\x01" + spv.ser_varint(0)
        + subj_raw + b"\x01" + spv.ser_varint(1)
    )
    print(f"    BEEF: {len(beef)} bytes (parent {len(parent_raw)}B + subject {len(subj_raw)}B + 2 BUMPs)")

    print("[3] verify_l3 …")
    env = spv.verify_l3(beef, AUTH_PUB, [subj_hdr, parent_hdr],
                        seen={}, tip_height=tip, min_depth=1)
    print(f"    PASS — action {env.action_name}, payload {env.payload.decode()!r}")
    print("    envelope authority sig ✓ · input sigs vs BEEF ancestors ✓ · "
          "fee ✓ · merkle inclusion of both TXs ✓ · header PoW ✓")

    (ROOT / "vectors" / "l3_live.json").write_text(json.dumps({
        "note": "Live BMP-0003 L3 proof on BSV mainnet. BEEF wraps the L2 "
                "command tx 4a6f612b… plus its parent ef5d1734…, each with its "
                "BRC-74 BUMP; headers fetched from WoC. Authority = published "
                "golden TEST key from vectors.json.",
        "subject_txid": SUBJECT,
        "parent_txid": PARENT,
        "beef_hex": beef.hex(),
        "subject_block": {"height": subj_h, "header_hex": subj_hdr.hex()},
        "parent_block": {"height": parent_h, "header_hex": parent_hdr.hex()},
        "tip_height_at_fetch": tip,
        "expected_payload": "HELLO, CHAIN. This command paid its own way.",
        "authority_pubkey": AUTH_PUB,
    }, indent=2))
    print("[4] wrote vectors/l3_live.json")


if __name__ == "__main__":
    main()
