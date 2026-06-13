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

## Credentials

Credentials can be provided in three ways, checked in this order:

### 1. CLI arguments (highest priority)

```bash
zonedrop --api-user USER --api-key KEY --client-ip IP ...
```

### 2. Environment variables

```bash
export ZONEDROP_API_USER=your_user
export ZONEDROP_API_KEY=your_key
export ZONEDROP_CLIENT_IP=your_ip
zonedrop ...
```

Or copy `.env.example` to `.env` and fill it in:

```bash
cp .env.example .env
# edit .env with your credentials
export $(grep -v '^#' .env | xargs)
zonedrop ...
```

### 3. Encrypted vault file (`~/.zonedrop.vault`, lowest priority)

```bash
# Install cryptography support
pip install zonedrop[vault]

# Encrypt your credentials from environment variables
export ZONEDROP_API_USER=your_user
export ZONEDROP_API_KEY=your_key
export ZONEDROP_CLIENT_IP=your_ip
zonedrop vault encrypt

# Use the vault
export ZONEDROP_VAULT_PASSWORD=your_vault_password
zonedrop ...

# View stored credentials
zonedrop vault decrypt
```

## Usage

```bash
# CLI
zonedrop \
  --sld example --tld com \
  --record "www:1.2.3.4" \
  --record "api:5.6.7.8" \
  --infra "ns1" --infra "ns2" \
  --backup-dir /backups

# Docker
docker run --rm \
  -v /host/backups:/backups \
  -e ZONEDROP_API_USER \
  -e ZONEDROP_API_KEY \
  -e ZONEDROP_CLIENT_IP \
  your-registry/zonedrop \
  --sld example --tld com \
  --record "www:1.2.3.4"
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
