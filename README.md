# zonedrop

**Idempotent Namecheap DNS zone sync with safety guards.**

Think of it as a DNS zone "upsert" — declare the records you want, and zonedrop
merges them into the existing zone while ensuring critical infrastructure records
are never accidentally removed.

## Features

- **Idempotent** — no write happens if the zone already matches your desired state
- **Safety guards** — infrastructure record protection, minimum record count
- **Backup before write** — every write is preceded by a full zone backup to disk
- **Post-write verification** — reads back the zone after writing and retries if records are missing
- **Dry-run mode** — see what would change without touching the zone

## Usage

```bash
# CLI
zonedrop \
  --api-user YOUR_USER \
  --api-key YOUR_KEY \
  --client-ip YOUR_IP \
  --sld example --tld com \
  --record "www:1.2.3.4" \
  --record "api:5.6.7.8" \
  --infra "ns1" --infra "ns2" \
  --backup-dir /backups

# Docker
docker run --rm \
  -v /host/backups:/backups \
  your-registry/zonedrop \
  --api-user YOUR_USER \
  --api-key YOUR_KEY \
  --client-ip YOUR_IP \
  --sld example --tld com \
  --record "www:1.2.3.4" \
  --backup-dir /backups
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0    | Zone unchanged or written and verified |
| 1    | Guard violation, API failure, or verify failure |

## Safety

Namecheap's `setHosts` API **replaces the entire zone**. zonedrop protects you by:

1. **Fetching existing records** before any write
2. **Merging** desired records into the existing set (does not remove unmanaged records)
3. **Checking infra records** — if any `--infra` record would be missing after merge, it aborts
4. **Minimum count guard** — rejects writes that would leave fewer than `--min-records` records
5. **Backup** — writes the pre-existing zone to `--backup-dir` before making changes
6. **Verification** — reads back the zone after writing and retries up to `--verify-retries` times
