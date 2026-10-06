import argparse
import base64
import json
import sys
from pathlib import Path
from .decoder import decode_bytes, DecodeFailure, MAX_BYTES


def main():
    parser = argparse.ArgumentParser(description='Offline SV Code decoder / Telegram service')
    parser.add_argument('command', choices=['decode', 'serve', '_worker'])
    parser.add_argument('image', nargs='?')
    args = parser.parse_args()
    if args.command == 'serve':
        from .service import run
        run()
        return
    try:
        if args.command == '_worker':
            data = sys.stdin.buffer.read(MAX_BYTES + 1)
        else:
            if not args.image: parser.error('decode requires an image path')
            with Path(args.image).open('rb') as handle:
                data = handle.read(MAX_BYTES + 1)
        result = decode_bytes(data)
        if args.command == '_worker':
            print(json.dumps({'text': result.text, 'trusted_claim': result.trusted_claim,
                              'reveal': base64.b64encode(result.reveal).decode() if result.reveal else None}))
        else:
            print(result.text)
            print('Reveal generated in memory:', bool(result.reveal))
    except (DecodeFailure, OSError) as exc:
        message = str(exc) if isinstance(exc, DecodeFailure) else 'Cannot read input image.'
        if args.command == '_worker': print(json.dumps({'error': message}))
        else: parser.exit(1, message + '\n')

if __name__ == '__main__': main()
