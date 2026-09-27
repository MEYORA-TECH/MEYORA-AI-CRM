"""Copy all Meyora data from one Postgres to another (e.g. moving Neon regions).

    python -m scripts.copy_database --source OLD_US_EAST_NEON_DATABASE_URL --target NEON_DATABASE_URL [--commit]

Both are names of owner-role URLs in the env file (commented lines like `# NAME=value` count).
Safety:
- both databases must be on the same migration revision (run scripts.setup_database on the
  target first), and the target must hold no data;
- everything is copied in ONE transaction: it either all arrives or nothing does;
- the source is only read;
- afterwards every table's row count and content fingerprint are compared.
Without --commit it only reports what it would copy.
"""

import argparse
import asyncio
import io
import re
import sys
from pathlib import Path

import asyncpg

BACKEND = Path(__file__).resolve().parents[1]
SKIP = {"alembic_version", "rate_limit_buckets"}  # schema bookkeeping; throwaway counters
ONLY = {"jobs": "status <> 'done'"}  # finished jobs are cleaned up after a day anyway


def _env_value(env_file: Path, name: str) -> str:
    text = env_file.read_text(encoding="utf-8")
    m = re.search(rf"(?m)^(?:#\s*)?{re.escape(name)}=(.+)$", text)
    if not m:
        sys.exit(f"{name} not found in {env_file}")
    return m.group(1).strip().strip('"').replace("postgresql+asyncpg://", "postgresql://", 1)


def _order() -> list[str]:
    """Tables parents-first, from the app's own model metadata."""
    sys.path.insert(0, str(BACKEND))
    from app.models import Base

    return [t.name for t in Base.metadata.sorted_tables if t.name not in SKIP]


async def _columns(conn, table: str) -> list[str]:
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = $1 "
        "ORDER BY ordinal_position",
        table,
    )
    return [r["column_name"] for r in rows]


def _fingerprint_sql(table: str, cols: list[str], where: str | None) -> str:
    """Order-independent hash of every row's text form."""
    row = "(" + ", ".join(f'"{c}"' for c in cols) + ")::text"
    return (
        f'SELECT count(*), coalesce(md5(string_agg(md5({row}), \'\' ORDER BY md5({row}))), \'\') FROM "{table}"'
        + (f" WHERE {where}" if where else "")
    )


async def main(source_name: str, target_name: str, env_file: Path, commit: bool) -> None:
    src = await asyncpg.connect(_env_value(env_file, source_name))
    dst = await asyncpg.connect(_env_value(env_file, target_name))
    try:
        v_src = await src.fetchval("SELECT version_num FROM alembic_version")
        v_dst = await dst.fetchval("SELECT version_num FROM alembic_version")
        if v_src != v_dst:
            sys.exit(f"Revisions differ (source {v_src}, target {v_dst}). Migrate both to the same version first.")

        tables = _order()
        for t in tables:
            if await dst.fetchval(f'SELECT EXISTS (SELECT 1 FROM "{t}")'):
                sys.exit(f"The target already has data in {t}. Refusing to copy over it.")

        plan = []
        for t in tables:
            cols = await _columns(src, t)
            where = ONLY.get(t)
            n = await src.fetchval(f'SELECT count(*) FROM "{t}"' + (f" WHERE {where}" if where else ""))
            plan.append((t, cols, where, n))
        total = sum(n for *_, n in plan)
        print(f"Revision {v_src}. {total} rows in {sum(1 for p in plan if p[3])} tables to copy:")
        for t, _, _, n in plan:
            if n:
                print(f"  {t:<28} {n}")
        if not commit:
            print("\nDry run. Re-run with --commit to copy.")
            return

        async with dst.transaction():
            for t, cols, where, n in plan:
                if not n:
                    continue
                buf = io.BytesIO()
                col_list = ", ".join(f'"{c}"' for c in cols)
                query = f'SELECT {col_list} FROM "{t}"' + (f" WHERE {where}" if where else "")
                await src.copy_from_query(query, output=buf, format="csv")
                buf.seek(0)
                await dst.copy_to_table(t, source=buf, columns=cols, format="csv")

        print("\nCopied. Verifying every table…")
        bad = []
        for t, cols, where, _ in plan:
            a = await src.fetchrow(_fingerprint_sql(t, cols, where))
            b = await dst.fetchrow(_fingerprint_sql(t, cols, None))
            if tuple(a) != tuple(b):
                bad.append((t, a[0], b[0]))
        if bad:
            sys.exit(f"MISMATCH in {bad}")
        print(f"All {len(plan)} tables match (row counts and content fingerprints).")
    finally:
        await src.close()
        await dst.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, help="Env var name of the source owner URL")
    parser.add_argument("--target", required=True, help="Env var name of the target owner URL")
    parser.add_argument("--env-file", type=Path, default=BACKEND.parent / ".env")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.source, args.target, args.env_file, args.commit))
