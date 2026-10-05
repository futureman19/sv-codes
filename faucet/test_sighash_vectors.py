"""test_sighash_vectors.py — validate txbuilder.sighash_forkid against Bitcoin ABC's
independent test vectors (src/test/data/sighash.json, amount=0, forkid entries)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import txbuilder as tx

JSON_PATH = os.environ.get("SIGHASH_JSON", os.path.join(os.environ.get("TMPDIR", "."), "sighash.json"))

def rd_varint(b, off):
    n = b[off]; off += 1
    if n < 0xFD: return n, off
    if n == 0xFD: return int.from_bytes(b[off:off+2], "little"), off + 2
    if n == 0xFE: return int.from_bytes(b[off:off+4], "little"), off + 4
    return int.from_bytes(b[off:off+8], "little"), off + 8

def parse_tx(raw):
    b = bytes.fromhex(raw)
    off = 0
    version = int.from_bytes(b[off:off+4], "little"); off += 4
    nin, off = rd_varint(b, off)
    inputs = []
    for _ in range(nin):
        outpoint = b[off:off+36]; off += 36
        slen, off = rd_varint(b, off)
        off += slen  # skip scriptSig
        seq = b[off:off+4]; off += 4
        inputs.append({"outpoint": outpoint, "sequence": seq})
    nout, off = rd_varint(b, off)
    outputs = []
    for _ in range(nout):
        val = int.from_bytes(b[off:off+8], "little"); off += 8
        slen, off = rd_varint(b, off)
        script = b[off:off+slen]; off += slen
        outputs.append((val, script))
    locktime = int.from_bytes(b[off:off+4], "little")
    return version, inputs, outputs, locktime

def main():
    data = json.load(open(JSON_PATH))
    checked = skipped = failed = 0
    for e in data[1:]:
        raw, script_hex, n_in, ht_signed, shreg, _shold, _shrep = e
        ht = ht_signed & 0xFFFFFFFF
        # keep: SIGHASH_ALL base + FORKID set + no ANYONECANPAY
        if (ht & 0x1F) != 0x01 or not (ht & 0x40) or (ht & 0x80):
            skipped += 1
            continue
        version, inputs, outputs, locktime = parse_tx(raw)
        if n_in >= len(inputs):
            skipped += 1
            continue
        digest = tx.sighash_forkid(inputs, outputs, n_in,
                                   bytes.fromhex(script_hex), 0,
                                   sighash_type=ht, version=version, locktime=locktime)
        # Core's uint256 GetHex() renders reversed (big-endian display)
        if digest[::-1].hex() == shreg.lower():
            checked += 1
        else:
            failed += 1
            if failed <= 3:
                print("MISMATCH:", n_in, hex(ht))
                print("  mine:", digest[::-1].hex())
                print("  abcs:", shreg)
    print(f"vectors checked: {checked}, skipped: {skipped}, failed: {failed}")
    sys.exit(1 if failed or checked == 0 else 0)

if __name__ == "__main__":
    main()
