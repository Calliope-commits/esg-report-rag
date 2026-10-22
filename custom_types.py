import pydantic


class RAGChunkAndSrc(pydantic.BaseModel):
    """
    Represents a chunk of text and its associated source information for RAG (Retrieval-Augmented Generation) tasks.
    """
    chunk: list[str]  # The text chunk
    source_id: str  = None  # The source of the text chunk (e.g., document name, URL, etc.)
    
    
class RAGUpsertResult(pydantic.BaseModel):
    """
    Represents the result of an upsert operation into a vector database for RAG tasks.
    """
    ingested: int  # The number of items successfully upserted into the database
    
class RAGSearchResult(pydantic.BaseModel):
    """
    Represents the result of a search operation in a vector database for RAG tasks.
    """
    contexts: list[str]  # The retrieved text chunks that match the search query
    sources: list[str]   # The sources of the retrieved text chunks
    

class RAGQueryResult(pydantic.BaseModel):
    """
    Represents the result of a RAG query operation, including the answer and the sources of the information.
    """
    answer: str  # The generated answer based on the retrieved contexts
    sources: list[str]  # The sources of the information used to generate the answer
    num_contexts: int  # The number of contexts retrieved and used to generate the answer