"""Queue indexing for every existing record: `python -m app.ai.backfill`.

Needed once for data created before the knowledge index existed; the job
worker then embeds it in the background.
"""

import asyncio

from sqlalchemy import select

from app.ai.knowledge import INDEXED
from app.database.session import SessionLocal, set_tenant
from app.jobs.queue import enqueue
from app.models import Organization


async def main() -> None:
    async with SessionLocal() as session:
        orgs = list(await session.scalars(select(Organization.id)))
    total = 0
    for org_id in orgs:
        async with SessionLocal() as session:
            await set_tenant(session, org_id)
            for kind, model in INDEXED.items():
                for record_id in await session.scalars(select(model.id).where(model.organization_id == org_id)):
                    await enqueue(
                        session,
                        "index_record",
                        org_id,
                        {"kind": kind, "id": str(record_id)},
                        dedupe_key=f"{kind}:{record_id}",
                    )
                    total += 1
            await session.commit()
    print(f"Queued {total} records across {len(orgs)} organization(s).")


if __name__ == "__main__":
    asyncio.run(main())
