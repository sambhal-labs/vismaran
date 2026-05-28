"""Vismaran CLI — ``uv run vismaran ...``.

Three subcommands in v0.1:
- ``vismaran erase --subject ... [--dry-run]``
- ``vismaran verify <receipt.json> [--pubkey <pubkey.pem>]``
- ``vismaran keygen [--out keys/operator.key]``

Wired to the orchestrator + receipt signer once those land (see SPEC.md).
"""

from __future__ import annotations

import click


@click.group()
@click.version_option(package_name="vismaran")
def main() -> None:
    """Vismaran — provable right-to-be-forgotten for AI agent memory."""


@main.command()
@click.option("--subject", required=True, help="Subject identifier (e.g., email).")
@click.option("--dry-run", is_flag=True, help="Preview only; no mutation, no receipt.")
@click.option(
    "--out", default="receipt.json", type=click.Path(), help="Where to write the signed receipt."
)
def erase(subject: str, dry_run: bool, out: str) -> None:
    """Erase a subject across all registered adapters."""
    click.echo(f"[not implemented] would erase subject={subject!r} dry_run={dry_run} -> {out}")
    click.echo("Erasure orchestration is not implemented yet; see SPEC.md.")


@main.command()
@click.argument("receipt_path", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--pubkey", type=click.Path(exists=True, dir_okay=False), help="Operator's Ed25519 public key."
)
def verify(receipt_path: str, pubkey: str | None) -> None:
    """Verify a signed deletion receipt offline."""
    click.echo(f"[not implemented] would verify {receipt_path} against pubkey={pubkey}")
    click.echo("Receipt verification is not implemented yet; see SPEC.md (Receipt format).")


@main.command()
@click.option(
    "--out", default="keys/operator.key", type=click.Path(), help="Where to write the private key."
)
def keygen(out: str) -> None:
    """Generate a new Ed25519 signing keypair."""
    click.echo(f"[not implemented] would generate Ed25519 keypair at {out} (+ {out}.pub)")
    click.echo("Key generation is not implemented yet; see SPEC.md.")


if __name__ == "__main__":
    main()
