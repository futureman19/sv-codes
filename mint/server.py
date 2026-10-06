"""Single-volume SV-0003 mint. No key creation, no network calls on import.

A cross-process OS lock covers assignment, wallet access and all WoC calls.
SQLite FULL synchronous commits reserve editions and journal signed raw bytes
BEFORE broadcasting. Any uncertainty freezes the wallet on those exact bytes.
"""
from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha256
import ipaddress
import json
import os
from pathlib import Path
import random
import sqlite3
import sys
import threading
import time

import httpx
import portalocker
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from . import txbuilder as tx

# Reuse the published renderer and BMP implementation, not a second renderer.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'poc'))
from make_genesis_001 import render_reveal, reveal_params
from svcode.crypto import key_from_hex, pubkey_hex
from svcode.envelope import Envelope

COL = 'sv-genesis'
SUPPLY = 100
DEMO_SEED = 'sv genesis collection issuer key v1 (demo)'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def make_certificate(edition, art_dir):
    if type(edition) is not int or not 1 <= edition <= SUPPLY:
        raise ValueError('edition out of range')
    seed = sha256(b'sv-genesis' + str(edition).encode('ascii')).digest()[:3].hex()
    art_dir = Path(art_dir)
    art_dir.mkdir(parents=True, exist_ok=True)
    art = render_reveal(seed, str(art_dir / f'{edition:03}.png'))
    p = reveal_params(seed)
    cert = dict(art=art, col=COL, ed=edition, item='genesis-blade', mint='0'*64,
                of=SUPPLY, seed=seed, tr=dict(core=p['core'], edge=p['edge']), v=2)
    if len(canonical(cert)) > 227:
        raise ValueError('certificate exceeds static frame budget')
    return cert


def make_templates(art_dir):
    return {ed: make_certificate(ed, art_dir) for ed in range(1, SUPPLY + 1)}


def address_script(address):
    # No stripping/repair; require a canonical, checksummed mainnet P2PKH address.
    try:
        if not isinstance(address, str) or not 26 <= len(address) <= 35:
            raise ValueError()
        raw = tx.b58decode(address)
        if len(raw) != 25 or raw[0] != 0 or tx.sha256d(raw[:-4])[:4] != raw[-4:]:
            raise ValueError()
        return b'\x76\xa9\x14' + raw[1:21] + b'\x88\xac'
    except (ValueError, IndexError):
        raise MintError(400, 'invalid_address') from None


class MintError(Exception):
    def __init__(self, status, error):
        self.status, self.error = status, error
        super().__init__(error)


class WoC:
    """Called only under the service's process-wide volume lock; never in parallel."""
    def __init__(self):
        self.client = httpx.Client(base_url='https://api.whatsonchain.com/v1/bsv/main',
                                   timeout=30, headers={'User-Agent': 'sv-mint/1.0'})

    def utxos(self, address):
        r = self.client.get(f'/address/{address}/unspent/all')
        r.raise_for_status()
        data = r.json()
        rows = data.get('result', []) if isinstance(data, dict) else data
        # Initial/top-up funding must be confirmed. Unconfirmed change is sourced
        # exclusively from our accepted and locally journaled parent transaction.
        return [dict(txid=u['tx_hash'], vout=int(u['tx_pos']), value=int(u['value']))
                for u in rows if int(u.get('height', 0)) > 0]

    def raw(self, txid):
        r = self.client.get(f'/tx/{txid}/hex')
        if r.status_code == 404:
            return None
        r.raise_for_status()
        value = r.text.strip().strip('"')
        bytes.fromhex(value)
        return value.lower()

    def broadcast(self, raw):
        r = self.client.post('/tx/raw', json={'txhex': raw})
        r.raise_for_status()
        value = r.json()
        return value if isinstance(value, str) else value.get('txid') or value.get('result')


def transaction_outputs(raw_hex):
    """Parse our journaled parent for change; never depend on the address index."""
    raw = bytes.fromhex(raw_hex)
    pos = 4
    def read(n):
        nonlocal pos
        out = raw[pos:pos+n]
        if len(out) != n: raise ValueError('truncated transaction')
        pos += n
        return out
    def vi():
        value = read(1)[0]
        return value if value < 253 else int.from_bytes(read({253:2, 254:4, 255:8}[value]), 'little')
    for _ in range(vi()):
        read(36); read(vi()); read(4)
    outputs = []
    for _ in range(vi()):
        value = int.from_bytes(read(8), 'little')
        outputs.append((value, read(vi())))
    if read(4) != b'\0'*4 or pos != len(raw): raise ValueError('unexpected transaction')
    return outputs


class MintService:
    def __init__(self, path, priv, issuer_seed, chain, *, templates=None, fee=300, max_ip=3, funding_txid=None):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.mutex = threading.RLock()
        self.priv = priv
        if not 1 <= priv < tx.N or fee < 1 or max_ip < 1:
            raise ValueError('invalid service configuration')
        self.pub = tx.compress_pub(tx.pubkey_from_priv(priv))
        self.address = tx.address_from_pubkey(self.pub)
        self.change_script = tx.p2pkh_script(self.pub)
        if not issuer_seed:
            raise ValueError('ISSUER_SEED required')
        self.issuer = key_from_hex(sha256(issuer_seed.encode('utf-8')).hexdigest())
        if self.issuer.privkey.secret_multiplier == priv:
            raise ValueError('MINT_WIF must be independent of issuer')
        self.chain, self.fee, self.max_ip = chain, fee, max_ip
        if funding_txid is not None and (len(funding_txid) != 64 or any(c not in '0123456789abcdef' for c in funding_txid)):
            raise ValueError('invalid FUNDING_TXID')
        self.funding_txid = funding_txid
        with self.lock(), self.db() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS mints (
                    col TEXT PRIMARY KEY, supply INTEGER NOT NULL, commitment TEXT NOT NULL,
                    shuffle_json TEXT NOT NULL, opened_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS claims (
                    col TEXT NOT NULL, edition INTEGER NOT NULL, address TEXT NOT NULL,
                    txid TEXT UNIQUE, ts REAL NOT NULL, ip TEXT NOT NULL, position INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('reserved','prepared','accepted')),
                    raw_tx TEXT, inputs_json TEXT, response_json TEXT,
                    PRIMARY KEY(col,edition), UNIQUE(col,address), UNIQUE(col,position));
                CREATE UNIQUE INDEX IF NOT EXISTS one_pending_wallet ON claims ((1)) WHERE state != 'accepted';
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS wallet (
                    txid TEXT NOT NULL, vout INTEGER NOT NULL, value INTEGER NOT NULL,
                    PRIMARY KEY(txid,vout));
            ''')
            binding = canonical({'funding_address': self.address, 'issuer_pub': pubkey_hex(self.issuer)}).decode()
            old = con.execute("SELECT value FROM meta WHERE key='binding'").fetchone()
            if old and old[0] != binding:
                raise ValueError('persisted mint key binding changed; refusing startup')
            con.execute("INSERT OR IGNORE INTO meta VALUES ('binding', ?)", (binding,))
            saved = con.execute("SELECT value FROM meta WHERE key='templates'").fetchone()
            if saved:
                self.templates = {int(k): v for k,v in json.loads(saved[0]).items()}
                if templates is not None and self.templates != templates:
                    raise ValueError('persisted certificate templates changed')
            else:
                self.templates = templates if templates is not None else make_templates(self.path.parent / 'art')
                if set(self.templates) != set(range(1,101)) or any(len(canonical(c)) > 227 for c in self.templates.values()):
                    raise ValueError('invalid certificate templates')
                con.execute("INSERT INTO meta VALUES ('templates',?)", (canonical(self.templates).decode(),))
            if not con.execute('SELECT 1 FROM mints WHERE col=?', (COL,)).fetchone():
                shuffle = list(range(1,SUPPLY+1)); random.SystemRandom().shuffle(shuffle)
                encoded = canonical(shuffle)
                con.execute('INSERT INTO mints VALUES (?,?,?,?,?)',
                            (COL, SUPPLY, sha256(encoded).hexdigest(), encoded.decode(), time.time()))

    @contextmanager
    def db(self):
        con = sqlite3.connect(self.path, timeout=60)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA synchronous=FULL')
        try:
            with con:
                yield con
        finally:
            con.close()

    @contextmanager
    def lock(self):
        with self.mutex:
            try:
                with portalocker.Lock(str(self.path) + '.lock', timeout=90):
                    yield
            except portalocker.exceptions.LockException:
                raise MintError(503, 'busy') from None

    def status(self):
        with self.db() as con:
            con.execute('BEGIN')
            mint = con.execute('SELECT * FROM mints WHERE col=?', (COL,)).fetchone()
            rows = con.execute("SELECT edition,position,txid,ts,response_json FROM claims WHERE state='accepted' ORDER BY position").fetchall()
            pending = con.execute("SELECT COUNT(*) FROM claims WHERE state!='accepted'").fetchone()[0]
        minted = [dict(edition=r['edition'], index=r['position'], txid=r['txid'],
                       seed=json.loads(r['response_json'])['seed'], ts=r['ts']) for r in rows]
        out = dict(col=COL, supply=SUPPLY, remaining=SUPPLY-len(rows)-pending,
                   commitment=mint['commitment'], minted=minted, pending=pending,
                   complete=len(rows)==SUPPLY)
        if out['complete']:
            out['shuffle'] = json.loads(mint['shuffle_json'])
        return out

    def _row(self, address):
        with self.db() as con:
            return con.execute('SELECT * FROM claims WHERE col=? AND address=?', (COL,address)).fetchone()

    def receipt(self, edition):
        with self.db() as con:
            row = con.execute("SELECT response_json FROM claims WHERE col=? AND edition=? AND state='accepted'", (COL,edition)).fetchone()
        if not row:
            raise MintError(404, 'edition_not_minted')
        return json.loads(row[0])

    def claim(self, address, ip):
        address_script(address)
        try:
            ip = str(ipaddress.ip_address(ip))
        except (ValueError, TypeError):
            raise MintError(400, 'missing_client_identity') from None
        if address == self.address:
            raise MintError(400, 'funding_address_not_allowed')
        with self.lock():
            row = self._row(address)
            if row and row['state'] == 'accepted':
                raise MintError(409, 'already_claimed')
            # Reconcile any older claim BEFORE touching funds or assigning an edition.
            with self.db() as con:
                pending = con.execute("SELECT * FROM claims WHERE state!='accepted'").fetchone()
            if pending:
                result = self._finish(pending)
                if pending['address'] == address:
                    return result
            with self.db() as con:
                con.execute('BEGIN IMMEDIATE')
                used = con.execute('SELECT COUNT(*) FROM claims').fetchone()[0]
                if used >= SUPPLY:
                    raise MintError(409, 'sold_out')
                rate = con.execute('SELECT COUNT(*) FROM claims WHERE ip=? AND ts>?', (ip,time.time()-86400)).fetchone()[0]
                if rate >= self.max_ip:
                    raise MintError(429, 'rate_limited')
                shuffle = json.loads(con.execute('SELECT shuffle_json FROM mints WHERE col=?', (COL,)).fetchone()[0])
                con.execute('INSERT INTO claims(col,edition,address,ts,ip,position,state) VALUES (?,?,?,?,?,?,?)',
                            (COL,shuffle[used],address,time.time(),ip,used,'reserved'))
            return self._finish(self._row(address))

    def _prepare(self, row):
        with self.db() as con:
            candidates = [dict(r) for r in con.execute('SELECT * FROM wallet')]
        picked = next((u for u in sorted(candidates, key=lambda u:-u['value']) if u['value'] >= self.fee+1), None)
        if picked is None:
            with self.db() as con:
                spent = {(u['txid'],u['vout']) for r in con.execute('SELECT inputs_json FROM claims WHERE inputs_json IS NOT NULL') for u in json.loads(r[0])}
            try:
                fetched = []
                if self.funding_txid:
                    parent = self.chain.raw(self.funding_txid)
                    if parent is None or tx.sha256d(bytes.fromhex(parent))[::-1].hex() != self.funding_txid:
                        raise ValueError('funding parent unavailable or mismatched')
                    fetched = [dict(txid=self.funding_txid, vout=i, value=value)
                               for i,(value,script) in enumerate(transaction_outputs(parent))
                               if script == self.change_script and value > 1 and (self.funding_txid,i) not in spent]
                if not fetched:
                    fetched = self.chain.utxos(self.address)
            except Exception:
                raise MintError(502, 'upstream') from None
            with self.db() as con:
                spent = {(u['txid'],u['vout']) for r in con.execute('SELECT inputs_json FROM claims WHERE inputs_json IS NOT NULL') for u in json.loads(r[0])}
                for u in fetched:
                    if (u['txid'],u['vout']) not in spent:
                        con.execute('INSERT OR IGNORE INTO wallet VALUES (?,?,?)', (u['txid'],u['vout'],u['value']))
                candidates = [dict(r) for r in con.execute('SELECT * FROM wallet')]
            picked = next((u for u in sorted(candidates, key=lambda u:-u['value']) if u['value'] >= self.fee+1), None)
        if picked is None:
            raise MintError(503, 'funding')
        cert = dict(self.templates[row['edition']])
        digest = sha256(canonical(cert)).digest()
        raw, txid = tx.build_mint_tx([picked], address_script(row['address']), digest,
                                    self.change_script, self.fee, self.priv)
        cert['mint'] = txid
        env = Envelope(target_id=0x47454E31, action=0xA47C, nonce=int(row['ts']), payload=canonical(cert))
        env.sign(self.issuer)
        response = dict(edition=row['edition'], seed=cert['seed'], cert=cert, txid=txid, envelope=env.serialize().hex())
        with self.db() as con:
            con.execute("UPDATE claims SET state='prepared',raw_tx=?,txid=?,inputs_json=?,response_json=? WHERE col=? AND edition=? AND state='reserved'",
                        (raw,txid,canonical([picked]).decode(),canonical(response).decode(),COL,row['edition']))
        return self._row(row['address'])

    def _finish(self, row):
        recovering = row['state'] == 'prepared'
        if row['state'] == 'reserved':
            row = self._prepare(row)
        raw, txid = row['raw_tx'], row['txid']
        if tx.sha256d(bytes.fromhex(raw))[::-1].hex() != txid:
            raise MintError(503, 'journal_corrupt')
        try:
            known = self.chain.raw(txid) if recovering else None
            if known is not None:
                if known.lower() != raw:
                    raise ValueError('upstream transaction mismatch')
            else:
                returned = self.chain.broadcast(raw)
                if returned != txid:
                    raise ValueError('ambiguous broadcast response')
        except Exception:
            # Never drop/reassign the reservation, select new inputs, or expose
            # signed success on timeout, rejection, mempool conflict or mismatch.
            raise MintError(503, 'pending') from None
        outputs = transaction_outputs(raw)
        with self.db() as con:
            con.execute('BEGIN IMMEDIATE')
            for u in json.loads(row['inputs_json']):
                con.execute('DELETE FROM wallet WHERE txid=? AND vout=?', (u['txid'],u['vout']))
            if len(outputs) == 3:
                value, script = outputs[2]
                if script != self.change_script:
                    raise MintError(503, 'journal_corrupt')
                con.execute('INSERT OR IGNORE INTO wallet VALUES (?,?,?)', (txid,2,value))
            con.execute("UPDATE claims SET state='accepted' WHERE col=? AND edition=?", (COL,row['edition']))
        return json.loads(row['response_json'])

    def health(self):
        status = self.status()
        with self.db() as con:
            balance = con.execute('SELECT COALESCE(SUM(value),0) FROM wallet').fetchone()[0]
        return dict(ok=True, network='main', address=self.address, issuer_pub=pubkey_hex(self.issuer),
                    accepted=SUPPLY-status['remaining']-status['pending'], pending=status['pending'],
                    wallet_cached_sats=balance, wallet_cache_is_live_balance=False,
                    commitment=status['commitment'])


class ClaimBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    address: str = Field(min_length=26, max_length=35)


def create_app(service=None):
    if service is None:
        wif = os.environ.get('MINT_WIF', '')
        seed = os.environ.get('ISSUER_SEED', '')
        # WIF decoding must not depend on assertions (which -O can remove).
        try:
            raw = tx.b58decode(wif)
            if len(raw) != 38 or raw[0] != 0x80 or raw[-5] != 1 or tx.sha256d(raw[:-4])[:4] != raw[-4:]:
                raise ValueError()
            priv = int.from_bytes(raw[1:33], 'big')
        except (ValueError, IndexError):
            raise ValueError('valid compressed mainnet MINT_WIF required') from None
        service = MintService(os.environ.get('DB_PATH', '/data/mint.db'), priv, seed, WoC(),
                              fee=int(os.environ.get('FEE_SATS','300')), max_ip=int(os.environ.get('MAX_IP_PER_DAY','3')),
                              funding_txid=os.environ.get('FUNDING_TXID') or None)
    app = FastAPI(title='sv-mint')
    app.state.mint = service
    app.add_middleware(CORSMiddleware, allow_origins=['https://svcode.org','https://www.svcode.org','https://futureman19.github.io'],
                       allow_methods=['GET','POST'], allow_headers=['Content-Type'])

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        # Do not echo submitted data: users sometimes paste secrets by mistake.
        return JSONResponse({'error':'bad_request'}, status_code=400)

    @app.exception_handler(MintError)
    async def mint_error(request, exc):
        return JSONResponse({'error':exc.error}, status_code=exc.status)

    @app.get('/health')
    def health():
        return service.health()

    def collection(col):
        if col != COL: raise MintError(404, 'unknown_collection')

    @app.get('/mint/{col}/status')
    def status(col: str):
        collection(col)
        return service.status()

    @app.post('/mint/{col}/claim')
    def claim(col: str, body: ClaimBody, request: Request):
        collection(col)
        return service.claim(body.address, request.headers.get('Fly-Client-IP'))

    @app.get('/mint/{col}/edition/{edition}')
    def receipt(col: str, edition: int):
        collection(col)
        return service.receipt(edition)

    return app
