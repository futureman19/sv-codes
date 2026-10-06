# SV-GENESIS mint service

SV-0003 implementation; only the `sv-genesis` collection, fixed supply 100.
The public demo issuer is **not a production anti-forgery key**. This server
never creates, rotates, returns or logs private keys.

## Run (repository root)

Python 3.12 is the container/runtime target. Dependencies are pinned, including
Pillow 12.3.0 to match the published renderer's current environment.

```sh
uv venv mint/.venv --python 3.12
uv pip install --python mint/.venv/Scripts/python.exe -r mint/requirements.txt
# Supply MINT_WIF, ISSUER_SEED securely through the environment.
# Local persistent storage (POSIX example; select a private path):
export DB_PATH="$PWD/mint/local/mint.db"
mint/.venv/Scripts/python.exe -m uvicorn mint.server:create_app --factory --host 127.0.0.1 --port 8080 --workers 1 --no-access-log
```

On Linux use `mint/.venv/bin/python` in place of `Scripts/python.exe`.
`MINT_WIF` must be a compressed mainnet WIF, distinct from the issuer key.
`ISSUER_SEED` is the UTF-8 phrase hashed with SHA-256 and then passed to
`svcode.crypto.key_from_hex`; use the exact registered demo phrase already
provisioned in the Fly secret, not a hex key. No secret has a default.
`FEE_SATS=300`, `MAX_IP_PER_DAY=3`, `DB_PATH=/data/mint.db` by default.

For local claim QA explicitly provide `Fly-Client-IP: 127.0.0.1`. Production
must be reachable only through Fly's trusted edge. The app deliberately refuses
missing/invalid identity and does not trust `X-Forwarded-For` or socket peers.
Do not expose its internal port directly to untrusted clients.

## Fly configuration (parent/operator only)

The provisioned app is `sv-mint`, region `sjc`, encrypted 1 GB volume
`mint_data`. Build context **must be the repository root**:

```sh
flyctl config validate -c mint/fly.toml
flyctl deploy . --remote-only --config mint/fly.toml --ignorefile "C:/Users/futur/Desktop/sv-codes/mint/Dockerfile.dockerignore" --ha=false -a sv-mint
flyctl scale count 1 -a sv-mint
```

Run exactly one machine and one application worker. Do not clone volumes or run
blue/green independent writers. The OS file lock also serializes accidental
multiple processes sharing the same volume; it is not distributed coordination.
The Dockerfile-specific allowlist excludes environments, secrets, DBs and test
artifacts from the remote build context. No deployment is performed by tests.

After deployment verify `/health`, `/mint/sv-genesis/status`, the public issuer
and funding address, persistent commitment across restart, then one authorized
real claim and its actual chain receipt. The health `wallet_cached_sats` field is
explicitly **not** a live balance or evidence of funding. Initial/top-up funding
must be confirmed unless `FUNDING_TXID` explicitly pins a parent transaction.
The shipped Fly configuration pins the parent-provided funding transaction;
its raw bytes, txid, and P2PKH script are verified locally before selecting its
output, permitting this known unconfirmed bootstrap without an address-index
race. This is not proof of confirmation or of an externally unspent output;
use a dedicated wallet. Service-owned unconfirmed change is chained from accepted
parent raw bytes without consulting a stale address index.

## API

- `GET /health`: liveness, public funding/issuer identity, cached wallet sats,
  accepted/pending counts, shuffle commitment. Does not call WoC.
- `GET /mint/sv-genesis/status`: `col`, `supply`, `remaining`, `commitment`,
  `minted` records (`edition`, `index`, `seed`, `txid`, `ts`), `pending`,
  `complete`. The original `shuffle` is published only when all 100 are accepted.
- `GET /mint/sv-genesis/edition/{edition}`: the exact persisted accepted response,
  including signed envelope hex. Returns 404 for pending/unassigned editions.
  Use this public read-only receipt to recover personal codes after a lost HTTP
  response or from the sold-out gallery; it never broadcasts or assigns again.
- `POST /mint/sv-genesis/claim`, JSON `{"address":"<mainnet P2PKH>"}`:
  success `{edition,seed,cert,txid,envelope}`. `envelope` is serialized BMP hex,
  carries canonical `cert`, action A47C, target GEN1, signed by the issuer.

Errors contain `{error}`: 400 invalid request/address/edge identity,
404 unknown collection, 409 `already_claimed` or `sold_out`, 429 `rate_limited`,
502 `upstream`, 503 `funding`, `pending`, `busy` or `journal_corrupt`.
A completed duplicate is always 409. Repeating a pending address recovers its
original response; requesting another address first reconciles the old pending
claim before a new assignment. This may remain 503 while an upstream is down.

`remaining` excludes reservations. If the last edition is pending,
`remaining=0`, `pending=1`, `complete=false`, and `shuffle` is absent; do not
announce completed sellout until `complete=true`.

## Durability and recovery

- SQLite WAL + synchronous FULL; stable secure shuffle and canonical SHA-256
  commitment persisted once. Certificate templates/render hashes and public key
  bindings persist as well; changing keys against an existing ledger is refused.
- Unique collection/address, collection/edition and shuffle position constraints.
  A partial unique index permits at most one unfinished wallet operation.
- Cross-process file lock covers every assignment and every WoC call. No network
  request is made from `/health` or `/status`.
- First commit reserves the assignment. A second commit journals immutable raw
  signed transaction, locally computed txid, input selection and final signed
  response **before** any broadcast attempt.
- A timeout, rejection, mempool conflict, missing/wrong returned txid, or failed
  reconciliation never releases an edition or switches inputs. Further claims
  first query the original txid's raw bytes; if absent they rebroadcast the exact
  journaled bytes. An unavailable lookup blocks rather than guesses.
- After accepted broadcast or byte-identical raw lookup, mark accepted and replace
  spent wallet entries with change parsed from parent output 2, atomically.
  Saved inputs exclude previously spent outputs from later funding refreshes.
- Reservations without a signed transaction (e.g. insufficient funds) also remain
  assigned and resume the same address/edition when funding becomes available.
- Dedicated funding wallet only: do not externally spend its cached change.
  Ancestor/mempool limits can pause chained mints until parents confirm. Resume by
  repeating the pending claim, never by deleting rows or creating a replacement TX.
- Back up SQLite using its online backup API or stop the service first. Copying
  just the DB while WAL is active is not a safe backup. Keep the volume and journal
  intact on redeploy; never erase a pending record to unblock the wallet.

Transaction acceptance is not SPV confirmation. Address submission does not prove
address ownership, and the one-address/IP policy is not Sybil resistance. Preserve
the collectible's one-satoshi output; ordinary wallets may spend it as funding.

## Tests

```sh
mint/.venv/Scripts/python.exe -m pytest mint/test_mint.py mint/test_recovery.py -q -s --basetemp=mint/.test-tmp
```

Tests use deterministic test keys and mocked WoC; no real network spends. They
exercise all 100 canonical rendered certificates and size bounds, independent
`ecdsa` transaction-signature verification, pre-mint SV2 anchoring, signed BMP
binding, no-change and multi-input builder cases, duplicate/thread/process races,
100-edition exhaustion and commitment audit, Fly-only limits, durable pre-send
journaling, both crash windows, upstream ambiguity and exact-TX recovery, key
binding, parent-change chaining, plus a real local Uvicorn HTTP claim smoke test.

The faucet txbuilder is preserved verbatim as a prefix of `mint/txbuilder.py`;
`build_mint_tx` is a separate appended function with the same signing flow.
No faucet, renderer, browser or specification files are modified by this service.
