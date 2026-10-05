"""svcode.anchor — BMP-0002 (L2): envelopes anchored in fee-paying BSV transactions.

Implements spec/BMP-0002-l2-on-chain-anchoring.md §3–§5:
- build_l2_tx: envelope in an OP_FALSE OP_RETURN output, P2PKH fee inputs
- extract_envelope: locate + parse the "BMP1" data output
- verify_l2: full offline validation (parse → envelope → authority →
  payment evidence → fee → outpoint freshness)
"""
from __future__ import annotations

from . import tx as txm
from .crypto import vk_from_hex
from .envelope import Envelope

MAGIC = b"BMP1"
MIN_FEE_SUGGESTED = 250


def pushdata(d: bytes) -> bytes:
    if len(d) <= 75:
        return bytes([len(d)]) + d
    if len(d) <= 0xFF:
        return b"\x4c" + bytes([len(d)]) + d
    if len(d) <= 0xFFFF:
        return b"\x4d" + len(d).to_bytes(2, "little") + d
    return b"\x4e" + len(d).to_bytes(4, "little") + d


def data_script(envelope_bytes: bytes) -> bytes:
    return b"\x00\x6a" + pushdata(MAGIC + envelope_bytes)


def build_l2_tx(envelope_bytes: bytes, utxos: list[dict], payer_priv: int,
                change_script: bytes | None = None, fee: int = 300):
    """utxos: [{txid, vout, value}] spent by payer_priv (P2PKH).
    Returns (raw_hex, txid, prevouts) where prevouts is the evidence bundle:
    [{txid, vout, value, script_hex}]."""
    payer_pub = txm.compress_pub(txm.pubkey_from_priv(payer_priv))
    payer_script = txm.p2pkh_script(payer_pub)
    if change_script is None:
        change_script = payer_script
    total = sum(u["value"] for u in utxos)
    if total <= fee:
        raise ValueError("insufficient funds for fee")
    outputs = [(0, data_script(envelope_bytes))]
    if total - fee > 0:
        outputs.append((total - fee, change_script))
    tx_inputs = [{
        "outpoint": txm.ser_outpoint(u["txid"], u["vout"]),
        "sequence": (0xFFFFFFFF).to_bytes(4, "little"),
        "value": u["value"],
    } for u in utxos]
    signed_inputs = []
    for i, inp in enumerate(tx_inputs):
        digest = txm.sighash_forkid(tx_inputs, outputs, i, payer_script, inp["value"])
        sig = txm.sign(payer_priv, digest) + bytes([txm.SIGHASH_ALL_FORKID])
        script_sig = txm.push(sig) + txm.push(payer_pub)
        signed_inputs.append(
            inp["outpoint"] + txm.varint(len(script_sig)) + script_sig + inp["sequence"])
    raw = (
        (1).to_bytes(4, "little") + txm.varint(len(signed_inputs)) + b"".join(signed_inputs) +
        txm.varint(len(outputs)) + b"".join(txm.ser_output(v, s) for v, s in outputs) +
        (0).to_bytes(4, "little")
    )
    prevouts = [{"txid": u["txid"], "vout": u["vout"], "value": u["value"],
                 "script_hex": payer_script.hex()} for u in utxos]
    return raw.hex(), txm.sha256d(raw)[::-1].hex(), prevouts


def extract_envelope(raw: bytes) -> bytes:
    """Locate the BMP1 data output and return the envelope bytes (spec §5.1)."""
    parsed = txm.parse_tx(raw)
    found = None
    for _val, script in parsed["outputs"]:
        if len(script) >= 2 and script[0] == 0x00 and script[1] == 0x6A:
            try:
                push, off = txm.read_push(script, 2)
            except ValueError:
                continue
            if off == len(script) and push[:4] == MAGIC:
                if found is not None:
                    raise ValueError("multiple BMP1 data outputs")
                found = push[4:]
    if found is None:
        raise ValueError("no BMP1 data output")
    return found


def verify_l2(raw: bytes, prevouts: list[dict], authority_vk_hex: str,
              seen: dict | None = None) -> Envelope:
    """Full offline L2 validation (spec §5). Returns the Envelope on success;
    raises ValueError with a reason on any failure.
    `seen`: caller-persisted dict {outpoint_key: txid} for the freshness rule."""
    parsed = txm.parse_tx(raw)                                   # 1. parse
    env_bytes = extract_envelope(raw)
    env = Envelope.parse(env_bytes)                              # 2. envelope
    if not env.verify(vk_from_hex(authority_vk_hex)):            # 3. authority
        raise ValueError("envelope signature invalid")

    evidence = {(p["txid"], p["vout"]): p for p in prevouts}
    structured_inputs = []
    total_in = 0
    for i, inp in enumerate(parsed["inputs"]):                   # 4. payment evidence
        txid = inp["outpoint"][:32][::-1].hex()
        vout = int.from_bytes(inp["outpoint"][32:], "little")
        ev = evidence.get((txid, vout))
        if ev is None:
            raise ValueError(f"missing prevout evidence for input {i}")
        prev_script = bytes.fromhex(ev["script_hex"])
        if not txm.is_p2pkh(prev_script):
            raise ValueError(f"prevout {i} is not P2PKH")
        sig_der, sighash_byte, pub = txm.parse_p2pkh_scriptsig(inp["script_sig"])
        if sighash_byte != txm.SIGHASH_ALL_FORKID:
            raise ValueError(f"input {i} wrong sighash type")
        if txm.hash160(pub) != prev_script[3:23]:
            raise ValueError(f"input {i} pubkey does not match prevout")
        structured = [{"outpoint": x["outpoint"], "sequence": x["sequence"]}
                      for x in parsed["inputs"]]
        digest = txm.sighash_forkid(
            structured, parsed["outputs"], i, prev_script, ev["value"],
            version=parsed["version"], locktime=parsed["locktime"])
        if not txm.verify(txm.parse_pubkey(pub), sig_der, digest):
            raise ValueError(f"input {i} signature invalid")
        structured_inputs.append(inp)
        total_in += ev["value"]

    total_out = sum(v for v, _ in parsed["outputs"])
    if total_in - total_out <= 0:                                # 5. fee
        raise ValueError("no fee paid")

    if seen is not None:                                         # 6. freshness
        for inp in parsed["inputs"]:
            key = inp["outpoint"].hex()
            prior = seen.get(key)
            if prior is not None and prior != parsed["txid"]:
                raise ValueError("double-spend: outpoint already backs another command")
        for inp in parsed["inputs"]:
            seen[inp["outpoint"].hex()] = parsed["txid"]
    return env
