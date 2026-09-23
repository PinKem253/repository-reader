from FlagEmbedding import BGEM3FlagModel

_model = None

def get_model():
    global _model 
    if _model is None: 
        _model = BGEM3FlagModel("BAAI/bge-m3", use_bf16=True) 
    return _model

def embed_texts(texts: list[str]):
    model = get_model()
    output = model.encode(texts, batch_size=12, max_length=512)
    return output["dense_vecs"]

if __name__ == "__main__":
    pass 