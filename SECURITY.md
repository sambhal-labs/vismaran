# Security Policy

## Reporting a vulnerability

Vismaran handles deletion of personal data and signs receipts that may be used
as compliance evidence. Security issues are taken seriously.

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, use [GitHub's private vulnerability reporting](https://github.com/sambhal-labs/vismaran/security/advisories/new)
("Report a vulnerability" under the Security tab). We aim to acknowledge within
72 hours.

## Scope of particular interest

- **Receipt forgery** — any way to produce a receipt that `vismaran verify`
  accepts without the operator's signing key, or to mutate a signed receipt
  without detection.
- **Incomplete erasure** — any path where `erase` reports success (and signs a
  receipt) while subject data survives in a target store. The
  `ModelInference`-cascade case in the TensorZero adapter is a known sharp edge;
  reports of similar leaks in any adapter are high priority.
- **Subject identifier leakage** — the raw subject identifier appearing anywhere
  in a receipt (receipts hold only a salted hash).
- **Provenance bypass** — writes that escape the provenance contract and become
  un-erasable.

## What is explicitly out of scope (by design)

Vismaran's threat model (see [`SPEC.md`](SPEC.md) and
[`docs/architecture/4-threat.mmd`](docs/architecture/4-threat.mmd)) does **not**
claim to erase: database backups, off-platform copies, model weights/fine-tunes
already trained on the data, or third-party observability mirrors. These require
separate controls and are not vulnerabilities in Vismaran.
