from openai import OpenAI
from llama_index.readers.file import PDFReader
from llama_index.core.node_parser import SentenceSplitter
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

#we are going to chunk our pdffile to smaller pieces so that we can embed them into our vector database

client= OpenAI()
EMBED_MODEL = "text-embedding-3-large"  # Model used for generating embeddings
EMBEDDING_DIM = 3072  # Dimensionality of the embedding vectors produced by the model

splitter = SentenceSplitter(chunk_size= 1000, chunk_overlap=200)      # Initialize a sentence splitter for chunking text 

def load_and_chunk_pdf(file_path: str):
    # Load the PDF file and split it into smaller chunks
    docs= PDFReader().load_data(file= file_path)
    texts = [d.text for d in docs if getattr(d, "text", None)]  # Extract text from loaded documents
    chunks =  []
    for t in texts : 
        chunks.extend(splitter.split_text(t))  # Split each text into smaller chunks
    return chunks  # Return the list of text chunks

def embed_texts(texts : list[str])-> list[list[float]]:
    response = client.embeddings.create(
        model=EMBED_MODEL,
        input=texts
    )
    return [item.embedding for item in response.data]  # Extract and return the embedding vectors from the response