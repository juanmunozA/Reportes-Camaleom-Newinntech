from __future__ import annotations

import base64
import hashlib
from contextlib import contextmanager
from typing import Any

import bcrypt
import psycopg2
import psycopg2.extras
from cryptography.fernet import Fernet

from ..config import DATABASE_URL, ENCRYPTION_KEY

_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_users (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS camaleom_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
    azure_org TEXT,
    azure_project TEXT,
    azure_team TEXT,
    azure_full_name TEXT,
    camaleom_user TEXT,
    camaleom_pass_enc TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _fernet() -> Fernet:
    if not ENCRYPTION_KEY:
        raise RuntimeError("Falta ENCRYPTION_KEY para cifrar/descifrar credenciales.")
    # Deriva una clave Fernet valida (32 bytes url-safe base64) a partir de cualquier string.
    digest = hashlib.sha256(ENCRYPTION_KEY.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt(value: str) -> str:
    if not value:
        return ""
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


@contextmanager
def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("Falta DATABASE_URL (Postgres) configurada.")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(_SCHEMA)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def create_user(email: str, password: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO app_users (email, password_hash) VALUES (%s, %s) RETURNING id",
                (email.strip().lower(), hash_password(password)),
            )
            return cur.fetchone()[0]


def get_user_by_email(email: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM app_users WHERE email = %s", (email.strip().lower(),))
            row = cur.fetchone()
            return dict(row) if row else None


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM app_users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None


def save_profile(
    user_id: int,
    azure_org: str,
    azure_project: str,
    azure_team: str,
    azure_full_name: str,
    camaleom_user: str,
    camaleom_pass: str | None,
) -> None:
    camaleom_pass_enc = encrypt(camaleom_pass) if camaleom_pass else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            if camaleom_pass_enc is not None:
                cur.execute(
                    """
                    INSERT INTO camaleom_profiles
                        (user_id, azure_org, azure_project, azure_team, azure_full_name, camaleom_user, camaleom_pass_enc, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (user_id) DO UPDATE SET
                        azure_org = EXCLUDED.azure_org,
                        azure_project = EXCLUDED.azure_project,
                        azure_team = EXCLUDED.azure_team,
                        azure_full_name = EXCLUDED.azure_full_name,
                        camaleom_user = EXCLUDED.camaleom_user,
                        camaleom_pass_enc = EXCLUDED.camaleom_pass_enc,
                        updated_at = now()
                    """,
                    (user_id, azure_org, azure_project, azure_team, azure_full_name, camaleom_user, camaleom_pass_enc),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO camaleom_profiles
                        (user_id, azure_org, azure_project, azure_team, azure_full_name, camaleom_user, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (user_id) DO UPDATE SET
                        azure_org = EXCLUDED.azure_org,
                        azure_project = EXCLUDED.azure_project,
                        azure_team = EXCLUDED.azure_team,
                        azure_full_name = EXCLUDED.azure_full_name,
                        camaleom_user = EXCLUDED.camaleom_user,
                        updated_at = now()
                    """,
                    (user_id, azure_org, azure_project, azure_team, azure_full_name, camaleom_user),
                )


def get_profile(user_id: int) -> dict[str, Any] | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM camaleom_profiles WHERE user_id = %s", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None
