"""svcode.spv — BMP-0003 (L3): SPV inclusion proof for anchored commands.

Implements spec/BMP-0003-l3-spv-inclusion.md:
- parse_bump / bump_root: BRC-74 BUMP parsing and merkle root calculation
- parse_beef: BRC-62 (v1, `0100BEEF`) container parsing
- verify_header: 80-byte block header PoW + field extraction
- verify_l3: full pipeline — BEEF → subject TX → BMP-0002 §5 validation with
  prevout evidence DERIVED from the included ancestor transactions → merkle
  inclusion of every BUMPed ancestor against the receiver's header store.

Hash byte-order convention: all hashes handled internally in natural
(internal/little-endian) byte order; display-hex conversion happens only at
API boundaries (txid arguments and returned values are display hex).
"""
from __future__ import annotations

from . import tx as txm
from .anchor import verify_l2
from .crypto import vk_from_hex  # noqa: F401  (re-export convenience)

BEEF_V1 = bytes.fromhex("0100beef")
FLAG_DUPLICATE = 0x01
FLAG_CLIENT_TXID = 0x02


# ---------- varint stream helpers ----------

def _rd(b: bytes, off: int, n: int) -> tuple[bytes, int]:
    if off + n > len(b):
        raise ValueError("truncated")
    return b[off:off + n], off + n

def rd_varint(b: bytes, off: int) -> tuple[int, int]:
    n = b[off]; off += 1
    if n < 0xFD: return n, off
    if n == 0xFD: v, off = _rd(b, off, 2); return int.from_bytes(v, "little"), off
    if n == 0xFE: v, off = _rd(b, off, 4); return int.from_bytes(v, "little"), off
    v, off = _rd(b, off, 8); return int.from_bytes(v, "little"), off

def ser_varint(n: int) -> bytes:
    if n < 0xFD: return bytes([n])
    if n <= 0xFFFF: return b"\xfd" + n.to_bytes(2, "little")
    if n <= 0xFFFFFFFF: return b"\xfe" + n.to_bytes(4, "little")
    return b"\xff" + n.to_bytes(8, "little")


# ---------- BRC-74 BUMP ----------

def parse_bump(b: bytes):
    """-> {block_height, tree_height, path: [[{offset, flags, hash(32B)|None}]]}"""
    height, off = rd_varint(b, 0)
    tree_height = b[off]; off += 1
    if tree_height == 0 or tree_height > 64:
        raise ValueError("bad tree height")
    path = []
    for _level in range(tree_height):
        n, off = rd_varint(b, off)
        leaves = []
        for _ in range(n):
            offset, off = rd_varint(b, off)
            flags = b[off]; off += 1
            h = None
            if not (flags & FLAG_DUPLICATE):
                h, off = _rd(b, off, 32)
            leaves.append({"offset": offset, "flags": flags, "hash": h})
        leaves.sort(key=lambda l: l["offset"])
        path.append(leaves)
    if off != len(b):
        raise ValueError("trailing bytes after BUMP")
    return {"block_height": height, "tree_height": tree_height, "path": path}


def bump_root(bump, txid_display_hex: str) -> bytes:
    """Merkle root (internal byte order) implied by this BUMP for the given txid."""
    txid = bytes.fromhex(txid_display_hex)[::-1]
    level0 = bump["path"][0]
    leaf = next((l for l in level0 if l["hash"] == txid), None)
    if leaf is None:
        raise ValueError("txid not in BUMP level 0")
    index = leaf["offset"]
    working = txid
    for height, leaves in enumerate(bump["path"]):
        sib_off = (index >> height) ^ 1
        sib = next((l for l in leaves if l["offset"] == sib_off), None)
        if sib is None:
            raise ValueError(f"missing sibling at level {height}")
        if sib["flags"] & FLAG_DUPLICATE:
            working = txm.sha256d(working + working)
        elif sib_off & 1:
            # sibling offset odd ⇒ working node is the LEFT child
            working = txm.sha256d(working + sib["hash"])
        else:
            # sibling offset even ⇒ working node is the RIGHT child
            working = txm.sha256d(sib["hash"] + working)
    return working


# ---------- BRC-62 BEEF (v1) ----------

def parse_raw_tx_stream(b: bytes, off: int):
    """Parse one raw tx starting at off; return (raw_bytes, new_off)."""
    start = off
    _ver, off = _rd(b, off, 4)
    nin, off = rd_varint(b, off)
    for _ in range(nin):
        _, off = _rd(b, off, 36)
        slen, off = rd_varint(b, off)
        _, off = _rd(b, off, slen)
        _, off = _rd(b, off, 4)
    nout, off = rd_varint(b, off)
    for _ in range(nout):
        _, off = _rd(b, off, 8)
        slen, off = rd_varint(b, off)
        _, off = _rd(b, off, slen)
    _, off = _rd(b, off, 4)
    return b[start:off], off


def parse_beef(b: bytes):
    """-> {bumps: [parsed BUMP], txs: [{raw, txid(display), bump_index|None}]}
    Subject transaction is the LAST entry (BRC-62 topological ordering)."""
    if b[:4] != BEEF_V1:
        raise ValueError("not BEEF v1 (0100BEEF)")
    off = 4
    n_bumps, off = rd_varint(b, off)
    bumps = []
    for _ in range(n_bumps):
        # a BUMP's length is implicit; parse and track consumption
        sub = parse_bump_stream(b, off)
        bumps.append(sub[0]); off = sub[1]
    n_txs, off = rd_varint(b, off)
    txs = []
    for _ in range(n_txs):
        raw, off = parse_raw_tx_stream(b, off)
        has_bump = b[off]; off += 1
        bidx = None
        if has_bump:
            bidx, off = rd_varint(b, off)
            if bidx >= len(bumps):
                raise ValueError("BUMP index out of range")
        txs.append({"raw": raw, "txid": txm.sha256d(raw)[::-1].hex(), "bump_index": bidx})
    if off != len(b):
        raise ValueError("trailing bytes after BEEF")
    return {"bumps": bumps, "txs": txs}


def parse_bump_stream(b: bytes, off: int):
    """Streaming BUMP parse; returns (bump, new_off)."""
    start = off
    height, off = rd_varint(b, off)
    tree_height = b[off]; off += 1
    if tree_height == 0 or tree_height > 64:
        raise ValueError("bad tree height")
    path = []
    for _level in range(tree_height):
        n, off = rd_varint(b, off)
        leaves = []
        for _ in range(n):
            offset, off = rd_varint(b, off)
            flags = b[off]; off += 1
            h = None
            if not (flags & FLAG_DUPLICATE):
                h, off = _rd(b, off, 32)
            leaves.append({"offset": offset, "flags": flags, "hash": h})
        leaves.sort(key=lambda l: l["offset"])
        path.append(leaves)
    return ({"block_height": height, "tree_height": tree_height, "path": path,
             "raw": b[start:off]}, off)


# ---------- block headers ----------

def target_from_bits(bits: int) -> int:
    exp = bits >> 24
    mant = bits & 0x007FFFFF
    if bits & 0x00800000:
        raise ValueError("negative target")
    return mant << (8 * (exp - 3)) if exp >= 3 else mant >> (8 * (3 - exp))


def verify_header(header: bytes):
    """PoW-check an 80-byte header. -> {hash(display), merkle_root(internal),
    prev_hash(internal), height-agnostic}. Raises on failure."""
    if len(header) != 80:
        raise ValueError("header must be 80 bytes")
    bits = int.from_bytes(header[72:76], "little")
    digest = txm.sha256d(header)
    if int.from_bytes(digest, "little") > target_from_bits(bits):
        raise ValueError("header fails proof-of-work")
    return {
        "hash": digest[::-1].hex(),
        "merkle_root": header[36:68],
        "prev_hash": header[4:36],
    }


# ---------- the L3 pipeline ----------

def verify_l3(beef: bytes, authority_vk_hex: str, headers: list[bytes],
              seen: dict | None = None, min_depth: int = 1,
              tip_height: int | None = None):
    """Full BMP-0003 validation. `headers`: locally held 80-byte headers (each
    PoW-verified here). `tip_height`: receiver's known chain-tip height for the
    optional burial-depth check. Returns the command Envelope."""
    doc = parse_beef(beef)                                   # 1. parse
    subject = doc["txs"][-1]                                 # 2. subject = last
    by_txid = {t["txid"]: t for t in doc["txs"]}

    parsed_subject = txm.parse_tx(subject["raw"])
    # 3. derive prevout evidence from included ancestors (no separate bundle)
    prevouts = []
    for inp in parsed_subject["inputs"]:
        ptxid = inp["outpoint"][:32][::-1].hex()
        pvout = int.from_bytes(inp["outpoint"][32:], "little")
        anc = by_txid.get(ptxid)
        if anc is None:
            raise ValueError(f"ancestor {ptxid[:16]}… not in BEEF")
        anc_parsed = txm.parse_tx(anc["raw"])
        if pvout >= len(anc_parsed["outputs"]):
            raise ValueError("input references nonexistent ancestor output")
        val, script = anc_parsed["outputs"][pvout]
        prevouts.append({"txid": ptxid, "vout": pvout, "value": val,
                         "script_hex": script.hex()})
    # 4. full BMP-0002 §5 validation (envelope, authority, input sigs, fee, freshness)
    env = verify_l2(subject["raw"], prevouts, authority_vk_hex, seen)

    # 5. merkle inclusion: every tx carrying a BUMP must root into a held header
    root_index = {}
    for h in headers:
        info = verify_header(h)                              # PoW per header
        root_index[info["merkle_root"]] = info
    for t in doc["txs"]:
        if t["bump_index"] is None:
            continue
        bump = doc["bumps"][t["bump_index"]]
        root = bump_root(bump, t["txid"])                    # 5a. BRC-74 walk
        hdr = root_index.get(root)
        if hdr is None:
            raise ValueError(f"tx {t['txid'][:16]}…: merkle root not in header store")
        if tip_height is not None:                           # 5b. burial depth
            depth = tip_height - bump["block_height"] + 1
            if depth < min_depth:
                raise ValueError(f"insufficient burial depth {depth} < {min_depth}")
    return env
