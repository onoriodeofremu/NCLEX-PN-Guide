"""Lightweight username/password auth for a small, personal-use app.

Passwords are never stored in plain text: each is salted and run through
PBKDF2-HMAC-SHA256 (200,000 iterations) before being written to storage,
using only the Python standard library for the hashing itself (no extra
dependency to install). Where the account record actually lives — a free
hosted database, or a local file — is handled by storage.py and is
invisible from here.

This is intentionally simple — built for a small group of friends and
family using one shared app, not a public product with thousands of users.
"""
from __future__ import annotations

import hashlib
import re
import secrets

import storage

USERNAME_RE = re.compile(r"^[a-z0-9_]{3,20}$")
PBKDF2_ITERATIONS = 200_000


def _hash_password(password: str, salt_hex: str | None = None) -> tuple[str, str]:
    salt = bytes.fromhex(salt_hex) if salt_hex else secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return salt.hex(), digest.hex()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def create_account(username: str, password: str) -> tuple[bool, str]:
    username = normalize_username(username)
    if not USERNAME_RE.match(username):
        return False, "Username must be 3-20 characters: lowercase letters, numbers, and underscore only."
    if len(password) < 6:
        return False, "Password must be at least 6 characters."
    if storage.username_exists(username):
        return False, "That username is already taken. Try another one."
    salt_hex, hash_hex = _hash_password(password)
    storage.create_user(username, salt_hex, hash_hex)
    return True, "Account created."


def verify_login(username: str, password: str) -> bool:
    username = normalize_username(username)
    record = storage.get_user(username)
    if not record:
        return False
    _, computed_hash = _hash_password(password, record["salt"])
    # constant-time comparison to avoid leaking timing information
    return secrets.compare_digest(computed_hash, record["hash"])