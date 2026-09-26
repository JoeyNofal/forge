"""
Shared local-embeddings client for agent memory (a ChromaDB embedding
function), extracted from CIPHER's memory module so every agent's
memory uses the exact same embedding logic instead of N duplicate
copies (Lesson #9 — merged now, while it's still just 2 files, rather
than after it's spread across all 9 agents).

Embeddings run through Ollama (already installed/used for local chat
models) instead of ChromaDB's default — keeps memory fully under the
one local runtime, no separate model-download mechanism (Decision,
CIPHER Session 4: option 2 — local-first over convenience).
"""
import os
import requests
from chromadb import Documents, EmbeddingFunction, Embeddings

OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embeddings")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Memory items are meant to be short, standalone facts — this also
# protects against nomic-embed-text's context limit, which a raw
# ~50,000-char save blew straight past (found in L5 testing, CIPHER
# Session 4: Ollama returned a 500 rather than a usable error).
MAX_MEMORY_CONTENT_CHARS = 2000


class OllamaEmbeddingFunction(EmbeddingFunction):
    """Embeds text via a local Ollama server. Requires `ollama pull nomic-embed-text` once."""

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = []
        for text in input:
            try:
                response = requests.post(
                    OLLAMA_EMBED_URL,
                    json={"model": OLLAMA_EMBED_MODEL, "prompt": text},
                    timeout=30,
                )
                response.raise_for_status()
            except requests.exceptions.ConnectionError as e:
                raise RuntimeError(
                    "This agent's memory needs Ollama running locally to create embeddings "
                    f"(tried {OLLAMA_EMBED_URL}). Start Ollama and make sure "
                    f"`ollama pull {OLLAMA_EMBED_MODEL}` has been run."
                ) from e
            except requests.exceptions.HTTPError as e:
                raise RuntimeError(
                    f"Ollama rejected an embedding request ({e}). This usually means "
                    f"the content was too long — keep memory content under "
                    f"{MAX_MEMORY_CONTENT_CHARS} characters."
                ) from e
            embeddings.append(response.json()["embedding"])
        return embeddings