"""Single-worker long polling; offset is reserved BEFORE work (at-most-once)."""
import base64
import json
import logging
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time
import httpx
from .decoder import MAX_BYTES, DecodeFailure, Result, MINT_LINK, SCAN_LINK

HELP = ('Send a photo or PNG/JPEG document containing a static SV Code. Original files work best. '
        'Limit: 8 MiB, 16 MP, 8192 pixels per side. Demo signatures do not prove ownership or chain confirmation. '
        'This bot never claims, spends, or opens payload URLs. Images are processed in memory and not retained.')
BUTTONS = {'inline_keyboard': [[{'text': 'Scanner', 'url': SCAN_LINK}]]}

class APIError(Exception):
    def __init__(self, retry_after=3):
        super().__init__('Telegram request failed')
        self.retry_after = max(1, min(60, retry_after))

class Telegram:
    def __init__(self, token, client=None):
        if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token):
            raise ValueError('Invalid dedicated Telegram token format')
        self.base = 'https://api.telegram.org/bot' + token + '/'
        self.files = 'https://api.telegram.org/file/bot' + token + '/'
        self.client = client or httpx.Client(timeout=httpx.Timeout(40, connect=5, write=10, pool=5),
                                             follow_redirects=False, trust_env=False)

    def request(self, method, data, files=None):
        try:
            if files:
                response = self.client.post(self.base + method, data=data, files=files, follow_redirects=False)
            else:
                response = self.client.post(self.base + method, json=data, follow_redirects=False)
            body = response.json()
            if response.status_code != 200 or not isinstance(body, dict) or body.get('ok') is not True:
                retry = body.get('parameters', {}).get('retry_after', 3) if isinstance(body, dict) else 3
                raise APIError(retry if type(retry) is int else 3)
            return body['result']
        except APIError:
            raise
        except Exception:
            raise APIError() from None

    def download(self, file_id):
        meta = self.request('getFile', {'file_id': file_id})
        if not isinstance(meta, dict):
            raise DecodeFailure('Invalid Telegram file metadata.')
        path = meta.get('file_path', '')
        # Relative Telegram image directories only. Reject URL, %, ?, #, .., backslash.
        if not isinstance(path, str) or not re.fullmatch(r'(?:photos|documents)/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png)', path):
            raise DecodeFailure('Unsupported Telegram file path.')
        size = meta.get('file_size', 0)
        if type(size) is not int or not 0 <= size <= MAX_BYTES:
            raise DecodeFailure('Image exceeds 8 MiB.')
        try:
            with self.client.stream('GET', self.files + path, timeout=15, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise APIError()
                length = response.headers.get('content-length')
                if length is not None and (not length.isdecimal() or int(length) > MAX_BYTES):
                    raise DecodeFailure('Image exceeds 8 MiB.')
                data = bytearray()
                deadline = time.monotonic() + 25
                for chunk in response.iter_bytes(65536):
                    if time.monotonic() > deadline:
                        raise DecodeFailure('Download timed out.')
                    if len(data) + len(chunk) > MAX_BYTES:
                        raise DecodeFailure('Image exceeds 8 MiB.')
                    data.extend(chunk)
                return bytes(data)
        except (APIError, DecodeFailure):
            raise
        except Exception:
            raise APIError() from None

    def send(self, chat_id, result):
        buttons = BUTTONS
        if result.trusted_claim:
            buttons = {'inline_keyboard': [[{'text': 'Mint information', 'url': MINT_LINK},
                                            {'text': 'Scanner', 'url': SCAN_LINK}]]}
        self.request('sendMessage', {'chat_id': chat_id, 'text': result.text[:3500],
                                    'link_preview_options': {'is_disabled': True}, 'reply_markup': buttons})
        if result.reveal:
            self.request('sendPhoto', {'chat_id': str(chat_id),
                                      'caption': 'Locally rendered demo reveal. Not proof of ownership or chain confirmation.'},
                         files={'photo': ('reveal.png', result.reveal, 'image/png')})


class State:
    def __init__(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), offset INTEGER NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS rate (user INTEGER PRIMARY KEY, last REAL NOT NULL)')
        self.db.commit()

    @property
    def offset(self):
        row = self.db.execute('SELECT offset FROM state WHERE id=1').fetchone()
        return row[0] if row else None

    def advance(self, offset):
        with self.db:
            self.db.execute('INSERT INTO state VALUES(1,?) ON CONFLICT(id) DO UPDATE SET offset=max(offset,excluded.offset)', (offset,))

    def permit(self, user, now):
        with self.db:
            self.db.execute('DELETE FROM rate WHERE last < ?', (now-60,))
            row = self.db.execute('SELECT last FROM rate WHERE user=?', (user,)).fetchone()
            if row and now-row[0] < 10:
                return False
            # Hard cap state cardinality as well as TTL.
            if not row and self.db.execute('SELECT count(*) FROM rate').fetchone()[0] >= 10000:
                return False
            self.db.execute('INSERT INTO rate VALUES(?,?) ON CONFLICT(user) DO UPDATE SET last=excluded.last', (user, now))
        return True


def worker_environment():
    """Only runtime OS essentials; never inherit credentials or Python injection knobs."""
    allowed = {'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'PATH', 'TEMP', 'TMP', 'TMPDIR'}
    env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    return env


def bounded_decode(data):
    try:
        proc = subprocess.run([sys.executable, '-B', '-m', 'telegram_bot', '_worker'], input=data,
                              capture_output=True, timeout=20, cwd=Path(__file__).resolve().parents[1],
                              env=worker_environment())
        if proc.returncode or len(proc.stdout) > 2_000_000:
            raise DecodeFailure('Image could not be decoded within the processing limit.')
        value = json.loads(proc.stdout)
        if 'error' in value:
            raise DecodeFailure(value['error'])
        return Result(value['text'], value['trusted_claim'], base64.b64decode(value['reveal']) if value['reveal'] else None)
    except DecodeFailure:
        raise
    except Exception:
        raise DecodeFailure('Image processing failed or timed out.') from None


class Bot:
    def __init__(self, api, state, allowed_chats=(), decoder=bounded_decode):
        self.api, self.state = api, state
        self.allowed_chats = set(allowed_chats)
        self.decoder = decoder

    def process(self, update):
        msg = update.get('message')
        if not isinstance(msg, dict): return
        sender, chat = msg.get('from'), msg.get('chat')
        if not isinstance(sender, dict) or not isinstance(chat, dict): return
        uid, cid = sender.get('id'), chat.get('id')
        if type(uid) is not int or type(cid) is not int: return
        if (sender.get('is_bot') is not False or chat.get('type') != 'private') and cid not in self.allowed_chats: return
        if not self.state.permit(uid, time.time()): return
        text = msg.get('text', '')
        if isinstance(text, str) and text.split(' ', 1)[0].split('@', 1)[0] in ('/start', '/help'):
            self.api.send(cid, Result(HELP)); return
        candidates = msg.get('photo')
        media = None
        if isinstance(candidates, list):
            valid = [p for p in candidates if isinstance(p, dict) and type(p.get('width')) is int and type(p.get('height')) is int]
            if valid: media = max(valid, key=lambda p: p['width']*p['height'])
        elif isinstance(msg.get('document'), dict):
            doc = msg['document']
            if doc.get('mime_type') in ('image/png', 'image/jpeg'): media = doc
        if media is None:
            self.api.send(cid, Result('Please send a photo or PNG/JPEG document. /help for limits.')); return
        size, fid = media.get('file_size', 0), media.get('file_id')
        if type(size) is not int or not 0 <= size <= MAX_BYTES or not isinstance(fid, str) or not 1 <= len(fid) <= 512:
            self.api.send(cid, Result('Invalid file or image exceeds 8 MiB.')); return
        try:
            result = self.decoder(self.api.download(fid))
        except DecodeFailure as exc:
            result = Result(str(exc))  # only our fixed, sanitized messages
        self.api.send(cid, result)

    def poll(self):
        if self.state.offset is None:
            # New DB intentionally discards the entire existing backlog, retaining no startup images.
            updates = self.api.request('getUpdates', {'offset': -1, 'limit': 1, 'timeout': 0, 'allowed_updates': ['message']})
            if not isinstance(updates, list): raise APIError()
            ids = [u['update_id'] for u in updates if isinstance(u, dict) and type(u.get('update_id')) is int]
            self.state.advance(max(ids)+1 if ids else 0)
            return
        updates = self.api.request('getUpdates', {'offset': self.state.offset, 'limit': 10, 'timeout': 25, 'allowed_updates': ['message']})
        if not isinstance(updates, list): raise APIError()
        for update in updates[:10]:
            if not isinstance(update, dict) or type(update.get('update_id')) is not int: continue
            uid = update['update_id']
            if uid < self.state.offset: continue
            self.state.advance(uid + 1)  # crash may lose ONE response, never replay it
            try:
                self.process(update)
            except APIError as exc:
                logging.warning('Telegram update delivery failed; not replaying')
                time.sleep(exc.retry_after)
            except Exception:
                logging.warning('Malformed update or local processing failure; skipped')


def run():
    # httpx INFO logging includes the token in request URLs. Never enable it here.
    logging.getLogger('httpx').disabled = True
    logging.getLogger('httpcore').disabled = True
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    if not token:
        raise SystemExit('Launch blocked: dedicated BotFather token absent (TELEGRAM_BOT_TOKEN).')
    try:
        allowed = {int(v) for v in os.environ.get('TELEGRAM_ALLOWED_CHAT_IDS', '').split(',') if v.strip()}
        api = Telegram(token)
        state = State(os.environ.get('TELEGRAM_STATE_DB', 'telegram_bot/state/offset.sqlite3'))
    except Exception:
        raise SystemExit('Invalid bot configuration; check token format, chat IDs, and writable state path.') from None
    try:
        identity = api.request('getMe', {})
        expected = os.environ.get('TELEGRAM_EXPECTED_USERNAME', 'svcodesbot')
        if (not isinstance(identity, dict) or identity.get('is_bot') is not True
                or identity.get('username', '').lower() != expected.lower()):
            raise SystemExit('Bot identity mismatch; polling refused.')
        webhook = api.request('getWebhookInfo', {})
        if not isinstance(webhook, dict) or webhook.get('url'):
            raise SystemExit('Existing webhook or invalid webhook status; polling refused.')
    except APIError:
        raise SystemExit('Telegram startup verification failed; details suppressed.') from None
    print('Verified dedicated bot @' + expected + '; starting single-worker polling.', flush=True)
    bot = Bot(api, state, allowed)
    try:
        while True:
            try:
                bot.poll()
            except APIError as exc:
                logging.warning('Telegram polling failed; retrying without request details')
                time.sleep(exc.retry_after)
    finally:
        api.client.close()
        state.db.close()
