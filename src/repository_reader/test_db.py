import asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from repository_reader.db import engine
from repository_reader.models import Repo

async def main():
    async with AsyncSession(engine) as session:
        result = await session.exec(select(Repo))
        repos = result.all()
        print(repos)

asyncio.run(main())