# Shared treasury atomic self-trade checkpoint

## Verified implementation

The authorized shared treasury CLI has a fixed-purpose `atomic-test` mode. It uses an isolated pinned SDK2/template dependency set, while ordinary sends retain SDK3. Every spending path uses the shared lock, killfile gates and durable public journal.

Parent verification: `bun test --timeout 30000` in `C:/Users/futur/.hermes/agent-treasury/atomic-test` returned **23 passed, 0 failed, 123 assertions**. Parent added exact funding/cancellation sighash `0x41` checks and paced explorer requests to one per second after a read-only plan received HTTP 429. No private key files were read by review tools and no new key was generated.

## Fixed budget and limits

- Shared address: `1GjcRUKdwqsnrxCHiDoHtF57rKqDd8oibT`.
- Dedicated allocation: 7,002 sats; bootstrap fee: 300 sats.
- Five stages: bootstrap, listing-sale, listing-cancel, purchase, cancel.
- Fixed fee per stage: 300 sats; full run: 1,500 sats; hard fee budget: 3,000 sats.
- Fixed self-payment price: 1,234 sats. All destinations are the same treasury address.
- The original 10,000-satoshi principal cap and human-only killfile removal remain enforced.
- Two independent disposable test assets exercise purchase and cancellation. No edition #052 spend or public mint claim.

## Actual bootstrap receipt

- Txid: `c3ce32e78dede3309b9a4143fb2ed867f3ef7159aa0da0816e3c82a24415cde9`.
- Source: `8793ab0efb9d8e89c47e89726637ff984f993c0f428462c999837e3ca1432cb2:2`, value 4,990,020 sats.
- Output values: `[1, 1, 5000, 500, 500, 500, 500, 4982718]`, all treasury P2PKH.
- Fixed fee: 300 sats.
- ARC response accepted. Parent independently fetched WoC raw bytes, matched the journal's exact signed transaction, and recomputed the txid.
- At checkpoint: explorer confirmation and block-height fields were null. A later read-only reconciliation attempt returned `API_HTTP_429`; the signed bootstrap remains pending/reserved, with no retries or further spending attempted after that result. This is **broadcast/visible, not confirmed**. No listing, purchase or cancellation has been broadcast.

## Resume without bypassing safety

1. Inspect `bun C:/Users/futur/.hermes/agent-treasury/treasury.ts atomic-test status`.
2. Run `... atomic-test reconcile` only to read back the exact pending txid and require confirmed/indexed outputs. It does not resend.
3. Only after successful reconciliation, run `... atomic-test plan`, inspect the fresh exact stage/output/fee/source report, and execute that stage using its returned digest. Never reuse another stage's digest or automatically loop broadcasts.
4. Stop on policy, cap, killfile, funding, unexpected spender or broadcast failure. Ambiguous outcomes remain reserved; no rebuilt resend, journal deletion, killfile deletion or manual release of protected assets.

Ordinary treasury sends also require reconciliation before further spending if this run or another send is pending. Public treasury state is held in `spending-state.json`; the signer treats missing initialized state and incomplete writes as blockers.

## What remains unproven

Live listing/purchase/cancellation, relay acceptance of their fixed fees, real two-wallet trading, Yours interoperability, production issuer provenance, and independent SPV. This same-key test does not prove separate buyer/seller identity or production marketplace readiness. Public paid trading remains disabled.
