"""Command-line interface for zonedrop."""

import argparse
import os
import sys
import textwrap

from zonedrop import __version__
from zonedrop.sync import sync_zone
from zonedrop.vault import vault_cmd, _load_vault, VAULT_PATH


_ENV_PREFIX = "ZONEDROP_"


def _resolve_creds(args: argparse.Namespace) -> tuple[str, str, str]:
    """Resolve API credentials from CLI args/env, falling back to vault."""
    api_user = args.api_user
    api_key = args.api_key
    client_ip = args.client_ip
    if not api_user and not api_key and not client_ip:
        pwd = os.environ.get(_ENV_PREFIX + "VAULT_PASSWORD", "")
        if pwd and os.path.exists(VAULT_PATH):
            try:
                data = _load_vault(VAULT_PATH, pwd)
                api_user = data.get("ZONEDROP_API_USER", "")
                api_key = data.get("ZONEDROP_API_KEY", "")
                client_ip = data.get("ZONEDROP_CLIENT_IP", "")
            except Exception:
                pass
    return api_user, api_key, client_ip


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="zonedrop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent("""\
            Idempotent Namecheap DNS zone sync with safety guards.

            Reads existing DNS records, merges desired records, verifies
            infrastructure records are intact, backs up the current zone,
            writes the new zone, and verifies the write succeeded.

            Exit codes:
              0  zone unchanged (no write needed)
              0  zone written and verified (check stdout for details)
              1  error (guard violation, API failure, verify failure)
        """),
    )
    parser.add_argument(
        "--version", action="version", version=f"zonedrop {__version__}"
    )

    # Auth
    auth = parser.add_argument_group("Namecheap API credentials")
    auth.add_argument(
        "--api-user",
        default=os.environ.get(_ENV_PREFIX + "API_USER", ""),
        required=not bool(os.environ.get(_ENV_PREFIX + "API_USER")),
        help="Namecheap API username. Env: ZONEDROP_API_USER",
    )
    auth.add_argument(
        "--api-key",
        default=os.environ.get(_ENV_PREFIX + "API_KEY", ""),
        required=not bool(os.environ.get(_ENV_PREFIX + "API_KEY")),
        help="Namecheap API key. Env: ZONEDROP_API_KEY",
    )
    auth.add_argument(
        "--client-ip",
        default=os.environ.get(_ENV_PREFIX + "CLIENT_IP", ""),
        required=not bool(os.environ.get(_ENV_PREFIX + "CLIENT_IP")),
        help="Whitelisted client IP for API access. Env: ZONEDROP_CLIENT_IP",
    )

    # Domain
    domain = parser.add_argument_group("Domain")
    domain.add_argument("--sld", required=True, help="Second-level domain (e.g. example)")
    domain.add_argument("--tld", required=True, help="Top-level domain (e.g. com)")

    # Records
    rec = parser.add_argument_group("Records")
    rec.add_argument(
        "--record",
        action="append",
        default=[],
        metavar="NAME:VALUE",
        help="DNS record in the form name:address. Can be specified multiple times.",
    )
    rec.add_argument(
        "--infra",
        action="append",
        default=[],
        metavar="NAME",
        help="Infrastructure record name that must never be removed. Can be specified multiple times.",
    )
    rec.add_argument(
        "--min-records",
        type=int,
        default=4,
        help="Minimum total records required after merge (default: 4)",
    )
    rec.add_argument(
        "--type",
        default="A",
        dest="record_type",
        help="Record type for --record entries (default: A)",
    )
    rec.add_argument(
        "--ttl",
        default="300",
        help="TTL for --record entries (default: 300)",
    )

    # Behavior
    beh = parser.add_argument_group("Behavior")
    beh.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would change but do not write",
    )
    beh.add_argument(
        "--backup-dir",
        default=None,
        help="Directory for pre-write zone backups (default: ./zonedrop-backups/)",
    )
    beh.add_argument(
        "--verify-retries",
        type=int,
        default=5,
        help="Number of post-write verification attempts (default: 5)",
    )
    beh.add_argument(
        "--verify-delay",
        type=float,
        default=3.0,
        help="Seconds between verification retries (default: 3.0)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    # Handle `zonedrop vault encrypt|decrypt` before argparse
    if argv and argv[0] == "vault":
        return vault_cmd(argv[1:])

    parser = build_parser()
    args = parser.parse_args(argv)

    records = []
    for r in args.record:
        if ":" not in r:
            parser.error(f"Invalid record format: {r!r} (expected name:address)")
        name, address = r.split(":", 1)
        records.append({
            "Name": name,
            "Type": args.record_type,
            "Address": address,
            "TTL": args.ttl,
        })
    infra = set(args.infra)

    api_user, api_key, client_ip = _resolve_creds(args)
    if not api_user or not api_key or not client_ip:
        parser.error(
            "API credentials required. Provide via --api-user/--api-key/--client-ip, "
            f"environment variables ({_ENV_PREFIX}API_USER, etc.), "
            f"or {_ENV_PREFIX}VAULT_PASSWORD + ~/.zonedrop.vault"
        )

    try:
        result = sync_zone(
            api_user=api_user,
            api_key=api_key,
            client_ip=client_ip,
            sld=args.sld,
            tld=args.tld,
            records=records,
            infra_names=infra,
            min_records=args.min_records,
            backup_dir=args.backup_dir,
            dry_run=args.dry_run,
            verify_retries=args.verify_retries,
            verify_delay=args.verify_delay,
        )
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    action = result["action"]
    if action == "unchanged":
        print(f"UNCHANGED — no write needed ({result['existing_count']} records already correct)")
        return 0
    elif action == "dry_run":
        print(f"DRY RUN — would write {result['merged_count']} records (currently {result['existing_count']})")
        return 0
    elif action == "written":
        print(f"OK — {result['merged_count']} records written (was {result['existing_count']})")
        if result["backup_path"]:
            print(f"Backup: {result['backup_path']}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
