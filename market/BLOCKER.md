# Resolved design mismatch; production blockers remain

The old draft 0→0 invariant was our design, not a user requirement. The selected supported OrdLockV2 path now uses exact BigInt cumulative sat-flow, with explicit front funding/cushion and same-index seller payout. Offline new-script creation, purchase and alternative cancel work and execute the real SDK interpreter. V1 creation stays deprecated; legacy vectors are compatibility-only.

Public paidTradingEnabled remains false. Missing front funding/sourceBEEF: FRONT_FUNDING_CAPABILITY_BLOCKED. Wallet returned-layout/no deferred AtomicBEEF: WALLET_CAPABILITY_BLOCKED. No automatic front preparation, @1sat/actions, wallet signing or broadcast.

Remaining: production certificate/anchor/chain/status/asset-free funding providers; real CWI layout/no-send/signature testing; durable reservations and reconciliation; separately reviewed user-approved signing/send. Synthetic proof and mock CWI are not live availability, SPV or wallet evidence. See README.md.
