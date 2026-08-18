# ForgeAI — Retrieval-Augmented Generation (RAG) Architecture

## Overview
The **Retrieval Service** (`forge_retrieval`, port `8004`) implements a high-precision, hybrid Code RAG engine. It indexes source code files, AST symbols, and static dependency relationships into **Qdrant Vector Database** (`forge_qdrant`, port `6333`), allowing multi-signal semantic search, lexical matching, and token-bounded context construction.

---

## 1. Vector Database Schema & Embedding Pipeline

- **Collection**: `forge_ai_code`
- **Vector Dimension**: `384` (Dense float32 vectors)
- **Distance Metric**: `Cosine`
- **Embedding Model**: `BAAI/bge-small-en-v1.5` / `sentence-transformers/all-MiniLM-L6-v2`
- **Payload Schema**:
  ```json
  {
    "repository_id": "repo_auth_svc_123",
    "file_path": "services/auth/jwt_manager.py",
    "language": "python",
    "symbol": "JWTManager.verify_token",
    "symbol_type": "method",
    "start_line": 45,
    "end_line": 80,
    "chunk_hash": "sha256_9a4f...",
    "git_commit": "c0ffee11",
    "snippet": "def verify_token(self, token: str) -> dict: ...",
    "dependency_metadata": {
      "imports": ["jwt", "cryptography", "time"],
      "calls": ["decode_jwt"]
    }
  }
  ```

---

## 2. Multi-Signal Hybrid Search & Reciprocal Rank Fusion (RRF)

The search pipeline combines four independent signal retrieval streams:
1. **Semantic Vector Search**: Cosine similarity against 384-dimensional dense embeddings in Qdrant.
2. **AST Symbol Matching**: Exact and fuzzy identifier lookups across classes, methods, and functions.
3. **Keyword / Regex Search**: Literal text matching across source files.
4. **Dependency Graph Traversal**: Upstream callers and downstream imported modules.

### RRF Reranking Formula:
$$RRF(d) = \sum_{m \in M} \frac{w_m}{k + r_m(d)}$$
Where $k = 60$, $w_m$ is the signal weight (Semantic: 1.0, Symbol: 1.2, Keyword: 0.8, Dependency: 0.6), and $r_m(d)$ is the rank in signal $m$.

---

## 3. Strict Multi-Repository Isolation

ForgeAI enforces strict vector isolation:
- All Qdrant queries include a hard filter on `repository_id`.
- Vector points are segregated; querying Repository A will never return points from Repository B (0 cross-contamination).
- Deleting a repository automatically purges its vector points from the collection.

---

## 4. Context Window & Token Budget Management

- The `ContextBuilder` dynamically formats retrieved code snippets into structured markdown context blocks.
- **Strict Budget Guarantee**: When a token budget (e.g., 4096 tokens) is specified, snippets are prioritized by RRF score and truncated safely at logical line boundaries, ensuring the LLM context limit is never exceeded.
