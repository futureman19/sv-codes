# Telegram SV Code decoder (display-only)

Python long-polling bot: `/start`, `/help`, photos (largest Telegram version), and PNG/JPEG documents. No wallet, claim endpoint request, transaction, spending, payload URL fetch, or network-based chain verification exists in this service.

**Launch prerequisite: a dedicated BotFather token is absent.** An operator must create/select a dedicated bot and provide its token through a secret manager as `TELEGRAM_BOT_TOKEN`. Never reuse a Hermes bot token, paste a token into source/chat, or launch two pollers with the same token. This work does not provision or deploy anything.

## Local offline verification (no token)

Run from the repository root. On this Windows checkout the existing interpreter is usable:

```sh
mint/.venv/Scripts/python.exe -B -m telegram_bot decode docs/nft/genesis/mint/mint-master-code.png
mint/.venv/Scripts/python.exe -B -m telegram_bot decode docs/nft/genesis/genesis-052-code.jpg
mint/.venv/Scripts/python.exe -B -m pytest telegram_bot -q -p no:cacheprovider --basetemp "$TMPDIR/svcode-telegram-tests"
```

For a standalone environment, create `telegram_bot/.venv`, install `telegram_bot/requirements-dev.txt`, and substitute that environment's Python. Production installs only `requirements.txt`. The tests exercise checked-in real master/item PNGs and JPEGs, real signature verification and pixel-identical local reveal, plus **explicitly mocked** Telegram request/download/send fixtures. No tests call Telegram or the mint service. Tests require repository artifacts and are not included in the container.

`decode` prints the verified display result and reports whether a reveal was generated **in memory**. It does not save images. `serve` runs the bot; `_worker` is an internal subprocess protocol, not a user interface.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | required | Dedicated BotFather bot credential only |
| `TELEGRAM_STATE_DB` | `telegram_bot/state/offset.sqlite3` | Durable SQLite offset and rate timestamps |
| `TELEGRAM_ALLOWED_CHAT_IDS` | empty | Comma-separated chat IDs explicitly permitted for groups or bot-origin messages |

Private human chats are enabled by default. Groups, channels, edited messages and other bots are ignored unless the relevant chat is explicitly allowlisted (only normal `message` updates are processed). The allowlist is an exception for groups/bots, not a private-user restriction. Rate-limited users are silently dropped, including repeated commands: one accepted update per user per 10 seconds. Rate state is bounded to 10,000 recently active users.

Once the operator securely injects the dedicated token:

```sh
python -B -m telegram_bot serve
```

Do not enable HTTP debug/access logging: Telegram request URLs contain the token. The service disables httpx/httpcore logging and never logs exception representations, user payloads, Telegram response descriptions, or request URLs. Error replies contain fixed safe text. There is no webhook setup and no automatic webhook deletion; an existing webhook for a chosen bot must be deliberately removed by the operator before long polling will work. A polling conflict usually means a second poller or webhook exists.

## Bounds, trust and privacy

- Download: 8 MiB maximum, checked from metadata, content length, and streaming byte count. PNG/JPEG signature/header validation, at most 8192 pixels on either side and 16 million pixels, one frame only, **before OpenCV allocation**.
- Telegram downloads are confined to `https://api.telegram.org/file/bot…/photos/…` or `documents/…` with simple PNG/JPEG filenames; no absolute paths, traversal, encoded components, query strings, or redirects. Proxy environment variables are ignored by the default HTTP client.
- Static single-frame BMP envelopes only (`ctype=1`, seed zero, K 1–10). A fresh existing `svcode.codec.Decoder` handles each upload. Fountain/video streams are intentionally unsupported.
- One image-processing subprocess at a time, killed/reaped after 20 seconds; bounded input and output. Its environment is allowlisted to OS runtime essentials, excluding the Telegram token, other secrets, and Python import injection variables. Download uses finite socket timeouts and an elapsed streaming deadline. All image/reveal data stays in memory; no image temp files to clean. Process memory is released on exit. SQLite stores only offsets and short-lived numeric user/rate timestamps, never images or payloads.
- Genesis, Night Districts and Grydbound public keys mirror `docs/js/scanner.js`. Labels explicitly say **demo**. Verification never proves ownership, transaction inclusion, or confirmation. No private demo key or generator is imported into the service.
- Claim gate requires genesis signature, action C1A1, GEN1 target, zero params, and exactly `{v:3,col:"sv-genesis",supply:100,price:0,exp:0,endpoint:"https://sv-mint.fly.dev"}` with exact types and canonical sorted compact JSON bytes (at most 227 payload bytes). Extra fields, alternate URLs, prices or expiry fail closed. Availability is not queried. The only buttons are fixed `svcode.org` scanner and mint-information pages; no claim is executed.
- Item certificates show bounded collection/item/edition/traits/seed. Registered signatures with a 64-hex nonzero mint reference get a fixed-domain Whatsonchain text link, explicitly unverified on-chain. Unknown signatures are display-only: no reveal and no payload-derived link.
- Genesis blade reveal is renderer-only code extracted from `poc/make_genesis_001.py`, with its geometry unchanged and in-memory output replacing file writes. It contains no key derivation/signing/mint code. Pixel parity is tested against the checked-in #052 reveal. PNG compression bytes can vary with Pillow/zlib, so no canonical `art` hash or ownership claim is made.
- No Telegram parse mode; bounded plain text. Payload text strips control characters and breaks URL/mention auto-link syntax. Link previews are explicitly disabled. Actual returned payload URLs are never requested.

## Offset / failure semantics

Exactly **one service process / machine** should use the DB and token. On a new empty DB, `getUpdates(offset=-1,limit=1)` skips the entire historical backlog, persists the next offset, and processes only subsequent updates. Existing DBs resume from the saved offset. Updates are reserved in a SQLite transaction **before** work: duplicate IDs and restarts cannot replay image work. This deliberately chooses **at-most-once**, not exactly-once: a crash or delivery failure can lose a reply. Users can resend. No automatic resend of failed messages/photos (an ambiguous success could duplicate them).

Polling errors retry after a bounded delay (including Telegram `retry_after`, capped at 60 seconds). Update errors are skipped with a fixed sanitized log. SQLite failures are fatal rather than processing without durable offset state. Do not delete the DB unless intentionally resetting the cursor and dropping pending history.

## Container / Fly example — DO NOT provision automatically

Build context must be the **repository root**:

```sh
docker build -f telegram_bot/Dockerfile -t sv-code-decoder .
```

`Dockerfile.dockerignore` is Docker's Dockerfile-specific context ignore: only this service and `poc/svcode/*.py` are sent. No mint/faucet state, website artifacts, `.env`, credentials, or genesis generator enters the image. Runtime is non-root uid 10001. There is no HTTP service / public port.

`telegram_bot/fly.toml` is an **unlaunched example** for app `sv-code-decoder`: one 512 MiB worker and a persistent `decoder_state` volume at `/data`. The volume must exist and be writable by uid 10001; mounted-volume ownership overrides image-layer directory ownership, so the operator must initialize that ownership before launch. Supply the dedicated token as a Fly secret, never in TOML/build args. Run one machine only (no HA duplicate). Root-context deployment would use `flyctl deploy . --config telegram_bot/fly.toml --ignorefile C:/Users/futur/Desktop/sv-codes/telegram_bot/Dockerfile.dockerignore --ha=false` (substitute the absolute ignorefile path on another machine; Dockerfile is resolved relative to the config) **only after approval**, application/volume provisioning, ownership setup and secure token injection. None of those actions has been performed here.

Offline tests are not evidence of a live Telegram launch or Docker/Fly runtime verification. Actual image reception on a real dedicated bot remains a post-credential smoke test.
