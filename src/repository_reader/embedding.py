"""Track 4 (production hardening, 2026-10-01): doi tu BGE-M3 CHAY LOCAL
(can GPU de nhanh) sang Gemini Embedding API.

Ly do doi: chuan bi deploy UI/API len production (Render) -- server deploy
se KHONG co GPU nhu may ca nhan, BGE-M3 chay CPU tren cloud se cham (da
xac nhan thuc te: ~12s/batch tren CHINH may co GPU nhung torch khong thay
CUDA). Dung API ngoai thi toc do khong con phu thuoc phan cung server nua.

Model "gemini-embedding-001" (KHONG dung "Gemini Embedding 2" -- da doc
doc chinh thuc truoc khi code, dung nguyen tac "Documentation First" da ap
dung cho Langfuse: model do GOP nhieu input thanh 1 embedding DUY NHAT,
sai muc dich vi can 1 vector RIENG cho moi chunk).

output_dimensionality=1024: EP ve dung 1024 chieu, KHOP CHINH XAC voi
VectorParams(size=1024) da khai trong vector_store.py -- nho vay KHONG
can doi gi o schema Qdrant. Luu y quan trong: vector BGE-M3 CU va vector
Gemini MOI la 2 THE GIOI khac nhau hoan toan (du cung 1024 chieu cung
KHONG so sanh duoc) -- repo da ingest TRUOC thay doi nay PHAI duoc ingest
LAI (dan lai dung URL cu, UUID5 se tu de dung chunk cu bang vector moi).
"""
import time

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from repository_reader.config import settings

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIM = 1024

# Gop nhieu chunk vao 1 request (nhanh hon, it request hon goi tung chunk
# 1) nhung van gioi han o muc an toan, tranh payload qua lon/de cham toi
# han rate limit kho doan truoc (free tier Gemini chua cong bo ro so nay).
_BATCH_SIZE = 32

_MAX_RETRIES = 10
_BASE_DELAY_SECONDS = 2  # 2s, 4s, 8s... giong het _generate_with_retry() trong agent.py

_client = genai.Client(api_key=settings.llm_api_key)


def _embed_batch_with_retry(batch: list[str], task_type: str):
    """Goi embed_content() cho 1 batch, retry+backoff CUNG PATTERN voi
    _generate_with_retry() trong agent.py -- embedding dung CHUNG quota
    Gemini voi LLM call, nen cung co the gap 429 (het quota/rate limit).
    ServerError (5xx) va ClientError 429 deu dang thu lai; cac ClientError
    4xx khac (sai key, sai ten model...) raise ngay vi retry khong giup gi.
    """
    last_error = None
    for attempt in range(_MAX_RETRIES):
        try:
            return _client.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=batch,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=EMBEDDING_DIM,
                ),
            )
        except genai_errors.ServerError as e:
            last_error = e
            time.sleep(_BASE_DELAY_SECONDS * (2 ** attempt))
        except genai_errors.ClientError as e:
            if e.code == 429:
                last_error = e
                time.sleep(_BASE_DELAY_SECONDS * (2 ** attempt))
            else:
                raise
    raise last_error


def embed_texts(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Tra ve list[list[float]] (1 vector/text, dung thu tu input).

    task_type khac nhau theo NGU CANH goi -- best-practice rieng cua
    Gemini Embedding cho retrieval (BGE-M3 cu khong phan biet 2 truong hop
    nay, dung chung 1 cach encode cho ca chunk va cau hoi):
    - "RETRIEVAL_DOCUMENT" (mac dinh): dung khi ingest chunk vao Qdrant
      (xem ingest.get_all_chunks() -> embed_texts()).
    - "RETRIEVAL_QUERY": dung khi embed cau hoi tim kiem cua nguoi dung
      (xem vector_store.search_semantic()).
    """
    if not texts:
        return []

    all_vectors: list[list[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        batch = texts[i : i + _BATCH_SIZE]
        response = _embed_batch_with_retry(batch, task_type)
        all_vectors.extend(e.values for e in response.embeddings)
    return all_vectors


if __name__ == "__main__":
    pass
