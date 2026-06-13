"""Core DNS sync logic: read, merge, guard, backup, write, verify."""

import json
import os
import time
import datetime
from typing import Optional

from zonedrop.namecheap import get_hosts, set_hosts


def sync_zone(
    api_user: str,
    api_key: str,
    client_ip: str,
    sld: str,
    tld: str,
    records: list[dict[str, str]],
    *,
    infra_names: Optional[set[str]] = None,
    min_records: int = 4,
    backup_dir: Optional[str] = None,
    dry_run: bool = False,
    verify_retries: int = 5,
    verify_delay: float = 3.0,
) -> dict:
    """Idempotently sync DNS records for a domain.

    Args:
        api_user: Namecheap API username.
        api_key: Namecheap API key.
        client_ip: Whitelisted IP for Namecheap API.
        sld: Second-level domain (e.g. "example").
        tld: Top-level domain (e.g. "com").
        records: Desired DNS records as list of {"Name", "Type", "Address", "TTL"}.
        infra_names: Set of record names that must never be removed (enforced after merge).
        min_records: Minimum total records required (safety guard).
        backup_dir: Directory to write pre-write backups. Defaults to CWD/zonedrop-backups.
        dry_run: If True, print what would change but don't write.
        verify_retries: Number of post-write verification attempts.
        verify_delay: Seconds between verification retries.

    Returns:
        Dict with keys:
            action: "unchanged" | "written" | "dry_run"
            existing_count: int
            merged_count: int
            backup_path: str | None
    """
    infra_names = infra_names or set()

    # 1. Fetch existing records
    existing = get_hosts(api_user, api_key, client_ip, sld, tld)

    # 2. Build merged set: keep existing records not being replaced, add desired
    replace_names = {r["Name"] for r in records}
    merged = [r for r in existing if r["Name"] not in replace_names]
    merged.extend(records)

    # 3. Ensure infra records are present
    infra_present = {r["Name"] for r in merged}
    missing_infra = infra_names - infra_present
    if missing_infra:
        raise RuntimeError(
            f"ABORT: infra records missing after merge: {', '.join(sorted(missing_infra))}"
            " — refusing to write"
        )

    # 4. Minimum record count guard
    if len(merged) < min_records:
        raise RuntimeError(
            f"ABORT: only {len(merged)} records, minimum is {min_records}"
            " — refusing to write"
        )

    # 5. Idempotency check
    def _key(r):
        return (r["Name"], r["Type"], r["Address"], r.get("TTL", "300"))
    if {_key(r) for r in existing} == {_key(r) for r in merged}:
        return {
            "action": "unchanged",
            "existing_count": len(existing),
            "merged_count": len(merged),
            "backup_path": None,
        }

    if dry_run:
        return {
            "action": "dry_run",
            "existing_count": len(existing),
            "merged_count": len(merged),
            "backup_path": None,
        }

    # 6. Backup before write
    bp = None
    if backup_dir is None:
        backup_dir = os.path.join(os.getcwd(), "zonedrop-backups")
    os.makedirs(backup_dir, exist_ok=True)
    bp = os.path.join(
        backup_dir,
        f"dns-backup-{datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%S')}.json",
    )
    with open(bp, "w") as f:
        json.dump(existing, f, indent=2)

    # 7. Write
    set_hosts(api_user, api_key, client_ip, sld, tld, merged)

    # 8. Post-write verification with retry
    for attempt in range(1, verify_retries + 1):
        after = get_hosts(api_user, api_key, client_ip, sld, tld)
        after_names = {r["Name"] for r in after}
        expected_names = {r["Name"] for r in merged}
        dropped = expected_names - after_names
        if not dropped and len(after) >= len(merged):
            return {
                "action": "written",
                "existing_count": len(existing),
                "merged_count": len(merged),
                "backup_path": bp,
            }
        if attempt < verify_retries:
            time.sleep(verify_delay)
        else:
            raise RuntimeError(
                f"POST-WRITE VERIFY FAILED: still missing records after {verify_retries} attempts: "
                f"{', '.join(sorted(dropped))}"
            )

    return {
        "action": "written",
        "existing_count": len(existing),
        "merged_count": len(merged),
        "backup_path": bp,
    }
