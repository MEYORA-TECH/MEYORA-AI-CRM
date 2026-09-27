"""Grant or revoke platform admin (the whole installation, above workspaces).

    python -m scripts.platform_admin grant you@example.com
    python -m scripts.platform_admin revoke you@example.com
    python -m scripts.platform_admin list

Deliberately a server command, not an app screen: whoever can run it already controls
the server. The person must have signed up already.
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.database.session import SessionLocal, engine
from app.models import User


async def main(action: str, email: str | None) -> None:
    async with SessionLocal() as session:
        if action == "list":
            admins = (await session.scalars(select(User).where(User.is_platform_admin).order_by(User.email))).all()
            print("\n".join(f"{u.email} ({u.full_name})" for u in admins) or "No platform admins yet.")
        else:
            user = await session.scalar(select(User).where(func.lower(User.email) == (email or "").lower()))
            if user is None:
                sys.exit(f"No account with {email}. They need to sign up first.")
            user.is_platform_admin = action == "grant"
            await session.commit()
            print(f"{user.email} is {'now' if user.is_platform_admin else 'no longer'} a platform admin.")
    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["grant", "revoke", "list"])
    parser.add_argument("email", nargs="?")
    args = parser.parse_args()
    if args.action != "list" and not args.email:
        parser.error("an email is required")
    asyncio.run(main(args.action, args.email))
