# Shared treasury atomic-test acceptance

This is a bounded self-trade integration test, not production marketplace activation and not a Yours Wallet compatibility test.

## Authority boundary

Use only `bun C:/Users/futur/.hermes/agent-treasury/treasury.ts` and its reviewed fixed-purpose atomic-test commands. The authorized shared mainnet address is `1GjcRUKdwqsnrxCHiDoHtF57rKqDd8oibT`. Do not generate another wallet, WIF, mnemonic, or project key file. Do not read, copy, print, or shell-pass the encrypted key or wrapping-key files. Key access remains inside the existing treasury signer boundary.

The shared signer must retain the 10,000-satoshi per-send cap and `STOP_SPENDING` killfile. Agents must not delete that killfile. Cap, killfile, empty-wallet, policy, or broadcast failures stop execution; they are not permission to bypass a guard.

## What the test must demonstrate

- A fixed-purpose plan creates isolated test assets under the same treasury key. Do not consume SV-GENESIS supply or spend edition #052.
- Supported OrdLockV2 scripts hold the test outputs with exact treasury payout and cancellation identity.
- A purchase pays the fixed seller amount and maps the collectible satoshi exactly into its one-satoshi treasury receive output.
- A separate test asset demonstrates cancellation. Cancellation and purchase must not be reported as successive valid spends of the same listing output.
- All relevant scripts execute under the actual interpreter before any broadcast. All funding signatures commit to the full output layout, not merely the seller payout.
- Each accepted transaction is independently checked by raw transaction hash, actual output values/scripts and explorer visibility. Broadcast acceptance is not confirmation.

All economic roles belong to the same treasury key. A successful self-trade establishes script execution, transaction construction and chain acceptance; it does not establish a trade between independent owners, custody separation, production issuer authenticity, or actual Yours extension support.

## Signer policy requirements

- No general sign-raw endpoint, arbitrary destination, arbitrary script, caller-supplied fee, or caller-supplied collectible outpoint.
- Produce an inspectable dry-run before execution. Bind approved fixed stages to exact prior transaction bytes and expected outputs.
- Limit each execution to one transaction. Pin a total fee budget before the first send, in addition to the per-send amount cap. Return a confirmation-wait state rather than looping broadcasts.
- Enforce a cross-profile exclusive spend lock. Ordinary sends must not consume test collectibles or stage-reserved funding.
- Recheck the killfile before signing and immediately before broadcasting. Missing/corrupt state fails closed.
- Persist the exact signed transaction identity and pending state before the network call. An unknown broadcast outcome must reconcile the original txid, never rebuild and automatically send again.
- Store only public transaction/recovery data outside the existing key boundary. Do not upload treasury secret material to the product repository.

## Release gate

The shared signer extension requires parent review of its complete policy and test output before any real-key invocation. Tests must cover cap/fee limits, strict amount parsing, killfile timing, concurrent access, asset exclusion, state corruption, layout tampering, and ambiguous broadcasts. An unsigned live plan may inspect public UTXOs but must not load the key.

Keep the public market's `paidTradingEnabled:false`. Real-wallet interoperability, production issuance, funding classification, independent proof policy, and marketplace settlement/recovery remain separate acceptance criteria.
