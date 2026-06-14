"""Encrypted config file management for zonedrop credentials.

Uses AES-256-GCM via Python's cryptography library to store API credentials
in an encrypted JSON file (default: ~/.zonedrop.vault).

Usage:
    zonedrop vault encrypt   # prompts for password, writes ~/.zonedrop.vault
    zonedrop vault decrypt   # prompts for password, prints credentials to stdout
"""

import getpass
import json
import os
import sys
from typing import Optional

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from cryptography.hazmat.primitives import hashes
except ImportError:
    AESGCM = None  # type: ignore

VAULT_PATH = os.path.join(os.path.expanduser("~"), ".zonedrop.vault")
SALT = b"zonedrop-v1-salt"  # static salt; the password provides the entropy
ITERATIONS = 600_000
KEY_LENGTH = 32  # AES-256


def _derive_key(password: str) -> bytes:
    if AESGCM is None:
        raise RuntimeError(
            "cryptography package required for vault operations.\n"
            "Install: pip install cryptography"
        )
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_LENGTH,
        salt=SALT,
        iterations=ITERATIONS,
    )
    return kdf.derive(password.encode())


def _load_vault(path: str, password: str) -> dict:
    if AESGCM is None:
        raise RuntimeError("cryptography package required")
    with open(path, "rb") as f:
        nonce = f.read(12)
        ct = f.read()
    key = _derive_key(password)
    aesgcm = AESGCM(key)
    plaintext = aesgcm.decrypt(nonce, ct, None)
    return json.loads(plaintext.decode())


def _save_vault(path: str, password: str, data: dict) -> None:
    if AESGCM is None:
        raise RuntimeError("cryptography package required")
    key = _derive_key(password)
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ct = aesgcm.encrypt(nonce, json.dumps(data).encode(), None)
    with open(path, "wb") as f:
        f.write(nonce)
        f.write(ct)
    os.chmod(path, 0o600)


def vault_cmd(args: list[str]) -> int:
    """Handle `zonedrop vault encrypt|decrypt`."""
    if AESGCM is None:
        print("ERROR: cryptography not installed. Run: pip install cryptography", file=sys.stderr)
        return 1

    if not args:
        print("Usage: zonedrop vault encrypt|decrypt", file=sys.stderr)
        return 1

    cmd = args[0]
    path = VAULT_PATH

    if cmd == "encrypt":
        if os.path.exists(path):
            print(f"ERROR: {path} already exists — remove it first to re-encrypt", file=sys.stderr)
            return 1
        password = getpass.getpass("Vault password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("ERROR: passwords do not match", file=sys.stderr)
            return 1
        data = {
            "ZONEDROP_API_USER": os.environ.get("ZONEDROP_API_USER", ""),
            "ZONEDROP_API_KEY": os.environ.get("ZONEDROP_API_KEY", ""),
            "ZONEDROP_CLIENT_IP": os.environ.get("ZONEDROP_CLIENT_IP", ""),
        }
        if not any(data.values()):
            print(
                "WARNING: no ZONEDROP_API_USER / ZONEDROP_API_KEY / ZONEDROP_CLIENT_IP "
                "environment variables set — vault will be empty",
            )
        _save_vault(path, password, data)
        print(f"Vault written to {path}")
        return 0

    elif cmd == "decrypt":
        if not os.path.exists(path):
            print(f"ERROR: {path} not found", file=sys.stderr)
            return 1
        password = getpass.getpass("Vault password: ")
        try:
            data = _load_vault(path, password)
        except Exception:
            print("ERROR: decryption failed (wrong password or corrupted vault)", file=sys.stderr)
            return 1
        for k, v in data.items():
            print(f"{k}={v}")
        return 0

    else:
        print(f"Unknown vault command: {cmd}", file=sys.stderr)
        print("Usage: zonedrop vault encrypt|decrypt", file=sys.stderr)
        return 1
