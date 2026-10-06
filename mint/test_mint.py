import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from ecdsa import VerifyingKey, SECP256k1, util


def api():
    from mint import server
    return server


def address(n=42):
    from mint import txbuilder as tx
    return tx.address_from_pubkey(tx.compress_pub(tx.pubkey_from_priv(n)))


class Chain:
    def __init__(self):
        self.sent = []
        self.known = {}
        self.fail = False
        self.fetches = 0
        self.before_send = None

    def utxos(self, addr):
        self.fetches += 1
        return [{'txid': '12' * 32, 'vout': 0, 'value': 100000}]

    def broadcast(self, raw):
        from mint import txbuilder as tx
        if self.before_send:
            self.before_send(raw)
        self.sent.append(raw)
        txid = tx.sha256d(bytes.fromhex(raw))[::-1].hex()
        if self.fail:
            raise TimeoutError('uncertain')
        self.known[txid] = raw
        return txid

    def raw(self, txid):
        return self.known.get(txid)


@pytest.fixture(scope='session')
def templates(tmp_path_factory):
    return api().make_templates(tmp_path_factory.mktemp('art'))


@pytest.fixture
def service(tmp_path, templates):
    return api().MintService(tmp_path / 'mint.db', 7, api().DEMO_SEED, Chain(), templates=templates, max_ip=200)


def test_required_implementation():
    assert (Path(__file__).parent / 'server.py').exists(), 'Mint server not implemented'


def test_all_certificates_deterministic(templates, tmp_path):
    s = api()
    sizes = []
    for ed, cert in templates.items():
        assert cert['seed'] == hashlib.sha256(b'sv-genesis' + str(ed).encode()).digest()[:3].hex()
        assert cert['mint'] == '0' * 64
        sizes.append(len(s.canonical(cert)))
    assert len(templates) == 100
    assert max(sizes) <= 227
    assert s.make_certificate(1, tmp_path) == templates[1]
    print('all 100 certificate byte sizes:', min(sizes), max(sizes))


def test_claim_journal_signature_and_anchor(service):
    s = api()
    from mint import txbuilder as tx
    def check(raw):
        with sqlite3.connect(service.path) as con:
            row = con.execute('SELECT state,raw_tx,txid FROM claims').fetchone()
        assert row[0] == 'prepared' and row[1] == raw and len(row[2]) == 64
    service.chain.before_send = check
    result = service.claim(address(), '1.2.3.4')
    assert set(result) == {'edition', 'seed', 'cert', 'txid', 'envelope'}
    env = s.Envelope.parse(bytes.fromhex(result['envelope']))
    assert env.verify(service.issuer.verifying_key)
    assert env.target_id == 0x47454E31 and env.action == 0xA47C
    assert env.payload == s.canonical(result['cert'])
    assert result['cert']['mint'] == result['txid']
    raw = service.chain.sent[0]
    inputs, outputs = parse_tx(raw)
    assert outputs[0] == (1, s.address_script(address()))
    pre = dict(result['cert'], mint='0' * 64)
    assert outputs[1] == (0, b'\x00\x6a\x23SV2' + hashlib.sha256(s.canonical(pre)).digest())
    for i, inp in enumerate(inputs):
        script = inp['script_sig']
        sig = script[1:1+script[0]]
        pub = script[2+script[0]:]
        assert sig[-1] == 0x41
        digest = tx.sighash_forkid(inputs, outputs, i, tx.p2pkh_script(pub), 100000)
        vk = VerifyingKey.from_string(pub, curve=SECP256k1)
        assert vk.verify_digest(sig[:-1], digest, sigdecode=util.sigdecode_der)
    assert tx.sha256d(bytes.fromhex(raw))[::-1].hex() == result['txid']


def parse_tx(raw):
    b = bytes.fromhex(raw); p = 4
    def read(n):
        nonlocal p
        out = b[p:p+n]; p += n; return out
    def vi():
        v = read(1)[0]
        return v if v < 253 else int.from_bytes(read({253:2,254:4,255:8}[v]), 'little')
    inputs = []
    for _ in range(vi()):
        outpoint = read(36); script = read(vi()); sequence = read(4)
        inputs.append(dict(outpoint=outpoint, script_sig=script, sequence=sequence))
    outputs = []
    for _ in range(vi()):
        value = int.from_bytes(read(8), 'little'); script = read(vi()); outputs.append((value,script))
    assert read(4) == b'\0' * 4 and p == len(b)
    return inputs, outputs


def test_duplicate_race_and_persistent_shuffle(service, templates):
    s = api()
    other = s.MintService(service.path, 7, s.DEMO_SEED, service.chain, templates=templates, max_ip=200)
    before = service.status()
    def attempt(i):
        try:
            return (service if i % 2 else other).claim(address(), '1.2.3.4')
        except s.MintError as e:
            return e.error
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(attempt, range(6)))
    assert sum(isinstance(r, dict) for r in rows) == 1
    assert rows.count('already_claimed') == 5
    assert len(service.chain.sent) == 1
    assert other.status()['commitment'] == before['commitment']


def test_ambiguous_restart_retries_identical_and_blocks_wallet(service, templates):
    s = api(); service.chain.fail = True
    with pytest.raises(s.MintError, match='pending'):
        service.claim(address(), '1.2.3.4')
    raw = service.chain.sent[0]
    restarted = s.MintService(service.path, 7, s.DEMO_SEED, service.chain, templates=templates, max_ip=200)
    with pytest.raises(s.MintError, match='pending'):
        restarted.claim(address(43), '1.2.3.5')
    assert service.chain.fetches == 1
    assert all(r == raw for r in service.chain.sent)
    service.chain.fail = False
    result = restarted.claim(address(), '1.2.3.4')
    assert result['txid'] == s.tx.sha256d(bytes.fromhex(raw))[::-1].hex()
    assert all(r == raw for r in service.chain.sent)
    restarted.claim(address(43), '1.2.3.5')
    assert service.chain.fetches == 1, 'must spend accepted parent change, not stale address index'
    ins, _ = parse_tx(service.chain.sent[-1])
    assert ins[0]['outpoint'] == s.tx.ser_outpoint(result['txid'], 2)


def test_lookup_recovers_without_rebroadcast(service):
    s = api(); service.chain.fail = True
    with pytest.raises(s.MintError): service.claim(address(), '1.2.3.4')
    raw = service.chain.sent[0]; txid = s.tx.sha256d(bytes.fromhex(raw))[::-1].hex()
    service.chain.known[txid] = raw
    assert service.claim(address(), '1.2.3.4')['txid'] == txid
    assert len(service.chain.sent) == 1


def test_sold_out_audit_and_unique_races(service):
    s = api()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda n: service.claim(address(n+100), '1.2.3.4'), range(100)))
    state = service.status()
    assert state['remaining'] == 0 and state['pending'] == 0
    shuffle = state['shuffle']
    assert sorted(shuffle) == list(range(1,101))
    assert hashlib.sha256(s.canonical(shuffle)).hexdigest() == state['commitment']
    assert len({r['edition'] for r in results}) == 100
    for row in state['minted']:
        assert shuffle[row['index']] == row['edition']
    with pytest.raises(s.MintError, match='sold_out'):
        service.claim(address(1000), '1.2.3.4')


def test_http_validation_limits_and_health(service):
    s = api(); service.max_ip = 1
    client = TestClient(s.create_app(service))
    assert client.get('/health').json()['network'] == 'main'
    assert client.get('/mint/unknown/status').status_code == 404
    assert client.post('/mint/sv-genesis/claim', json={'address':address()}).status_code == 400
    assert client.post('/mint/sv-genesis/claim', json={'address':'bad'}, headers={'Fly-Client-IP':'1.2.3.4'}).status_code == 400
    assert client.post('/mint/sv-genesis/claim', json={'address':address()}, headers={'Fly-Client-IP':'1.2.3.4'}).status_code == 200
    assert client.post('/mint/sv-genesis/claim', json={'address':address(43)}, headers={'Fly-Client-IP':'1.2.3.4'}).status_code == 429
    assert client.post('/mint/sv-genesis/claim', json={'address':address(43)}, headers={'Fly-Client-IP':'1.2.3.5'}).status_code == 200


def test_underfunded_reservation_recovers(service):
    s = api(); original = service.chain.utxos
    service.chain.utxos = lambda a: []
    with pytest.raises(s.MintError, match='funding'):
        service.claim(address(), '1.2.3.4')
    assert not service.chain.sent
    service.chain.utxos = original
    assert service.claim(address(), '1.2.3.4')['edition']


def test_verbatim_faucet_fork():
    root = Path(__file__).parent.parent
    assert (root/'mint/txbuilder.py').read_bytes().startswith((root/'faucet/txbuilder.py').read_bytes())
