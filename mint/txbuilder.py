"""txbuilder.py — raw BSV transaction construction (P2PKH, SIGHASH_ALL|FORKID).

Self-contained: pure-Python secp256k1 + RFC 6979 (mirrors the verified
poc/svcode/crypto.py math), base58, hash160 (pure-Python RIPEMD-160 fallback
for OpenSSL-3 hosts that dropped it).
"""
import hashlib
import hmac as hmac_mod

# ---------- secp256k1 ----------
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
G = (0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798,
     0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8)

def _inv(a, m=P): return pow(a, -1, m)

def pt_add(p, q):
    if p is None: return q
    if q is None: return p
    (x1, y1), (x2, y2) = p, q
    if x1 == x2 and (y1 + y2) % P == 0: return None
    if p == q: lam = (3 * x1 * x1) * _inv(2 * y1) % P
    else:      lam = (y2 - y1) * _inv(x2 - x1) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)

def pt_mul(k, p=G):
    r = None
    while k:
        if k & 1: r = pt_add(r, p)
        p = pt_add(p, p); k >>= 1
    return r

def lift_x(x, odd):
    y2 = (pow(x, 3, P) + 7) % P
    y = pow(y2, (P + 1) // 4, P)
    if (y & 1) != (1 if odd else 0): y = P - y
    return (x, y)

def pubkey_from_priv(priv_int):
    return pt_mul(priv_int % N)

def compress_pub(point):
    x, y = point
    return bytes([2 | (y & 1)]) + x.to_bytes(32, "big")

def parse_pubkey(pub_bytes):
    if len(pub_bytes) == 33 and pub_bytes[0] in (2, 3):
        return lift_x(int.from_bytes(pub_bytes[1:], "big"), pub_bytes[0] == 3)
    raise ValueError("unsupported pubkey")

# ---------- RFC 6979 + DER ----------
def rfc6979_k(priv_int, digest):
    x = priv_int.to_bytes(32, "big")
    v = b"\x01" * 32
    k = b"\x00" * 32
    k = hmac_mod.new(k, v + b"\x00" + x + digest, hashlib.sha256).digest()
    v = hmac_mod.new(k, v, hashlib.sha256).digest()
    k = hmac_mod.new(k, v + b"\x01" + x + digest, hashlib.sha256).digest()
    v = hmac_mod.new(k, v, hashlib.sha256).digest()
    while True:
        v = hmac_mod.new(k, v, hashlib.sha256).digest()
        cand = int.from_bytes(v, "big")
        if 1 <= cand < N: return cand
        k = hmac_mod.new(k, v + b"\x00", hashlib.sha256).digest()
        v = hmac_mod.new(k, v, hashlib.sha256).digest()

def _der_int(x):
    b = x.to_bytes((x.bit_length() + 7) // 8 or 1, "big")
    if b[0] & 0x80: b = b"\x00" + b
    return b"\x02" + bytes([len(b)]) + b

def sign(priv_int, digest):
    z = int.from_bytes(digest, "big")
    while True:
        k = rfc6979_k(priv_int, digest)
        x, _ = pt_mul(k)
        r = x % N
        s = (_inv(k, N) * (z + r * priv_int)) % N
        if s > N // 2: s = N - s  # low-s
        if r and s: break
    sig = _der_int(r) + _der_int(s)
    return b"\x30" + bytes([len(sig)]) + sig

def verify(pub_point, sig_der, digest):
    # minimal DER parse
    assert sig_der[0] == 0x30
    i = 2
    assert sig_der[i] == 0x02
    lr = sig_der[i + 1]; r = int.from_bytes(sig_der[i+2:i+2+lr], "big"); i += 2 + lr
    assert sig_der[i] == 0x02
    ls = sig_der[i + 1]; s = int.from_bytes(sig_der[i+2:i+2+ls], "big")
    z = int.from_bytes(digest, "big")
    w = _inv(s, N)
    u1, u2 = z * w % N, r * w % N
    x, _ = pt_add(pt_mul(u1), pt_mul(u2, pub_point))
    return x % N == r

# ---------- hashes / encodings ----------
def sha256d(b): return hashlib.sha256(hashlib.sha256(b).digest()).digest()

def _ripemd160_pure(msg):
    RL = [0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,7,4,13,1,10,6,15,3,12,0,9,5,2,14,11,8,3,10,14,4,9,15,8,1,2,7,0,6,13,11,5,12,1,9,11,10,0,8,12,4,13,3,7,15,14,5,6,2,4,0,5,9,7,12,2,10,14,1,3,8,11,6,15,13]
    RR = [5,14,7,0,9,2,11,4,13,6,15,8,1,10,3,12,6,11,3,7,0,13,5,10,14,15,8,12,4,9,1,2,15,5,1,3,7,14,6,9,11,8,12,2,10,0,4,13,8,6,4,1,3,11,15,0,5,12,2,13,9,7,10,14,12,15,10,4,1,5,8,7,6,2,13,14,0,3,9,11]
    SL = [11,14,15,12,5,8,7,9,11,13,14,15,6,7,9,8,7,6,8,13,11,9,7,15,7,12,15,9,11,7,13,12,11,13,6,7,14,9,13,15,14,8,13,6,5,12,7,5,11,12,14,15,14,15,9,8,9,14,5,6,8,6,5,12,9,15,5,11,6,8,13,12,5,12,13,14,11,8,5,6]
    SR = [8,9,9,11,13,15,15,5,7,7,8,11,14,14,12,6,9,13,15,7,12,8,9,11,7,7,12,7,6,15,13,11,9,7,15,11,8,6,6,14,12,13,5,14,13,13,7,5,15,5,8,11,14,14,6,14,6,9,12,9,12,5,15,8,8,5,12,9,12,5,14,6,8,13,6,5,15,13,11,11]
    KL = [0x00000000,0x5A827999,0x6ED9EBA1,0x8F1BBCDC,0xA953FD4E]
    KR = [0x50A28BE6,0x5C4DD124,0x6D703EF3,0x7A6D76E9,0x00000000]
    rol = lambda x, n: ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF
    def f(j, x, y, z):
        if j < 16: return x ^ y ^ z
        if j < 32: return (x & y) | (~x & z)
        if j < 48: return (x | ~y) ^ z
        if j < 64: return (x & z) | (y & ~z)
        return x ^ (y | ~z)
    ml = len(msg)
    msg = bytearray(msg); msg.append(0x80)
    while len(msg) % 64 != 56: msg.append(0)
    msg += (ml * 8).to_bytes(8, "little")
    h0, h1, h2, h3, h4 = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0
    M = 0xFFFFFFFF
    for off in range(0, len(msg), 64):
        X = [int.from_bytes(msg[off+4*i:off+4*i+4], "little") for i in range(16)]
        a, b, c, d, e = h0, h1, h2, h3, h4
        aa, bb, cc, dd, ee = h0, h1, h2, h3, h4
        for j in range(80):
            bl = j >> 4
            t = (rol((a + f(j, b, c, d) + X[RL[j]] + KL[bl]) & M, SL[j]) + e) & M
            a, e, d, c, b = e, d, rol(c, 10), b, t
            t = (rol((aa + f(79 - j, bb, cc, dd) + X[RR[j]] + KR[bl]) & M, SR[j]) + ee) & M
            aa, ee, dd, cc, bb = ee, dd, rol(cc, 10), bb, t
        t = (h1 + c + dd) & M
        h1 = (h2 + d + ee) & M; h2 = (h3 + e + aa) & M
        h3 = (h4 + a + bb) & M; h4 = (h0 + b + cc) & M; h0 = t
    return b"".join(h.to_bytes(4, "little") for h in (h0, h1, h2, h3, h4))

def ripemd160(msg):
    try:
        h = hashlib.new("ripemd160"); h.update(msg); return h.digest()
    except (ValueError, TypeError):
        return _ripemd160_pure(msg)

def hash160(b): return ripemd160(hashlib.sha256(b).digest())

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58decode(s):
    n = 0
    for ch in s: n = n * 58 + B58.index(ch)
    b = n.to_bytes((n.bit_length() + 7) // 8 or 1, "big")
    zeros = len(s) - len(s.lstrip("1"))
    return b"\x00" * zeros + b

def b58check_decode(s):
    raw = b58decode(s)
    payload, chk = raw[:-4], raw[-4:]
    assert sha256d(payload)[:4] == chk, "bad checksum"
    return payload[0], payload[1:]

def wif_to_priv(wif):
    ver, payload = b58check_decode(wif)
    assert ver == 0x80, "not a mainnet WIF"
    if len(payload) == 33 and payload[-1] == 1: payload = payload[:-1]
    return int.from_bytes(payload, "big")

def p2pkh_script(pubkey_bytes):
    return b"\x76\xa9\x14" + hash160(pubkey_bytes) + b"\x88\xac"

def address_from_pubkey(pubkey_bytes, version=0x00):
    h = hash160(pubkey_bytes)
    raw = bytes([version]) + h
    chk = sha256d(raw)[:4]
    n = int.from_bytes(raw + chk, "big")
    out = ""
    while n: n, r = divmod(n, 58); out = B58[r] + out
    for byte in raw + chk:
        if byte == 0: out = "1" + out
        else: break
    return out

# ---------- transaction building ----------
SIGHASH_ALL_FORKID = 0x41

def varint(n):
    if n < 0xFD: return bytes([n])
    if n <= 0xFFFF: return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xFFFFFFFF: return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")

def push(data):
    return bytes([len(data)]) + data  # all our pushes < 76 bytes

def ser_outpoint(txid_hex, vout):
    return bytes.fromhex(txid_hex)[::-1] + vout.to_bytes(4, "little")

def ser_output(value, script):
    return value.to_bytes(8, "little") + varint(len(script)) + script

def sighash_forkid(tx_inputs, tx_outputs, idx, script_code, value,
                   sighash_type=SIGHASH_ALL_FORKID, version=1, locktime=0):
    """BIP143-style preimage digest used by BSV (SIGHASH_ALL|FORKID)."""
    hp = sha256d(b"".join(i["outpoint"] for i in tx_inputs))
    hs = sha256d(b"".join(i["sequence"] for i in tx_inputs))
    ho = sha256d(b"".join(ser_output(v, s) for v, s in tx_outputs))
    inp = tx_inputs[idx]
    pre = (
        version.to_bytes(4, "little") + hp + hs +
        inp["outpoint"] + varint(len(script_code)) + script_code +
        value.to_bytes(8, "little") + inp["sequence"] +
        ho + locktime.to_bytes(4, "little") + sighash_type.to_bytes(4, "little")
    )
    return sha256d(pre)

def build_tx(utxos, pay_script, amount, change_script, fee, faucet_priv):
    """utxos: [{txid, vout, value}]. Returns (raw_hex, txid)."""
    total = sum(u["value"] for u in utxos)
    if total < amount + fee: raise ValueError("insufficient funds")
    change = total - amount - fee
    outputs = [(amount, pay_script)]
    if change > 0: outputs.append((change, change_script))
    faucet_pub = compress_pub(pubkey_from_priv(faucet_priv))
    script_code = p2pkh_script(faucet_pub)
    tx_inputs = [{
        "outpoint": ser_outpoint(u["txid"], u["vout"]),
        "sequence": (0xFFFFFFFF).to_bytes(4, "little"),
        "value": u["value"],
    } for u in utxos]
    signed_inputs = []
    for i, inp in enumerate(tx_inputs):
        digest = sighash_forkid(tx_inputs, outputs, i, script_code, inp["value"])
        sig = sign(faucet_priv, digest) + bytes([SIGHASH_ALL_FORKID])
        script_sig = push(sig) + push(faucet_pub)
        signed_inputs.append(
            inp["outpoint"] + varint(len(script_sig)) + script_sig + inp["sequence"])
    raw = (
        (1).to_bytes(4, "little") + varint(len(signed_inputs)) + b"".join(signed_inputs) +
        varint(len(outputs)) + b"".join(ser_output(v, s) for v, s in outputs) +
        (0).to_bytes(4, "little")
    )
    return raw.hex(), sha256d(raw)[::-1].hex()


# ---------- SV-0003 mint; upstream faucet implementation above is verbatim ----------
def build_mint_tx(utxos, pay_script, pre_mint_hash, change_script, fee, faucet_priv):
    """One-sat output 0, zero-value SV2 anchor output 1, optional change output 2.

    The signing/serialization flow is intentionally identical to build_tx.
    """
    if len(pre_mint_hash) != 32:
        raise ValueError("pre-mint hash must be 32 bytes")
    if not utxos or fee < 1:
        raise ValueError("inputs and positive fee required")
    total = sum(u["value"] for u in utxos)
    amount = 1
    if total < amount + fee: raise ValueError("insufficient funds")
    change = total - amount - fee
    outputs = [(amount, pay_script), (0, b"\x00\x6a" + push(b"SV2" + pre_mint_hash))]
    if change > 0: outputs.append((change, change_script))
    faucet_pub = compress_pub(pubkey_from_priv(faucet_priv))
    script_code = p2pkh_script(faucet_pub)
    tx_inputs = [{
        "outpoint": ser_outpoint(u["txid"], u["vout"]),
        "sequence": (0xFFFFFFFF).to_bytes(4, "little"),
        "value": u["value"],
    } for u in utxos]
    signed_inputs = []
    for i, inp in enumerate(tx_inputs):
        digest = sighash_forkid(tx_inputs, outputs, i, script_code, inp["value"])
        sig = sign(faucet_priv, digest) + bytes([SIGHASH_ALL_FORKID])
        script_sig = push(sig) + push(faucet_pub)
        signed_inputs.append(
            inp["outpoint"] + varint(len(script_sig)) + script_sig + inp["sequence"])
    raw = (
        (1).to_bytes(4, "little") + varint(len(signed_inputs)) + b"".join(signed_inputs) +
        varint(len(outputs)) + b"".join(ser_output(v, s) for v, s in outputs) +
        (0).to_bytes(4, "little")
    )
    return raw.hex(), sha256d(raw)[::-1].hex()
