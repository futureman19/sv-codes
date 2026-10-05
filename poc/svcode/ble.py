"""svcode.ble — BMP-0001 (BMP-BLE) fragmentation and reassembly.

Carries SV-0001 §3.1 streams over connectionless BLE advertising.
MSD payload layout (after 2-byte company ID):

    "SV" (2) ‖ Stream_Seq (1) ‖ Frag_Index (1) ‖ Frag_Count (1) ‖ Frag_Data (MTU)

Profiles: LE-Legacy MTU = 19 bytes (31-byte PDUs), LE-Extended MTU = 251.
Implements spec/BMP-0001-bmp-ble.md §3–§5 exactly.
"""
from __future__ import annotations

COMPANY_ID = 0xFFFF
MAGIC = b"SV"
LEGACY_MTU = 19
EXTENDED_MTU = 251
_HEADER = 5  # magic(2) + seq(1) + idx(1) + cnt(1)


def fragment(stream: bytes, stream_seq: int = 0, mtu: int = LEGACY_MTU) -> list[bytes]:
    """Split a stream into MSD data blobs (company ID NOT included — see pack_pdu)."""
    if not stream: raise ValueError("empty stream")
    count = (len(stream) + mtu - 1) // mtu
    if count > 255: raise ValueError("stream too large for one generation")
    out = []
    for i in range(count):
        chunk = stream[i * mtu:(i + 1) * mtu]
        chunk = chunk + b"\x00" * (mtu - len(chunk))  # zero-pad final fragment
        out.append(MAGIC + bytes([stream_seq & 0xFF, i, count]) + chunk)
    return out


class Reassembler:
    """Collects fragments for one generation at a time (spec §5)."""

    def __init__(self):
        self._seq = None
        self._count = 0
        self._mtu = 0
        self._frags: dict[int, bytes] = {}

    def feed(self, msd: bytes) -> bytes | None:
        """Feed one MSD payload (company ID already stripped). Returns the
        reassembled stream when the current generation completes, else None."""
        if len(msd) < _HEADER + 1 or msd[:2] != MAGIC:
            return None  # not BMP-BLE / truncated — drop silently
        seq, idx, cnt = msd[2], msd[3], msd[4]
        if cnt == 0 or idx >= cnt:
            return None
        if seq != self._seq:
            # generation change: discard any incomplete previous set
            self._seq, self._count, self._mtu, self._frags = seq, cnt, len(msd) - _HEADER, {}
        else:
            if cnt != self._count or (len(msd) - _HEADER) != self._mtu:
                return None  # inconsistent fragment within a generation
        self._frags[idx] = msd[_HEADER:]
        if len(self._frags) < self._count:
            return None
        buf = b"".join(self._frags[i] for i in range(self._count))
        self._frags = {}  # generation consumed; duplicates of it re-arm
        # spec §5.3: truncate count*MTU back to the framed stream length
        if len(buf) < 8:
            return None
        clen = int.from_bytes(buf[:4], "big")
        if clen > 65535 + 85:
            return None  # garbage generation — wait for next cycle
        total = ((8 + clen + 31) // 32) * 32
        if total > len(buf):
            return None
        return buf[:total]


# ---------- full on-air legacy PDU packing (spec §3.2) ----------

def pack_pdu(msd: bytes) -> bytes:
    """Wrap MSD data into a complete 31-byte legacy advertising payload
    (Flags + Manufacturer Specific AD structure, company ID little-endian)."""
    struct = bytes([1 + 2 + len(msd), 0xFF]) + COMPANY_ID.to_bytes(2, "little") + msd
    payload = bytes([0x02, 0x01, 0x06]) + struct
    if len(payload) > 31:
        raise ValueError(f"legacy adv payload too large: {len(payload)} > 31")
    return payload


def unpack_pdu(payload: bytes) -> bytes | None:
    """Parse a legacy advertising payload back to MSD data (None if not BMP-BLE)."""
    off = 0
    while off + 2 <= len(payload):
        ln, ad_type = payload[off], payload[off + 1]
        body = payload[off + 2: off + 1 + ln]
        if len(body) != ln - 1:
            return None
        if ad_type == 0xFF and len(body) >= 2 + _HEADER:
            return body[2:]  # strip company ID
        off += 1 + ln
    return None
