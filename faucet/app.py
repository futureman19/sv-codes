"""SV Codes sticker faucet — pays a few sats to a fresh in-browser wallet.

Endpoints:
  POST /claim  {pub, s, fp}  -> {address, sats, txid}
  GET  /health               -> network, balance, claim counts
  GET  /stats                -> per-sticker claim counts

Config (env): FAUCET_WIF (required to pay), NETWORK=main|test,
FAUCET_SATS, FEE_SATS, MAX_IP_PER_DAY, MAX_FP, MAX_PER_DAY, DB_PATH.
"""
import asyncio
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.request

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import txbuilder as tx

NETWORK = os.environ.get("NETWORK", "main")
WIF = os.environ.get("FAUCET_WIF", "")
SATS = int(os.environ.get("FAUCET_SATS", "50000"))
FEE = int(os.environ.get("FEE_SATS", "300"))
MAX_IP_PER_DAY = int(os.environ.get("MAX_IP_PER_DAY", "3"))
MAX_FP = int(os.environ.get("MAX_FP", "2"))
MAX_PER_DAY = int(os.environ.get("MAX_PER_DAY", "200"))
DB_PATH = os.environ.get("DB_PATH", "/data/faucet.db" if os.path.isdir("/data") else "faucet.db")
WOC = f"https://api.whatsonchain.com/v1/bsv/{NETWORK}"

PUB_RE = re.compile(r"^0[23][0-9a-fA-F]{64}$")

app = FastAPI(title="sv-faucet")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
claim_lock = asyncio.Lock()

# ---------- storage ----------
def db():
    con = sqlite3.connect(DB_PATH)
    con.execute("""CREATE TABLE IF NOT EXISTS claims(
        pub TEXT PRIMARY KEY, ip TEXT, fp TEXT, sticker TEXT,
        sats INTEGER, txid TEXT, ts REAL)""")
    return con

def day_ago(): return time.time() - 86400

def count(con, where, arg):
    return con.execute(f"SELECT COUNT(*) FROM claims WHERE {where}", (arg,)).fetchone()[0]

# ---------- chain ----------
def http_json(url, payload=None, timeout=20):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": "sv-faucet/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def fetch_utxos(address):
    r = http_json(f"{WOC}/address/{address}/unspent/all")
    rows = r["result"] if isinstance(r, dict) and "result" in r else r
    return [{"txid": u["tx_hash"], "vout": u["tx_pos"], "value": int(u["value"])} for u in rows]

def broadcast(raw_hex):
    try:
        r = http_json(f"{WOC}/tx/raw", {"txhex": raw_hex}, timeout=30)
        return r if isinstance(r, str) else r.get("txid") or r.get("result")
    except urllib.error.HTTPError as e:
        raise RuntimeError("broadcast rejected: " + e.read().decode()[:300])

# ---------- faucet key ----------
_faucet = {"priv": None, "pub": None, "address": None}
def faucet():
    if _faucet["priv"] is None and WIF:
        priv = tx.wif_to_priv(WIF)
        pub = tx.compress_pub(tx.pubkey_from_priv(priv))
        _faucet.update(priv=priv, pub=pub, address=tx.address_from_pubkey(pub))
    return _faucet

# ---------- endpoints ----------
@app.get("/health")
def health():
    f = faucet()
    out = {"ok": True, "network": NETWORK, "funded": f["priv"] is not None,
           "address": f["address"], "sats_per_claim": SATS}
    if f["priv"]:
        try:
            utxos = fetch_utxos(f["address"])
            out["balance_sats"] = sum(u["value"] for u in utxos)
            out["utxos"] = len(utxos)
        except Exception as e:
            out["balance_error"] = str(e)[:200]
    with db() as con:
        out["claims_total"] = con.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
        out["claims_today"] = con.execute("SELECT COUNT(*) FROM claims WHERE ts > ?",
                                          (day_ago(),)).fetchone()[0]
    return out

@app.get("/stats")
def stats():
    with db() as con:
        rows = con.execute(
            "SELECT sticker, COUNT(*), COALESCE(SUM(sats),0) FROM claims GROUP BY sticker").fetchall()
    return {"network": NETWORK,
            "per_sticker": {s: {"claims": c, "sats": v} for s, c, v in rows},
            "total_claims": sum(c for _, c, _ in rows)}

@app.post("/claim")
async def claim(req: Request):
    body = await req.json()
    pub_hex = (body.get("pub") or "").strip()
    sticker = re.sub(r"[^a-zA-Z0-9-]", "", (body.get("s") or "web"))[:32] or "web"
    fp = re.sub(r"[^0-9a-f]", "", (body.get("fp") or ""))[:16]
    # behind fly.io's proxy req.client.host is the edge proxy IP (shared by ALL
    # visitors) — use Fly-Client-IP so rate limits apply per real visitor
    ip = req.headers.get("fly-client-ip") or (req.client.host if req.client else "?")

    if not PUB_RE.match(pub_hex):
        return JSONResponse({"error": "bad_request", "detail": "invalid pubkey"}, 400)
    try:
        tx.parse_pubkey(bytes.fromhex(pub_hex))
    except Exception:
        return JSONResponse({"error": "bad_request", "detail": "pubkey not on curve"}, 400)
    f = faucet()
    if not f["priv"]:
        return JSONResponse({"error": "faucet_empty", "detail": "faucet not funded yet"}, 503)

    async with claim_lock:
        with db() as con:
            if count(con, "pub = ?", pub_hex):
                row = con.execute("SELECT sats, txid FROM claims WHERE pub = ?",
                                  (pub_hex,)).fetchone()
                return JSONResponse({"error": "already_claimed",
                                     "address": tx.address_from_pubkey(bytes.fromhex(pub_hex)),
                                     "sats": row[0], "txid": row[1]}, 409)
            ip_n = con.execute("SELECT COUNT(*) FROM claims WHERE ip = ? AND ts > ?",
                               (ip, day_ago())).fetchone()[0]
            fp_n = con.execute("SELECT COUNT(*) FROM claims WHERE fp = ? AND fp != ''", (fp,)).fetchone()[0]
            day_n = con.execute("SELECT COUNT(*) FROM claims WHERE ts > ?", (day_ago(),)).fetchone()[0]
            if day_n >= MAX_PER_DAY:
                return JSONResponse({"error": "rate_limited", "detail": "daily cap reached"}, 429)
            if ip_n >= MAX_IP_PER_DAY:
                return JSONResponse({"error": "rate_limited", "detail": "this network claimed recently"}, 429)
            if fp and fp_n >= MAX_FP:
                return JSONResponse({"error": "rate_limited", "detail": "this device already claimed"}, 429)

        address = tx.address_from_pubkey(bytes.fromhex(pub_hex))
        pay_script = tx.p2pkh_script(bytes.fromhex(pub_hex))
        change_script = tx.p2pkh_script(f["pub"])
        try:
            utxos = fetch_utxos(f["address"])
        except Exception as e:
            return JSONResponse({"error": "upstream", "detail": str(e)[:200]}, 502)
        # prefer fewest inputs: sort descending, take until covered
        utxos.sort(key=lambda u: -u["value"])
        picked, acc = [], 0
        for u in utxos:
            picked.append(u); acc += u["value"]
            if acc >= SATS + FEE: break
        if acc < SATS + FEE:
            return JSONResponse({"error": "faucet_empty"}, 503)
        try:
            raw, txid = await asyncio.to_thread(
                tx.build_tx, picked, pay_script, SATS, change_script, FEE, f["priv"])
            got = await asyncio.to_thread(broadcast, raw)
            if got and got != txid:
                txid = got
        except Exception as e:
            return JSONResponse({"error": "broadcast_failed", "detail": str(e)[:300]}, 502)
        with db() as con:
            con.execute("INSERT INTO claims VALUES (?,?,?,?,?,?,?)",
                        (pub_hex, ip, fp, sticker, SATS, txid, time.time()))
        return {"address": address, "sats": SATS, "txid": txid}
