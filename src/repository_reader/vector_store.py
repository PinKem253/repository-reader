from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams, Distance, PointStruct, PayloadSchemaType,
    Filter, FieldCondition, MatchValue,
)
from repository_reader import embedding
import uuid

client = QdrantClient(url = "http://localhost:6333")

def create_collection():
    client.create_collection(
        collection_name="repo_chunks",
        vectors_config=VectorParams(size = 1024, distance=Distance.COSINE)
    )
    client.create_payload_index(
        collection_name="repo_chunks",
        field_name="repo_id",
        field_schema=PayloadSchemaType.INTEGER
    )

def upsert_chunks(all_chunks, dense_vecs, repo_id):
    points = [
        PointStruct(
            id=str(uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"{repo_id}:{all_chunks[i]['file']}:{all_chunks[i]['start_line']}",
            )),
            # Khong con ".tolist()" -- embedding.embed_texts() (2026-10-01,
            # doi sang Gemini Embedding API) tra ve thang list[list[float]],
            # khac ban cu (BGE-M3/FlagEmbedding tra numpy array can .tolist()).
            vector=dense_vecs[i],
            payload={
                "repo_id": repo_id,
                "file": all_chunks[i]["file"],
                "start_line": all_chunks[i]["start_line"],
                "end_line": all_chunks[i]["end_line"],
                "text": all_chunks[i]["text"],
            },
        )
        for i in range(len(all_chunks))
    ]
    client.upsert(collection_name="repo_chunks", points=points)

def search_semantic(query, repo_id: int, top_k: int = 5):
    # task_type="RETRIEVAL_QUERY" -- khac "RETRIEVAL_DOCUMENT" (mac dinh
    # cua embed_texts(), dung luc ingest chunk o tren) vi day la embed 1
    # CAU HOI tim kiem, khong phai 1 doan noi dung can luu tru -- best
    # practice rieng cua Gemini Embedding cho bai toan retrieval.
    embed_query = embedding.embed_texts([query], task_type="RETRIEVAL_QUERY")[0]
    repo_filter = Filter(
        must=[FieldCondition(key="repo_id", match=MatchValue(value=repo_id))]
    )
    search_result = client.query_points(
        collection_name="repo_chunks",
        query=embed_query,
        query_filter=repo_filter,
        limit=top_k,
    ).points
    return [
        {**point.payload, "score": point.score}
        for point in search_result
    ]
if __name__ == "__main__":
    #client.delete_collection("repo_chunks")
    #create_collection()
    pass 
