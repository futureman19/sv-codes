"""test_txbuilder.py — verify the consensus-critical pieces without funds.

1. RIPEMD-160 + hash160 vectors (pure-Python path forced too)
2. WIF decode: KwDiBf89... -> privkey 1 (famous vector)
3. privkey 1 -> address 1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH
4. Sighash + signature self-consistency: build a TX from fabricated UTXOs,
   recompute every input's sighash independently, verify each signature
   against the faucet pubkey.
5. Structural re-parse of the built TX (fields, varints, scripts).
"""
import txbuilder as tx

passed = failed = 0
def ok(cond, name):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1
        print("FAIL:", name)

# --- 1. hashes
ok(tx._ripemd160_pure(b"").hex() == "9c1185a5c5e9fc54612808977ee8f548b2258d31", "ripemd160 pure empty")
ok(tx._ripemd160_pure(b"abc").hex() == "8eb208f7e05d987a9b044a8e98c6b087f15a0bfc", "ripemd160 pure abc")
ok(tx.ripemd160(b"abc").hex() == "8eb208f7e05d987a9b044a8e98c6b087f15a0bfc", "ripemd160 auto abc")
ok(tx.hash160(bytes.fromhex("0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798")).hex()
   == "751e76e8199196d454941c45d1b3a323f1433bd6", "hash160(G compressed)")

# --- 2/3. WIF + address vectors
priv1 = tx.wif_to_priv("KwDiBf89QgGbjEhKnhXJuH7LrciVrZi3qYjgd9M7rFU73sVHnoWn")
ok(priv1 == 1, "WIF decode -> 1")
pub1 = tx.compress_pub(tx.pubkey_from_priv(1))
ok(tx.address_from_pubkey(pub1) == "1BgGZ9tcN4rm9KBzDn7KprQz87SZ26SAMH", "address(1)")

# --- 4. sighash + signature self-consistency on a fabricated spend
faucet_priv = 0xC0FFEE % tx.N
faucet_pub = tx.compress_pub(tx.pubkey_from_priv(faucet_priv))
fake_utxos = [
    {"txid": "aa" * 32, "vout": 0, "value": 100_000},
    {"txid": "bb" * 32, "vout": 1, "value": 50_000},
]
payee_pub = tx.compress_pub(tx.pubkey_from_priv(12345))
pay_script = tx.p2pkh_script(payee_pub)
change_script = tx.p2pkh_script(faucet_pub)
raw, txid = tx.build_tx(fake_utxos, pay_script, 50_000, change_script, 300, faucet_priv)
rawb = bytes.fromhex(raw)

# independently recompute sighash for each input and verify the signature
tx_inputs = [{"outpoint": tx.ser_outpoint(u["txid"], u["vout"]),
              "sequence": (0xFFFFFFFF).to_bytes(4, "little"),
              "value": u["value"]} for u in fake_utxos]
outputs = [(50_000, pay_script), (100_000 + 50_000 - 50_000 - 300, change_script)]
ok(rawb[:4] == (1).to_bytes(4, "little"), "version 1")
ok(rawb[-4:] == (0).to_bytes(4, "little"), "locktime 0")

# walk the serialized tx and verify each input's embedded signature
off = 4
nin = rawb[off]; off += 1
ok(nin == 2, "two inputs")
for i in range(nin):
    off += 36  # outpoint
    slen = rawb[off]; off += 1
    script_sig = rawb[off:off + slen]; off += slen
    off += 4  # sequence
    sig_len = script_sig[0]
    sig_der = script_sig[1:1 + sig_len - 1]  # strip sighash byte
    ok(script_sig[sig_len] == tx.SIGHASH_ALL_FORKID, f"sighash byte input {i}")
    digest = tx.sighash_forkid(tx_inputs, outputs, i, tx.p2pkh_script(faucet_pub), tx_inputs[i]["value"])
    ok(tx.verify(tx.parse_pubkey(faucet_pub), sig_der, digest), f"signature verifies input {i}")

# --- 5. outputs re-parse
nout = rawb[off]; off += 1
ok(nout == 2, "two outputs")
val0 = int.from_bytes(rawb[off:off + 8], "little"); off += 8
l0 = rawb[off]; off += 1 + l0
val1 = int.from_bytes(rawb[off:off + 8], "little"); off += 8
ok(val0 == 50_000, "pays 50,000 sats")
ok(val1 == 99_700, "change correct")
ok(tx.sha256d(rawb)[::-1].hex() == txid, "txid matches serialization")

print(f"{passed} passed, {failed} failed")
raise SystemExit(1 if failed else 0)
