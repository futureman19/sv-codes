"""Cryptographic primitives: hashing, integrity, secp256k1 envelope signatures.

Signature rule (BMP-0000 §4.3):
    digest = SHA-256(canonical header bytes 0x00..0x14 || Payload_Data)
    sig    = ECDSA/secp256k1, deterministic (RFC 6979), 64-byte compact r||s, low-s
"""

from __future__ import annotations

import hashlib
import zlib

from ecdsa import SECP256k1, SigningKey, VerifyingKey, util


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def crc32(data: bytes) -> int:
    """IEEE 802.3 CRC-32 (matches zlib and the SV-0001 JS transmitter)."""
    return zlib.crc32(data) & 0xFFFFFFFF


def generate_key() -> SigningKey:
    return SigningKey.generate(curve=SECP256k1)


def key_from_hex(priv_hex: str) -> SigningKey:
    return SigningKey.from_string(bytes.fromhex(priv_hex), curve=SECP256k1)


def pubkey_hex(sk_or_vk) -> str:
    vk = sk_or_vk.verifying_key if isinstance(sk_or_vk, SigningKey) else sk_or_vk
    return vk.to_string("compressed").hex()


def vk_from_hex(pub_hex: str) -> VerifyingKey:
    raw = bytes.fromhex(pub_hex)
    if len(raw) == 33:  # compressed
        return VerifyingKey.from_string(raw, curve=SECP256k1)
    if len(raw) == 64:  # raw x||y
        return VerifyingKey.from_string(raw, curve=SECP256k1)
    raise ValueError(f"unsupported pubkey length {len(raw)}")


def sign_digest(sk: SigningKey, digest: bytes) -> bytes:
    """64-byte compact r||s, RFC 6979 deterministic, low-s normalized.

    NOTE: python-ecdsa's plain sign_digest() draws a RANDOM k; the
    deterministic variant is required for reproducible golden vectors.
    """
    return sk.sign_digest_deterministic(
        digest, hashfunc=hashlib.sha256, sigencode=util.sigencode_string_canonize
    )


def verify_digest(vk: VerifyingKey, sig: bytes, digest: bytes) -> bool:
    """Strict verify: compact r||s encoding AND low-s required (BMP-0000 §4.3)."""
    from ecdsa import BadSignatureError

    if len(sig) != 64:
        return False
    try:
        _r, s = util.sigdecode_string(sig, SECP256k1.order)
        if s > SECP256k1.order // 2:  # low-s rule
            return False
        return vk.verify_digest(sig, digest, sigdecode=util.sigdecode_string)
    except (BadSignatureError, Exception):  # noqa: BLE001 - any failure = invalid
        return False
