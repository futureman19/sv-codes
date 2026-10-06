"""SV Code webcam scanner.

Point a webcam at any SV Code source — the live website demo
(https://svcode.org/) or `encode.py --play` — and this
decodes the stream, verifies the BMP envelope signature, and prints the action.

Usage:
  python scanner.py                          # camera 0, report signature status
  python scanner.py --authority-pub <hex>    # require a specific authority key
  python scanner.py --demo-ok                # accept the website's zeroed demo signature
  python scanner.py --camera 1
"""

from __future__ import annotations

import argparse
import time

import cv2

from svcode.codec import Decoder
from svcode.crypto import vk_from_hex
from svcode.decode import DecodeError, decode_image
from svcode.envelope import Envelope, EnvelopeError


def describe(env: Envelope, sig_status: str) -> str:
    ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(env.nonce))
    lines = [
        "─" * 56,
        f"  ACTION     : {env.action_name} (0x{env.action:04X})",
        f"  TARGET     : 0x{env.target_id:08X}",
        f"  NONCE      : {env.nonce} ({ts})",
        f"  SIGNATURE  : {sig_status}",
    ]
    if env.payload:
        try:
            lines.append(f"  PAYLOAD    : {env.payload.decode('utf-8')}")
        except UnicodeDecodeError:
            lines.append(f"  PAYLOAD    : {env.payload.hex()} ({len(env.payload)} bytes)")
    lines.append("─" * 56)
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="SV Code webcam scanner")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--authority-pub", help="compressed pubkey hex to verify against")
    ap.add_argument("--demo-ok", action="store_true",
                    help="treat the all-zero demo signature as acceptable")
    args = ap.parse_args()

    vk = vk_from_hex(args.authority_pub) if args.authority_pub else None
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"cannot open camera {args.camera}")
        return 1

    dec = Decoder()
    last_report: str | None = None
    print("scanning… point the camera at an SV Code grid (q to quit)")
    while True:
        ok, frame = cap.read()
        if not ok:
            continue
        try:
            bits = decode_image(frame)
        except DecodeError:
            bits = None

        status = "searching for grid…"
        if bits is not None:
            content = dec.feed_bits(bits)
            prog = dec.progress()
            if content is not None:
                try:
                    env = Envelope.parse(content)
                    if env.signature == bytes(64):
                        sig = "DEMO PLACEHOLDER (zeroed)"
                        ok_sig = args.demo_ok
                    elif vk is not None:
                        ok_sig = env.verify(vk)
                        sig = "VALID ✓" if ok_sig else "INVALID ✗"
                    else:
                        ok_sig = None
                        sig = "present (no --authority-pub given, unverified)"
                    report = describe(env, sig)
                    if report != last_report:
                        print(report)
                        last_report = report
                        if ok_sig is False:
                            print("refusing to act: signature invalid")
                    status = "stream decoded"
                except EnvelopeError as e:
                    status = f"decoded stream is not a valid envelope: {e}"
            elif prog:
                status = f"collecting… {prog[0]}/{prog[1]} symbols (frame {dec.frames_seen})"

        cv2.putText(frame, status, (16, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.imshow("SV Code RX", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cap.release()
    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
