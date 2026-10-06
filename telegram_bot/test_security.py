"""Security / lifecycle tests. ALL Telegram requests are httpx MockTransport fixtures.
No Telegram credentials, live API, mint requests, or blockchain transactions.
"""
import io
import json
from pathlib import Path
import subprocess
import sys
import httpx
import pytest
from PIL import Image
from telegram_bot import decoder as dec
from telegram_bot.decoder import ROOT, DecodeFailure, Result, describe, decode_bytes
from telegram_bot.service import Telegram, APIError, State, Bot, bounded_decode
from svcode.codec import Encoder
from svcode.envelope import Envelope
from svcode.render import render_frame

MASTER = ROOT / 'docs/nft/genesis/mint/mint-master-code.png'
RECEIPT = ROOT / 'docs/nft/genesis/genesis-052-receipt.json'
RAW = bytes.fromhex(json.loads(RECEIPT.read_text())['envelope'])
TOKEN_FIXTURE = '123456:MOCK_TOKEN_NOT_A_CREDENTIAL'


def test_renderer_exact_existing_artifact():
    # PNG compression varies by Pillow/zlib version; canonical pixels must match.
    actual = Image.open(io.BytesIO(decode_bytes((ROOT/'docs/nft/genesis/genesis-052-code.png').read_bytes()).reveal))
    with Image.open(ROOT/'docs/nft/genesis/genesis-052-reveal.png') as expected:
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()


def test_worker_real_image():
    assert bounded_decode(MASTER.read_bytes()).trusted_claim


def test_unknown_signature_real_image():
    raw = bytearray(RAW); raw[21:85] = b'\xff' * 64
    bits = Encoder(bytes(raw)).frame_bits(0)[1]
    out = io.BytesIO(); render_frame(bits, scale=16).save(out, format='PNG')
    result = decode_bytes(out.getvalue())
    assert 'UNKNOWN' in result.text
    assert result.reveal is None and not result.trusted_claim
    assert 'https://whatsonchain' not in result.text


def test_tampered_envelope():
    raw = RAW.replace(b'"ed":52', b'"ed":53')
    assert 'UNKNOWN' in describe(raw).text


@pytest.mark.parametrize('size', [(8193, 1), (4001, 4000)])
def test_dimensions_guard_before_cv2(monkeypatch, size):
    out = io.BytesIO(); Image.new('RGB', size).save(out, format='PNG')
    monkeypatch.setattr(dec.cv2, 'imdecode', lambda *_: pytest.fail('cv2 called before guard'))
    with pytest.raises(DecodeFailure): decode_bytes(out.getvalue())


def test_non_png_jpeg():
    out = io.BytesIO(); Image.new('RGB', (10, 10)).save(out, format='GIF')
    with pytest.raises(DecodeFailure): decode_bytes(out.getvalue())


@pytest.mark.parametrize('change', [{'endpoint': 'https://evil.example'}, {'endpoint': 'https://sv-mint.fly.dev/'},
                                   {'v': 2}, {'price': 1}, {'price': False}, {'supply': 99}, {'exp': 1},
                                   {'col': 'evil'}, {'extra': 'field'}])
def test_exact_claim_gate_policy_fixture(monkeypatch, change):
    # Explicit mock verification isolates policy gates, NOT a signed fixture.
    cert = {'v': 3, 'col': 'sv-genesis', 'supply': 100, 'price': 0, 'exp': 0, 'endpoint': 'https://sv-mint.fly.dev'}
    cert.update(change)
    monkeypatch.setattr(Envelope, 'verify', lambda *_: True)
    env = Envelope(0x47454E31, 0xC1A1, payload=json.dumps(cert, sort_keys=True, separators=(',', ':')).encode())
    assert not describe(env.serialize()).trusted_claim


@pytest.mark.parametrize('target,action,params', [(1, 0xC1A1, bytes(8)), (0x47454E31, 1, bytes(8)), (0x47454E31, 0xC1A1, b'1'*8)])
def test_claim_header_policy_fixture(monkeypatch, target, action, params):
    cert = json.loads((ROOT/'docs/nft/genesis/mint/mint-master-cert.json').read_text())['cert']
    monkeypatch.setattr(Envelope, 'verify', lambda *_: True)
    assert not describe(Envelope(target, action, params=params, payload=json.dumps(cert, sort_keys=True, separators=(',', ':')).encode()).serialize()).trusted_claim


def make_api(handler):
    return Telegram(TOKEN_FIXTURE, httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False))


@pytest.mark.parametrize('path', ['https://evil/a.png', '//evil/a.jpg', '../file.png', 'photos/../a.png',
                                'photos/%2e%2e.png', 'photos/a.png?x=1', 'photos/a.png#x', 'photos\\a.png'])
def test_download_path_rejected(path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'ok': True, 'result': {'file_path': path}})
    with pytest.raises(DecodeFailure): make_api(handler).download('mock-file')
    assert len(calls) == 1


def test_mock_download_send_real_decode():
    calls = []
    def handler(req):
        calls.append(req)
        if req.url.path.endswith('/getFile'):
            return httpx.Response(200, json={'ok': True, 'result': {'file_path': 'photos/mock.png'}})
        if '/file/' in req.url.path: return httpx.Response(200, content=MASTER.read_bytes())
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1}})
    api = make_api(handler)
    api.send(1, decode_bytes(api.download('mock-id')))
    body = json.loads(calls[-1].content)
    assert 'parse_mode' not in body and body['link_preview_options']['is_disabled']
    urls = [b['url'] for row in body['reply_markup']['inline_keyboard'] for b in row]
    assert set(urls) == {dec.SCAN_LINK, dec.MINT_LINK}


def test_mock_send_reveal():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200, json={'ok': True, 'result': {}})
    make_api(handler).send(1, decode_bytes((ROOT/'docs/nft/genesis/genesis-052-code.png').read_bytes()))
    assert calls[-1].url.path.endswith('/sendPhoto')
    assert b'filename="reveal.png"' in calls[-1].content


@pytest.mark.parametrize('kind', ['redirect', 'declared', 'streamed'])
def test_download_bounds_and_redirect(kind):
    def handler(req):
        if req.url.path.endswith('/getFile'):
            return httpx.Response(200, json={'ok': True, 'result': {'file_path': 'documents/mock.png'}})
        if kind == 'redirect': return httpx.Response(302, headers={'location': 'https://evil.example'})
        if kind == 'declared': return httpx.Response(200, headers={'content-length': str(dec.MAX_BYTES+1)}, content=b'')
        return httpx.Response(200, content=b'x'*(dec.MAX_BYTES+1), headers={'content-length': '1'})
    with pytest.raises((APIError, DecodeFailure)): make_api(handler).download('mock')


def test_exception_redacted():
    def handler(req): raise httpx.ConnectError(str(req.url))
    with pytest.raises(APIError) as exc: make_api(handler).request('getUpdates', {})
    assert TOKEN_FIXTURE not in str(exc.value)
    assert exc.value.__suppress_context__


def test_api_retry_after_bounded():
    api = make_api(lambda _: httpx.Response(429, json={'ok': False, 'parameters': {'retry_after': 99999}}))
    with pytest.raises(APIError) as exc: api.request('getUpdates', {})
    assert exc.value.retry_after == 60


class MockAPI:
    """Pure MOCK Telegram fixture, never performs network I/O."""
    def __init__(self, batches=()): self.batches = iter(batches); self.sent = []; self.ids = []; self.requests = []
    def request(self, method, data): self.requests.append((method, data)); return next(self.batches)
    def download(self, fid): self.ids.append(fid); return MASTER.read_bytes()
    def send(self, cid, result): self.sent.append((cid, result))


def message(uid=1, cid=1, kind='private', bot=False):
    return {'message': {'from': {'id': uid, 'is_bot': bot}, 'chat': {'id': cid, 'type': kind},
                        'photo': [{'file_id': 'small', 'width': 20, 'height': 20},
                                  {'file_id': 'large', 'width': 100, 'height': 100}]}}


@pytest.fixture
def state(tmp_path):
    value = State(str(tmp_path/'state.sqlite3'))
    yield value
    value.db.close()


def test_photo_selection_rate_limit(state):
    api = MockAPI(); bot = Bot(api, state, decoder=lambda _: Result('mock decode'))
    bot.process(message()); bot.process(message())
    assert api.ids == ['large'] and len(api.sent) == 1


@pytest.mark.parametrize('kind,botflag', [('group', False), ('supergroup', False), ('private', True)])
def test_default_rejects_groups_and_bots(state, kind, botflag):
    api = MockAPI(); Bot(api, state).process(message(kind=kind, bot=botflag))
    assert not api.ids and not api.sent


def test_allowlist_group(state):
    api = MockAPI(); Bot(api, state, allowed_chats={-9}, decoder=lambda _: Result('mock')).process(message(cid=-9, kind='group'))
    assert api.ids == ['large']


@pytest.mark.parametrize('text', ['/start', '/help', '/help@mockbot'])
def test_commands(state, text):
    api = MockAPI(); msg = message(); msg['message']['text'] = text
    Bot(api, state).process(msg)
    assert 'never claims' in api.sent[0][1].text and not api.ids


@pytest.mark.parametrize('document', [{'mime_type': 'application/pdf', 'file_id': 'mock'},
                                    {'mime_type': 'image/png', 'file_id': 'mock', 'file_size': dec.MAX_BYTES+1},
                                    {'mime_type': 'image/jpeg', 'file_id': None}])
def test_malformed_document(state, document):
    api = MockAPI(); msg = message(); del msg['message']['photo']; msg['message']['document'] = document
    Bot(api, state).process(msg)
    assert not api.ids


def test_poll_bootstrap_offset_duplicates_and_restart(tmp_path):
    path = str(tmp_path/'offset.sqlite3'); state = State(path)
    u = dict(message(), update_id=102)
    api = MockAPI([[dict(message(), update_id=100)], [u, u, {'update_id': 103, 'message': None}], []])
    bot = Bot(api, state, decoder=lambda _: Result('mock'))
    bot.poll(); assert state.offset == 101 and not api.ids
    bot.poll(); assert state.offset == 104 and api.ids == ['large']
    state.db.close(); state = State(path)
    assert state.offset == 104
    Bot(api, state).poll()
    assert api.requests[-1][1]['offset'] == 104
    state.db.close()


def test_offset_reserved_before_processing(state):
    state.advance(10)
    api = MockAPI([[dict(message(), update_id=10)]])
    def decode(_):
        assert state.offset == 11
        raise RuntimeError('mock failure')
    Bot(api, state, decoder=decode).poll()
    assert state.offset == 11


def test_worker_timeout(monkeypatch):
    def timeout(*args, **kwargs): raise subprocess.TimeoutExpired('mock', 20)
    monkeypatch.setattr(subprocess, 'run', timeout)
    with pytest.raises(DecodeFailure, match='timed out'): bounded_decode(b'mock')


def test_worker_environment_excludes_secrets(monkeypatch):
    from telegram_bot.service import worker_environment
    monkeypatch.setenv('TELEGRAM_BOT_TOKEN', TOKEN_FIXTURE)
    monkeypatch.setenv('UNRELATED_SECRET_KEY', 'MOCK_SECRET')
    monkeypatch.setenv('PYTHONPATH', 'MOCK_INJECTION')
    child = subprocess.run([sys.executable, '-B', '-c',
                            'import os,json; print(json.dumps(sorted(os.environ)))'],
                           env=worker_environment(), capture_output=True, text=True, check=True)
    keys = json.loads(child.stdout)
    assert 'TELEGRAM_BOT_TOKEN' not in keys and 'UNRELATED_SECRET_KEY' not in keys
    assert 'PYTHONPATH' not in keys
    original_run = subprocess.run
    def checked_run(*args, **kwargs):
        assert 'TELEGRAM_BOT_TOKEN' not in kwargs['env']
        assert 'UNRELATED_SECRET_KEY' not in kwargs['env']
        return original_run(*args, **kwargs)
    monkeypatch.setattr(subprocess, 'run', checked_run)
    assert bounded_decode(MASTER.read_bytes()).trusted_claim


@pytest.mark.parametrize('variant', ['spaces', 'order', 'oversize', 'duplicate'])
def test_noncanonical_claim_rejected_policy_fixture(monkeypatch, variant):
    cert = json.loads((ROOT/'docs/nft/genesis/mint/mint-master-cert.json').read_text())['cert']
    canonical = json.dumps(cert, sort_keys=True, separators=(',', ':')).encode()
    payload = {'spaces': json.dumps(cert).encode(),
               'order': json.dumps(dict(reversed(list(cert.items()))), separators=(',', ':')).encode(),
               'oversize': canonical + b' ' * 228,
               'duplicate': canonical[:-1] + b',"v":3}'}[variant]
    assert json.loads(payload) == cert  # equal parsed data is deliberately insufficient
    monkeypatch.setattr(Envelope, 'verify', lambda *_: True)
    assert not describe(Envelope(0x47454E31, 0xC1A1, payload=payload).serialize()).trusted_claim


def test_untrusted_plain_payload_no_active_links():
    env = Envelope(1, 1, payload=b'<b>fake</b> https://evil.example @victim')
    result = describe(env.serialize())
    assert 'https://' not in result.text and '@victim' not in result.text and len(result.text) <= 3500
