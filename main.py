import logging                      # Standard logging module to record app events and errors
from fastapi import FastAPI          # FastAPI framework to build the web API
import inngest                       # Inngest SDK to define and run event-driven background functions
import inngest.fast_api              # Inngest integration that mounts Inngest functions onto a FastAPI app
from dotenv import load_dotenv       # Loads environment variables from a .env file
import uuid                          # Generates unique identifiers (e.g. for IDs or event keys)
import os                            # Access to environment variables and OS-level utilities
import datetime                      # Date and time handling (timestamps, durations, etc.)
from inngest.experimental import ai  # Experimental Inngest AI helpers (e.g. calling LLMs inside steps)
from data_loader import load_and_chunk_pdf, embed_texts  # Custom functions to load and embed PDF text chunks
from vector_db import QdrantStorage  # Custom wrapper around Qdrant vector database for storing and searching embeddings
from custom_types import RAGChunkAndSrc, RAGUpsertResult, RAGSearchResult, RAGQueryResult  # Custom Pydantic models for structured data handling

load_dotenv()  # Load environment variables from .env file

# Create an Inngest client to define and run event-driven functions
inngest_client = inngest.Inngest(
    app_id="rag_app",
    logger=logging.getLogger("uvicorn"),
    is_production=False,
    serializer= inngest.PydanticSerializer()
)

@inngest_client.create_function(
    fn_id="RAG : Ingest PDF",
    trigger=inngest.TriggerEvent(event="rag/ingest_pdf")
)


async def rag_ingest_pdf(ctx: inngest.Context) : 
    
    def _load(ctx: inngest.Context) -> RAGChunkAndSrc:
        pdf_path = ctx.event.data["pdf_path"]  # Extract the PDF file path from the event data
        source_id = ctx.event.data.get("source_id", pdf_path)  # Use provided source_id or use the PDF path
        chunks = load_and_chunk_pdf(pdf_path)  # Load and chunk the PDF into smaller text pieces
        return RAGChunkAndSrc(chunk=chunks, source_id=source_id)  # Return a structured object with chunks and source ID
    
    def _upsert(chunks_and_src: RAGChunkAndSrc) -> RAGUpsertResult:
        
        chunks = chunks_and_src.chunk  # Extract the text chunks
        source_id = chunks_and_src.source_id  # Extract the source ID
        vecs = embed_texts(chunks)  # Generate embeddings for the text chunks
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source_id}_{i}")) for i in range(len(chunks))]  # Generate unique IDs for each chunk
        payloads = [{"source": source_id, "text": chunks[i]} for i in range(len(chunks))]  # Create payloads with source and text
        QdrantStorage().upsert(ids, vecs, payloads)     # Upsert the embeddings and payloads into the Qdrant vector database
        return RAGUpsertResult(ingested=len(chunks))  # Return the number of chunks successfully ingested
    
    
    chunks_and_src = await ctx.step.run("load-and-chunk", lambda : _load(ctx), output_type=RAGChunkAndSrc)
    ingested = await ctx.step.run("embed-and-upsert", lambda : _upsert(chunks_and_src), output_type=RAGUpsertResult)
    return ingested.model_dump()

@inngest_client.create_function(
    fn_id="RAG : Query PDF",
    trigger=inngest.TriggerEvent(event="rag/query_pdf_ai")
)
async def rag_query_pdf_ai(ctx: inngest.Context):
    def _search(question: str, top_k: int = 5):
        query_vec = embed_texts([question])[0]  # Generate embedding for the query question
        store = QdrantStorage()  # Initialize the Qdrant storage
        found = store.search(query_vec, top_k=top_k)  # Search for the top_k most similar chunks in the vector database
        return RAGSearchResult(contexts=found["contexts"], sources = found["sources"])    # Return the search results as a structured object    
    
    question = ctx.event.data["question"]  # Extract the question from the event data
    top_k = int(ctx.event.data.get("top_k", 5))
    
    found = await ctx.step.run("embed-and-search", lambda : _search(question, top_k), output_type=RAGSearchResult)
    
    context_block = "\n \n".join(f"- {c}" for c in found.contexts)  # Format the found contexts into a single string block
    user_content = (
        "Use the following context to answer the question.\n \n"
        f"Context:\n{context_block}\n \n"
        f"Question:\n{question}\n \n"
        "Answer concisely, synthesizing the relevant information from the context, "
        "even if it is not phrased exactly like the question. "
        "Only say the answer is not in the context if no part of it is relevant."
    )
    
    adapter = ai.openai.Adapter(
        auth_key=os.getenv("OPENAI_API_KEY"),
        model="gpt-4o-mini",
    )
    
    res = await ctx.step.ai.infer(
        "llm-answer",
        adapter = adapter,
        body ={
            "max_tokens" : 1024,
            "temperature" : 0.2,
            "messages": [
                {"role": "system", "content": "You answer the questions using only the provided context."},
                {"role": "user", "content": user_content}
            ],
        },
    )
    
    answer = res["choices"][0]["message"]["content"].strip()# Extract the answer from the LLM response
    
    return {"answer": answer, "sources": found.sources, "num_contexts": len(found.contexts)}  # Return the answer and the sources used


app = FastAPI()  # Create a FastAPI app instance


inngest.fast_api.serve(app, inngest_client, [rag_ingest_pdf, rag_query_pdf_ai])