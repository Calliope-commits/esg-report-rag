from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

# Wrapper around a Qdrant collection used to store and search document embeddings
class QdrantStorage:
    def __init__(self, url="http://localhost:6333", collection="docs", dim=3072):
        # Connect to the Qdrant server running in Docker
        self.client = QdrantClient(url=url, timeout=30)
        self.collection = collection

        # Create the collection on first use; dim must match the embedding model's vector size
        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            
    def upsert(self, ids, vectors, payloads):
        points = [PointStruct(id = ids[i], vector = vectors[i], payload=payloads[i]) for i in range(len(ids))]
        self.client.upsert(self.collection, points)
        
    
    def search(self, query_vector, top_k: int=5):
        results = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            with_payload=True,
            limit=top_k
        ).points
        contexts = []
        sources = set() #to not add the same sources multiple times
        
        for r in results: 
            payload = getattr(r, "payload", None) or {}
            text = payload.get("text", "")
            source = payload.get("source", "")
            if text:
                contexts.append(text)
                sources.add(source)
            
        return {"contexts": contexts, "sources": list(sources)}