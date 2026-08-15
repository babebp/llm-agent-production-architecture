"""Ingest markdown docs into Qdrant.

Run inside the mcp container (it already has the deps and the corpus mount):

    docker compose exec mcp python ingest.py

Embeddings are computed locally via fastembed (see ADR-0005) — the client
embeds `models.Document` payloads on upsert, no API key needed.
Re-running is idempotent: the collection is rebuilt from scratch.
"""

import glob
import os

from qdrant_client import QdrantClient, models

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION = os.environ.get("COLLECTION", "docs")
CORPUS_DIR = os.environ.get("CORPUS_DIR", "/corpus")
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBED_DIM = 384  # bge-small-en-v1.5 output size
CHUNK_SIZE = 1500


def chunk(text: str, size: int = CHUNK_SIZE) -> list[str]:
    # ponytail: paragraph-greedy chunking; move to semantic chunking if retrieval quality matters
    parts, buf = [], ""
    for para in text.split("\n\n"):
        if buf and len(buf) + len(para) > size:
            parts.append(buf.strip())
            buf = ""
        buf += para + "\n\n"
    if buf.strip():
        parts.append(buf.strip())
    return parts


def main() -> None:
    client = QdrantClient(url=QDRANT_URL)

    points = []
    for path in sorted(glob.glob(f"{CORPUS_DIR}/**/*.md", recursive=True)):
        source = os.path.relpath(path, CORPUS_DIR)
        with open(path) as f:
            for c in chunk(f.read()):
                points.append(
                    models.PointStruct(
                        id=len(points),
                        vector=models.Document(text=c, model=EMBED_MODEL),
                        payload={"text": c, "source": source},
                    )
                )

    if not points:
        raise SystemExit(f"no markdown files found under {CORPUS_DIR}")

    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=models.VectorParams(size=EMBED_DIM, distance=models.Distance.COSINE),
    )

    client.upsert(collection_name=COLLECTION, points=points)
    sources = {p.payload["source"] for p in points}
    print(f"ingested {len(points)} chunks from {len(sources)} files")


if __name__ == "__main__":
    main()
