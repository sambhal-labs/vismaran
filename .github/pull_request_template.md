<!-- Title should follow Conventional Commits, e.g. "feat(graph): add Kuzu backend" -->

## What & why

<!-- What does this change do, and why is it needed? Link any issue/discussion. -->

## Approach

<!-- Key decisions, trade-offs, anything a reviewer should focus on. -->

## Test plan

<!-- TDD: which test(s) would have failed before this change? -->

- [ ] Unit tests added/updated (`make test-unit`)
- [ ] Integration tests added/updated (`make test`, requires `make up`)
- [ ] `make lint` and `make typecheck` clean

## Compliance impact

<!-- For changes touching erasure, adapters, provenance, or receipts: -->

- [ ] Does this change what a signed receipt attests to? (If yes, explain.)
- [ ] Could this leave subject data behind in any store? (If no, how do you know?)
- [ ] N/A — no erasure-path or receipt change
