"""L2 live demo — broadcast a real BMP-0002 anchored command on BSV mainnet.

Flow:
  1. Generate a fresh, disposable fee-payer keypair (published in l2_live.json).
  2. Claim 50,000 sats to it from the public sv-faucet API (same path any
     sticker visitor uses).
  3. Build an L2 transaction: envelope signed by the golden TEST authority
     (poc/vectors/vectors.json), fee paid by the demo key, change returned to
     the faucet hot wallet.
  4. Broadcast to mainnet via WhatsOnChain.
  5. Fetch the confirmed raw tx back from WoC and run the full offline
     verify_l2 pipeline against the ledger's own bytes.

Writes poc/vectors/l2_live.json. Cost to the faucet: 300 sats (the fee) plus
the claim tx's own fee; the 49,700-sat change returns to the faucet.
"""
from __future__ import annotations

import json
import pathlib
import time
import urllib.request

from svcode import anchor, tx as txm
from svcode.crypto import generate_key, key_from_hex
from svcode.envelope import Envelope

ROOT = pathlib.Path(__file__).parent
VECTORS = json.loads((ROOT / "vectors" / "vectors.json").read_text())
AUTH_PRIV = VECTORS["private_key_hex"]
AUTH_PUB = VECTORS["authority_pubkey_compressed"]

WOC = "https://api.whatsonchain.com/v1/bsv/main"
FAUCET = "https://sv-faucet.fly.dev"
FAUCET_ADDRESS = "1FpHQ4VrLYGp1sLDNXs5Cxh3x8KE4opYgU"
FEE = 300

PAYLOAD = "HELLO, CHAIN. This command paid its own way."


def http_json(url, payload=None, timeout=25):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "svc-l2-demo"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def http_text(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": "svc-l2-demo"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode()


def p2pkh_script_from_address(addr: str) -> bytes:
    _ver, h160 = txm.b58check_decode(addr)
    return bytes.fromhex("76a914") + h160 + bytes.fromhex("88ac")


def main() -> None:
    # 1. fresh fee-payer keypair (disposable, published — see note in l2_live.json)
    sk = generate_key()
    payer_priv = int.from_bytes(sk.to_string(), "big")
    payer_pub = txm.compress_pub(txm.pubkey_from_priv(payer_priv))
    payer_addr = txm.address_from_pubkey(payer_pub)
    print(f"[1] demo payer address: {payer_addr}")
    # persist IMMEDIATELY so a mid-run failure never strands funds
    (ROOT / "vectors" / "l2_live.json").write_text(json.dumps({
        "status": "in_progress",
        "payer_pubkey": payer_pub.hex(),
        "payer_priv_hex": sk.to_string().hex(),
        "payer_address": payer_addr,
        "note": "recovery record written before any funds move",
    }, indent=2))

    # 2. claim from the public faucet
    print("[2] claiming 50,000 sats from sv-faucet…")
    claim = http_json(f"{FAUCET}/claim", {"pub": payer_pub.hex(), "s": "l2-demo", "fp": ""})
    if "txid" not in claim:
        raise SystemExit(f"claim failed: {claim}")
    claim_txid = claim["txid"]
    print(f"    claim txid: {claim_txid}")

    # 3. derive the UTXO from the claim tx itself (address indexers lag)
    utxo = None
    for _ in range(30):
        try:
            ctx = http_json(f"{WOC}/tx/{claim_txid}")
            for v in ctx["vout"]:
                addrs = v.get("scriptPubKey", {}).get("addresses") or []
                if payer_addr in addrs:
                    utxo = {"txid": claim_txid, "vout": v["n"],
                            "value": int(round(v["value"] * 1e8))}
                    break
            if utxo:
                break
        except Exception:
            pass
        time.sleep(4)
    if utxo is None:
        raise SystemExit("claim tx never appeared on WoC (payer key saved in l2_live.json)")
    print(f"[3] utxo visible: {utxo['value']} sats @ {utxo['txid'][:16]}…:{utxo['vout']}")

    # 4. build the L2 command: authority signs, demo key pays, change → faucet
    env = Envelope(target_id=0x53564331, action=0x00FF, payload=PAYLOAD.encode())
    env.sign(key_from_hex(AUTH_PRIV))
    raw_hex, txid, prevouts = anchor.build_l2_tx(
        env.serialize(), [utxo], payer_priv,
        change_script=p2pkh_script_from_address(FAUCET_ADDRESS), fee=FEE)
    print(f"[4] L2 tx built: {txid}  ({len(bytes.fromhex(raw_hex))} bytes, fee {FEE})")

    # 5. broadcast (retry — parent may still be propagating)
    print("[5] broadcasting…")
    got = None
    for attempt in range(12):
        try:
            r = _broadcast(raw_hex)
            got = r.strip().strip('"')
            break
        except Exception as e:
            print(f"    attempt {attempt + 1}: {str(e)[:120]}")
            time.sleep(5)
    if not got:
        raise SystemExit("broadcast never accepted")
    print(f"    accepted: {got}")

    # 6. re-verify from the ledger's own bytes
    fetched = None
    for _ in range(30):
        try:
            fetched = http_text(f"{WOC}/tx/{txid}/hex").strip()
            if fetched:
                break
        except Exception:
            pass
        time.sleep(4)
    if not fetched:
        raise SystemExit("tx never appeared on WoC")
    seen = {}
    out = anchor.verify_l2(bytes.fromhex(fetched), prevouts, AUTH_PUB, seen)
    print(f"[6] VERIFY FROM LEDGER: PASS — action {out.action_name}, "
          f"payload {out.payload.decode()!r}, authority sig valid")

    (ROOT / "vectors" / "l2_live.json").write_text(json.dumps({
        "note": "Live BMP-0002 L2 proof on BSV mainnet. Payer key is a fresh "
                "disposable demo key (published intentionally; it holds no funds — "
                "change returned to the faucet). Authority key is the published "
                "golden TEST key from vectors.json.",
        "txid": txid,
        "claim_txid": claim_txid,
        "network": "main",
        "fee_sats": FEE,
        "payload_text": PAYLOAD,
        "envelope_hex": env.serialize().hex(),
        "authority_pubkey": AUTH_PUB,
        "payer_pubkey": payer_pub.hex(),
        "payer_priv_hex": sk.to_string().hex(),
        "prevouts": prevouts,
        "change_returned_to": FAUCET_ADDRESS,
        "verify_from_ledger": True,
        "timestamp": int(time.time()),
    }, indent=2))
    print(f"[7] wrote vectors/l2_live.json")


def _broadcast(raw_hex: str) -> str:
    req = urllib.request.Request(
        f"{WOC}/tx/raw", data=json.dumps({"txhex": raw_hex}).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "svc-l2-demo"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode()


if __name__ == "__main__":
    main()
