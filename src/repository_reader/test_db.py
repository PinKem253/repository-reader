import asyncio
from repository_reader.ingest import ingest_repo

async def main():
    # repo 1: psf/requests — đã biết rõ nội dung để tự verify
   # repo_id_1 = await ingest_repo("https://github.com/psf/requests")
    #print("repo 1 ->", repo_id_1)

    # repo 2: chọn 1 repo rất nhỏ (README gần như trống) để test nhanh,
    # không cần nội dung phong phú — chỉ cần khác hẳn nội dung repo 1
    repo_id_2 = await ingest_repo("https://github.com/octocat/Spoon-Knife")
    print("repo 2 ->", repo_id_2)

asyncio.run(main())