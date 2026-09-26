"""Prepare a hosted Postgres (e.g. Neon) for Meyora.

    python -m scripts.setup_database --env-file ../.env

1. Runs all migrations as the database owner (read from NEON_DATABASE_URL).
2. Creates the runtime role `meyora_app` if it doesn't exist. Hosted owners such as
   Neon's `neondb_owner` have BYPASSRLS, so the app must not connect as them or
   row-level security would silently stop applying.
3. Grants that role row access only (no DDL, no RLS bypass), including tables
   added by future migrations.
4. Writes the app's connection URL (pooled host) to NEON_APP_DATABASE_URL.

Safe to re-run: existing roles keep their password unless --rotate-password is given.
"""

import argparse
import asyncio
import os
import re
import secrets
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import asyncpg
from dotenv import dotenv_values

BACKEND = Path(__file__).resolve().parents[1]
APP_ROLE = "meyora_app"


def _plain(url: str) -> str:
    """asyncpg itself wants postgresql://, SQLAlchemy wants postgresql+asyncpg://."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _app_url(pooled_url: str, password: str) -> str:
    parts = urlsplit(pooled_url)
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=f"{APP_ROLE}:{quote(password, safe='')}@{host}"))


def _set_env(env_file: Path, key: str, value: str) -> None:
    text = env_file.read_text(encoding="utf-8")
    line = f"{key}={value}"
    if re.search(rf"(?m)^{key}=", text):
        text = re.sub(rf"(?m)^{key}=.*$", lambda _: line, text)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    env_file.write_text(text, encoding="utf-8")


def migrate(owner_url: str) -> None:
    env = {**os.environ, "ALEMBIC_DATABASE_URL": owner_url}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)


async def provision(owner_url: str, rotate: bool) -> str | None:
    """Returns a new password when the role was created or rotated, else None."""
    conn = await asyncpg.connect(_plain(owner_url))
    try:
        owner = await conn.fetchval("SELECT current_user")
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname = $1", APP_ROLE)
        password = secrets.token_urlsafe(32) if (rotate or not exists) else None
        async with conn.transaction():
            if not exists:
                # token_urlsafe only yields [A-Za-z0-9_-], so the literal is safe to inline.
                await conn.execute(
                    f"CREATE ROLE {APP_ROLE} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS "
                    f"PASSWORD '{password}'"
                )
            elif password:
                await conn.execute(f"ALTER ROLE {APP_ROLE} PASSWORD '{password}'")
            await conn.execute(f"ALTER ROLE {APP_ROLE} NOBYPASSRLS")
            db = await conn.fetchval("SELECT current_database()")
            for sql in (
                f'GRANT CONNECT ON DATABASE "{db}" TO {APP_ROLE}',
                f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}",
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}",
                f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {APP_ROLE}",
                f"REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM {APP_ROLE}",
                # Tables created by later migrations (run as the owner) get the same grants.
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA public '
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}",
                f'ALTER DEFAULT PRIVILEGES FOR ROLE "{owner}" IN SCHEMA public '
                f"GRANT USAGE, SELECT ON SEQUENCES TO {APP_ROLE}",
            ):
                await conn.execute(sql)
        return password
    finally:
        await conn.close()


async def check(app_url: str) -> None:
    """The app role must be subject to RLS: with no tenant set it sees no tenant rows."""
    conn = await asyncpg.connect(_plain(app_url), statement_cache_size=0)
    try:
        role = await conn.fetchrow("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        assert not role["rolsuper"] and not role["rolbypassrls"], "app role must not bypass RLS"
        visible = await conn.fetchval("SELECT count(*) FROM companies")
        assert visible == 0, "companies visible without a tenant: RLS is not applied"
        try:
            await conn.execute("CREATE TABLE _meyora_ddl_probe (id int)")
            raise AssertionError("app role can create tables")
        except asyncpg.InsufficientPrivilegeError:
            pass
    finally:
        await conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", type=Path, default=BACKEND.parent / ".env")
    parser.add_argument("--rotate-password", action="store_true")
    args = parser.parse_args()

    env = dotenv_values(args.env_file)
    owner_url, pooled_url = env.get("NEON_DATABASE_URL"), env.get("NEON_DATABASE_URL_POOLED")
    if not owner_url or not pooled_url:
        sys.exit("Set NEON_DATABASE_URL and NEON_DATABASE_URL_POOLED in the env file first.")

    print("Running migrations as the owner…")
    migrate(owner_url)
    print(f"Provisioning role {APP_ROLE}…")
    password = asyncio.run(provision(owner_url, args.rotate_password))
    if password:
        _set_env(args.env_file, "NEON_APP_DATABASE_URL", _app_url(pooled_url, password))
        print(f"Saved NEON_APP_DATABASE_URL to {args.env_file.name}.")
    app_url = dotenv_values(args.env_file).get("NEON_APP_DATABASE_URL")
    if not app_url:
        sys.exit("NEON_APP_DATABASE_URL is missing; re-run with --rotate-password to create it.")
    asyncio.run(check(app_url))
    print("Checked: app role connects through the pooler, can't bypass RLS and can't change the schema.")


if __name__ == "__main__":
    main()
