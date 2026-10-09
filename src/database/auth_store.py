"""
auth_store.py
-------------
Handles user account persistence for authentication.

Storage strategy (same dual-layer as the rest of the app):
  1. DynamoDB Users table (primary) — UserId = email, PasswordHash = bcrypt hash
  2. local_data.json under the 'users' collection (offline fallback)

Passwords are NEVER stored in plaintext. bcrypt is used with a work factor
of 12 rounds, which is suitable for a web application.
"""

import logging
import os
from typing import Optional

import bcrypt

from src.database.local_store import load_items, save_items

logger = logging.getLogger(__name__)

AWS_REGION           = os.environ.get("AWS_REGION", "us-east-1")
USERS_TABLE          = os.environ.get("USERS_TABLE", "Users")


# ---------------------------------------------------------------------------
# DynamoDB helpers (graceful fallback if AWS not available)
# ---------------------------------------------------------------------------

def _get_users_table():
    import boto3
    return boto3.resource("dynamodb", region_name=AWS_REGION).Table(USERS_TABLE)


def _dynamo_get_user(email: str) -> Optional[dict]:
    try:
        response = _get_users_table().get_item(Key={"UserId": email})
        return response.get("Item")
    except Exception as exc:
        logger.warning("DynamoDB get_user failed for %s: %s", email, exc)
        return None


def _dynamo_put_user(user: dict) -> bool:
    try:
        _get_users_table().put_item(Item=user)
        return True
    except Exception as exc:
        logger.warning("DynamoDB put_user failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Local fallback helpers
# ---------------------------------------------------------------------------

def _local_get_user(email: str) -> Optional[dict]:
    for user in load_items("users"):
        if user.get("UserId") == email:
            return user
    return None


def _local_put_user(user: dict) -> None:
    users = load_items("users")
    users = [u for u in users if u.get("UserId") != user["UserId"]]
    users.append(user)
    save_items("users", users)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_user(email: str) -> Optional[dict]:
    """
    Look up a user by email. Tries DynamoDB first, then local fallback.
    Returns the raw user dict (contains PasswordHash) or None.
    """
    user = _dynamo_get_user(email)
    if user:
        return user
    return _local_get_user(email)


def create_user(email: str, password: str, display_name: str = "") -> tuple[bool, str]:
    """
    Register a new user.

    Returns (True, "") on success, or (False, error_message) on failure.
    Passwords are hashed with bcrypt before any storage.
    """
    if get_user(email):
        return False, "An account with this email already exists."

    if len(password) < 8:
        return False, "Password must be at least 8 characters."

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    user = {
        "UserId":       email,
        "Email":        email,
        "DisplayName":  display_name or email.split("@")[0],
        "PasswordHash": password_hash,
    }

    saved_to_dynamo = _dynamo_put_user(user)
    _local_put_user(user)   # always write locally as backup

    return True, ""


def verify_password(email: str, password: str) -> tuple[bool, Optional[dict]]:
    """
    Verify a login attempt.

    Returns (True, user_dict) on success, (False, None) on failure.
    Uses bcrypt.checkpw for timing-safe comparison.
    """
    user = get_user(email)
    if not user:
        # Run a dummy hash to prevent user-enumeration via timing
        bcrypt.checkpw(b"dummy", bcrypt.hashpw(b"dummy", bcrypt.gensalt(rounds=12)))
        return False, None

    stored_hash = user.get("PasswordHash", "")
    if not stored_hash:
        return False, None

    try:
        match = bcrypt.checkpw(password.encode(), stored_hash.encode())
    except Exception:
        return False, None

    if match:
        return True, user
    return False, None
