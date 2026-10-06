"""Real artifact decoding; all Telegram traffic below uses MOCK fixtures only."""
import io
import json
from pathlib import Path
import pytest
from PIL import Image
from telegram_bot.decoder import decode_bytes, DecodeFailure, ROOT

@pytest.mark.parametrize('stem', ['mint/mint-master', 'genesis-052'])
@pytest.mark.parametrize('ext', ['png', 'jpg'])
def test_real_images(stem, ext):
    result = decode_bytes((ROOT / 'docs/nft/genesis' / f'{stem}-code.{ext}').read_bytes())
    assert 'SV-GENESIS (demo)' in result.text
    assert 'not proof of ownership' in result.text
    if 'master' in stem:
        assert result.trusted_claim and result.reveal is None
    else:
        assert '52 / 100' in result.text and 'f8ef2a' in result.text
        assert result.reveal.startswith(b'\x89PNG')

@pytest.mark.parametrize('data', [b'broken', b'', b'X' * (8*1024*1024+1)], ids=['corrupt', 'empty', 'oversize'])
def test_bad_bytes(data):
    with pytest.raises(DecodeFailure): decode_bytes(data)

def test_blank_image():
    out = io.BytesIO(); Image.new('RGB', (200, 200)).save(out, format='PNG')
    with pytest.raises(DecodeFailure): decode_bytes(out.getvalue())
