"""SV Code transmitter CLI.

Usage:
  python encode.py "HELLO, MACHINE." --out frame.png        # static PNG (K<=10)
  python encode.py "big message..." --dir frames/           # PNG sequence
  python encode.py "HELLO, MACHINE." --play                 # on-screen player (12 fps)

Signs the BMP envelope with --key <hex> (default: deterministic PoC demo key
printed on stdout — do not use for anything real).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from svcode.codec import Encoder
from svcode.crypto import generate_key, key_from_hex, pubkey_hex, sha256
from svcode.envelope import Envelope
from svcode.render import render_frame

DEMO_KEY_SEED = b"svcode poc demo authority key (not for production)"


def demo_key():
    return key_from_hex(sha256(DEMO_KEY_SEED).hex())


def main() -> int:
    ap = argparse.ArgumentParser(description="SV Code transmitter")
    ap.add_argument("message", help="UTF-8 text payload (vendor action 0x00FF)")
    ap.add_argument("--key", help="authority private key hex (default: PoC demo key)")
    ap.add_argument("--target", default="0x53564331", help="Target_ID hex (default 'SVC1')")
    ap.add_argument("--out", help="write a single static frame PNG here")
    ap.add_argument("--dir", help="write an animated frame sequence (PNG) here")
    ap.add_argument("--frames", type=int, default=8, help="frames to dump with --dir")
    ap.add_argument("--scale", type=int, default=10, help="pixels per cell (default 10)")
    ap.add_argument("--play", action="store_true", help="play the stream in a window at 12 fps")
    args = ap.parse_args()

    sk = key_from_hex(args.key) if args.key else demo_key()
    env = Envelope(target_id=int(args.target, 16), action=0x00FF, payload=args.message.encode())
    env.sign(sk)
    enc = Encoder(env.serialize())

    print(f"authority pubkey : {pubkey_hex(sk)}")
    print(f"envelope bytes   : {len(env.serialize())}")
    print(f"stream bytes     : {len(enc.stream)}  (K={enc.k} symbols)")
    print(f"mode             : {'STATIC (seed 0)' if enc.static else 'FOUNTAIN'}")

    if args.out:
        if not enc.static:
            print("warning: payload exceeds static mode; writing frame seed=1", file=sys.stderr)
        seed, bits = enc.frame_bits(0)
        render_frame(bits, scale=args.scale).save(args.out)
        print(f"wrote {args.out} (seed={seed})")
    if args.dir:
        Path(args.dir).mkdir(parents=True, exist_ok=True)
        n = 1 if enc.static else args.frames
        for i in range(n):
            seed, bits = enc.frame_bits(i)
            render_frame(bits, scale=args.scale).save(Path(args.dir) / f"frame_{seed:05d}.png")
        print(f"wrote {n} frame(s) to {args.dir}/")
    if args.play:
        import cv2
        import numpy as np

        i = 0
        print("playing at ~12 fps — press q to quit")
        while True:
            seed, bits = enc.frame_bits(i)
            img = np.array(render_frame(bits, scale=args.scale))[:, :, ::-1]  # RGB->BGR
            cv2.imshow("SV Code TX", img)
            if cv2.waitKey(83) & 0xFF == ord("q"):
                break
            i += 1
            if enc.static:
                time.sleep(0.083)
        cv2.destroyAllWindows()
    if not (args.out or args.dir or args.play):
        print("nothing to do: pass --out, --dir, or --play", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
