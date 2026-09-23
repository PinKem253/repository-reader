from google import genai
from repository_reader.config import settings

client = genai.Client(api_key=settings.llm_api_key)

def generate_answer(query, chunks):
    context = "\n\n".join(
        f"[{c['file']}:{c['start_line']}-{c['end_line']}]\n{c['text']}"
        for c in chunks
    )
    
    prompt = (
        f"Context:\n{context}\n\n"
        f"Question: {query}\n\n"
        "Answer only using the context above. Cite the file and line range for each claim."
    )
    
    response = client.models.generate_content(
        model="gemini-flash-latest",
        contents=prompt,
    )
    return response.text
    
    
if __name__ == "__main__":
    pass 
