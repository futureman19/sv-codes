import json
import multiprocessing
import sqlite3

import httpx
import pytest

from mint.test_mint import api, address, Chain, parse_tx, templates, service


@pytest.mark.parametrize('outcome', ['wrong_txid', 'none', 'rejected', 'lookup_down'])
def test_fail_closed_all_ambiguous_outcomes(service, outcome):
    s = api()
    def send(raw):
        service.chain.sent.append(raw)
        if outcome == 'rejected': raise RuntimeError('txn-mempool-conflict')
        return 'ff'*32 if outcome == 'wrong_txid' else None
    service.chain.broadcast = send
    with pytest.raises(s.MintError, match='pending'):
        service.claim(address(), '1.2.3.4')
    if outcome == 'lookup_down':
        service.chain.raw = lambda _: (_ for _ in ()).throw(TimeoutError())
    with pytest.raises(s.MintError, match='pending'):
        service.claim(address(43), '1.2.3.5')
    with sqlite3.connect(service.path) as con:
        assert con.execute('SELECT COUNT(*) FROM claims').fetchone()[0] == 1
        assert con.execute('SELECT state FROM claims').fetchone()[0] == 'prepared'
    assert len(set(service.chain.sent)) == 1
    assert service.status()['pending'] == 1
    assert 'shuffle' not in service.status()


def test_crash_before_broadcast_uses_journal(service, templates):
    s = api()
    def crash(raw): raise SystemExit('simulated process death')
    service.chain.before_send = crash
    with pytest.raises(SystemExit): service.claim(address(), '1.2.3.4')
    assert not service.chain.sent
    with sqlite3.connect(service.path) as con:
        original = con.execute('SELECT raw_tx FROM claims').fetchone()[0]
    service.chain.before_send = None
    reboot = s.MintService(service.path, 7, s.DEMO_SEED, service.chain, templates=templates)
    reboot.claim(address(), '1.2.3.4')
    assert service.chain.sent == [original]


def test_crash_after_broadcast_before_accept_commit(service, templates):
    s = api(); original = service.chain.broadcast
    def accepted_then_crash(raw):
        original(raw)
        raise SystemExit('crash after network acceptance')
    service.chain.broadcast = accepted_then_crash
    with pytest.raises(SystemExit): service.claim(address(), '1.2.3.4')
    reboot = s.MintService(service.path, 7, s.DEMO_SEED, service.chain, templates=templates)
    reboot.claim(address(), '1.2.3.4')
    assert len(service.chain.sent) == 1
    assert reboot.status()['pending'] == 0


def _process_claim(path, queue):
    s = api()
    try:
        svc = s.MintService(path, 7, s.DEMO_SEED, Chain())
        svc.claim(address(), '1.2.3.4')
        queue.put('accepted')
    except s.MintError as e:
        queue.put(e.error)


def test_cross_process_reservation_lock(service):
    ctx = multiprocessing.get_context('spawn')
    queue = ctx.Queue()
    workers = [ctx.Process(target=_process_claim, args=(str(service.path), queue)) for _ in range(4)]
    for p in workers: p.start()
    rows = [queue.get(timeout=30) for _ in workers]
    for p in workers:
        p.join(timeout=30)
        assert p.exitcode == 0
    assert rows.count('accepted') == 1
    assert rows.count('already_claimed') == 3


def test_key_rotation_and_self_mint_rejected(service, templates):
    s = api()
    with pytest.raises(ValueError, match='binding changed'):
        s.MintService(service.path, 8, s.DEMO_SEED, Chain(), templates=templates)
    with pytest.raises(ValueError, match='binding changed'):
        s.MintService(service.path, 7, 'different issuer', Chain(), templates=templates)
    with pytest.raises(s.MintError, match='funding_address_not_allowed'):
        service.claim(service.address, '1.2.3.4')


def test_missing_edge_identity_never_falls_back(service):
    from fastapi.testclient import TestClient
    client = TestClient(api().create_app(service))
    response = client.post('/mint/sv-genesis/claim', json={'address': address()}, headers={'X-Forwarded-For':'1.2.3.4'})
    assert response.status_code == 400
    assert response.json()['error'] == 'missing_client_identity'
    assert not service.chain.sent


def test_woc_adapter_urls_and_confirmed_funding_only():
    s = api(); calls = []
    def handler(req):
        calls.append(req.url.path)
        if req.url.path.endswith('/unspent/all'):
            return httpx.Response(200, json={'result':[
                {'tx_hash':'12'*32, 'tx_pos':0, 'value':1000, 'height':800000},
                {'tx_hash':'13'*32, 'tx_pos':0, 'value':1000, 'height':0}]})
        if req.method == 'POST':
            assert json.loads(req.content) == {'txhex':'abcd'}
            return httpx.Response(200, json='aa'*32)
        return httpx.Response(404)
    woc = s.WoC()
    woc.client.close()
    woc.client = httpx.Client(base_url='https://api.whatsonchain.com/v1/bsv/main', transport=httpx.MockTransport(handler))
    assert len(woc.utxos(address())) == 1
    assert woc.raw('aa'*32) is None
    assert woc.broadcast('abcd') == 'aa'*32
    assert all(p.startswith('/v1/bsv/main/') for p in calls)
    woc.client.close()


def test_real_http_server_smoke(service):
    import socket
    import threading
    import time
    import uvicorn
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    runner = uvicorn.Server(uvicorn.Config(api().create_app(service), log_level='error', access_log=False))
    thread = threading.Thread(target=runner.run, kwargs={'sockets':[sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not runner.started and time.monotonic() < deadline:
            time.sleep(0.01)
        assert runner.started
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', timeout=10) as client:
            assert client.get('/health').status_code == 200
            assert client.get('/mint/sv-genesis/status').json()['remaining'] == 100
            result = client.post('/mint/sv-genesis/claim', json={'address':address()}, headers={'Fly-Client-IP':'1.2.3.4'})
            assert result.status_code == 200
            assert api().Envelope.parse(bytes.fromhex(result.json()['envelope'])).verify(service.issuer.verifying_key)
            assert client.get('/mint/sv-genesis/status').json()['remaining'] == 99
    finally:
        runner.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


def test_public_receipt_after_lost_http_response(service):
    from fastapi.testclient import TestClient
    client = TestClient(api().create_app(service))
    receipt = service.claim(address(), '1.2.3.4')
    duplicate = client.post('/mint/sv-genesis/claim', json={'address':address()}, headers={'Fly-Client-IP':'1.2.3.4'})
    assert duplicate.status_code == 409
    recovered = client.get(f"/mint/sv-genesis/edition/{receipt['edition']}")
    assert recovered.status_code == 200 and recovered.json() == receipt
    assert client.get('/mint/sv-genesis/edition/101').status_code == 404
    assert len(service.chain.sent) == 1
    service.chain.fail = True
    with pytest.raises(api().MintError): service.claim(address(43), '1.2.3.5')
    with sqlite3.connect(service.path) as con:
        pending = con.execute("SELECT edition FROM claims WHERE state='prepared'").fetchone()[0]
    assert client.get(f'/mint/sv-genesis/edition/{pending}').status_code == 404


def test_explicit_unconfirmed_funding_parent(service, templates):
    s = api()
    pub = s.tx.compress_pub(s.tx.pubkey_from_priv(9))
    raw, txid = s.tx.build_tx([{'txid':'ab'*32,'vout':0,'value':60000}],
                              service.change_script, 50000, s.tx.p2pkh_script(pub), 300, 9)
    service.chain.known[txid] = raw
    reboot = s.MintService(service.path, 7, s.DEMO_SEED, service.chain, templates=templates, funding_txid=txid)
    result = reboot.claim(address(), '1.2.3.4')
    assert result['edition']
    assert service.chain.fetches == 0
    ins, _ = parse_tx(service.chain.sent[0])
    assert ins[0]['outpoint'] == s.tx.ser_outpoint(txid, 0)


def test_no_change_output_and_multiple_input_signatures():
    from ecdsa import SECP256k1, VerifyingKey, util
    s = api(); tx = s.tx
    pub = tx.compress_pub(tx.pubkey_from_priv(7))
    inputs = [{'txid':'aa'*32,'vout':1,'value':100}, {'txid':'bb'*32,'vout':2,'value':201}]
    raw, _ = tx.build_mint_tx(inputs, s.address_script(address()), bytes(32), tx.p2pkh_script(pub), 300, 7)
    ins, outs = parse_tx(raw)
    assert len(outs) == 2
    vk = VerifyingKey.from_string(pub, curve=SECP256k1)
    for i, inp in enumerate(ins):
        script = inp['script_sig']; sig = script[1:1+script[0]]
        digest = tx.sighash_forkid(ins, outs, i, tx.p2pkh_script(pub), inputs[i]['value'])
        assert vk.verify_digest(sig[:-1], digest, sigdecode=util.sigdecode_der)
