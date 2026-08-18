"""
Phase 2 RAG Forensic Certification Script
Strict double verification with Qdrant collection validation, multi-repo isolation, and token budget testing.
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.resolve()))

from services.retrieval.app.context.context_builder import ContextBuilder
from services.retrieval.app.embeddings.vector_encoder import get_code_vector_encoder
from services.retrieval.app.qdrant.qdrant_client import get_qdrant_client
from services.retrieval.app.search.pipeline import RAGSearchPipeline


def run_phase_2_rag_certification(run_label: str = "RUN_A") -> dict[str, Any]:
    print(f"\n========================================================")
    print(f"[*] EXECUTING PHASE 2 RAG FORENSIC CERTIFICATION: {run_label}")
    print(f"========================================================")

    qdrant = get_qdrant_client()
    encoder = get_code_vector_encoder()
    pipeline = RAGSearchPipeline()

    # 1. Collection Architecture Verification
    coll_name = "forge_ai_code"
    try:
        qdrant.ensure_collection_exists()
        coll_info = qdrant.client.get_collection(coll_name)
        dim = coll_info.config.params.vectors.size
        dist = str(coll_info.config.params.vectors.distance)
        print(f"[+] Qdrant Collection '{coll_name}' verified:")
        print(f"    - Vector Dimension: {dim} (Expected: 384)")
        print(f"    - Distance Metric: {dist} (Expected: Cosine)")
        assert dim == 384, f"Dimension mismatch: {dim} != 384"
    except Exception as e:
        print(f"[!] Collection verification error: {e}")
        raise

    # 2. Multi-Repository Isolation Setup
    repo_alpha_id = f"repo_alpha_{uuid.uuid4().hex[:8]}"
    repo_beta_id = f"repo_beta_{uuid.uuid4().hex[:8]}"

    alpha_points = [
        {
            "file_path": "services/alpha_core.py",
            "language": "python",
            "symbol": "alpha_compute_engine",
            "symbol_type": "class",
            "start_line": 10,
            "end_line": 45,
            "chunk_hash": "sha256_alpha_112233",
            "git_commit": "c0ffee11",
            "snippet": "class alpha_compute_engine:\n    def execute_heavy_computation(self, matrix):\n        return matrix * 42",
        },
        {
            "file_path": "services/alpha_utils.py",
            "language": "python",
            "symbol": "alpha_normalizer",
            "symbol_type": "function",
            "start_line": 5,
            "end_line": 15,
            "chunk_hash": "sha256_alpha_445566",
            "git_commit": "c0ffee11",
            "snippet": "def alpha_normalizer(data):\n    return [d / 100.0 for d in data]",
        },
    ]

    beta_points = [
        {
            "file_path": "security/beta_vault.py",
            "language": "python",
            "symbol": "beta_encryption_vault",
            "symbol_type": "class",
            "start_line": 20,
            "end_line": 60,
            "chunk_hash": "sha256_beta_778899",
            "git_commit": "deadbeef",
            "snippet": "class beta_encryption_vault:\n    def encrypt_secret(self, raw_data):\n        return b'ENC_' + raw_data",
        },
        {
            "file_path": "security/beta_auth.py",
            "language": "python",
            "symbol": "beta_token_validator",
            "symbol_type": "function",
            "start_line": 8,
            "end_line": 25,
            "chunk_hash": "sha256_beta_aabbcc",
            "git_commit": "deadbeef",
            "snippet": "def beta_token_validator(token_str):\n    return token_str.startswith('bearer_')",
        },
    ]

    # Encode embeddings
    alpha_vecs = encoder.encode_batch([p["snippet"] for p in alpha_points])
    for p, v in zip(alpha_points, alpha_vecs):
        p["embedding"] = v

    beta_vecs = encoder.encode_batch([p["snippet"] for p in beta_points])
    for p, v in zip(beta_points, beta_vecs):
        p["embedding"] = v

    # Upsert into Qdrant
    upserted_alpha = qdrant.upsert_points(repo_alpha_id, alpha_points)
    upserted_beta = qdrant.upsert_points(repo_beta_id, beta_points)
    print(f"[+] Upserted {upserted_alpha} points for {repo_alpha_id}")
    print(f"[+] Upserted {upserted_beta} points for {repo_beta_id}")

    # 3. Payload & Metadata Completeness Verification
    alpha_sample = qdrant.search(query_vector=alpha_vecs[0], repository_id=repo_alpha_id, limit=1)
    assert len(alpha_sample) > 0, "Failed to retrieve upserted alpha point"
    meta = alpha_sample[0]
    print(f"[+] Point Metadata Verification:")
    print(f"    - repository_id: {meta.get('repository_id')}")
    print(f"    - symbol: {meta.get('symbol')}")
    print(f"    - symbol_type: {meta.get('symbol_type')}")
    print(f"    - start_line: {meta.get('start_line')}")
    print(f"    - end_line: {meta.get('end_line')}")
    print(f"    - chunk_hash: {meta.get('chunk_hash')}")
    assert meta.get("symbol") == "alpha_compute_engine", "Symbol mismatch"
    assert meta.get("start_line") == 10, "start_line mismatch"
    assert meta.get("chunk_hash") == "sha256_alpha_112233", "chunk_hash mismatch"

    # 4. Multi-Repository Cross-Contamination Test
    print("[*] Testing Multi-Repository Strict Isolation...")
    # Query for Alpha code within Beta repo
    cross_search_beta = qdrant.search(query_vector=alpha_vecs[0], repository_id=repo_beta_id, limit=10)
    for hit in cross_search_beta:
        assert "alpha" not in hit.get("symbol", "").lower(), f"Cross-contamination detected in Beta: {hit}"
    print(f"    - Cross-contamination Alpha in Beta: 0 matches (CLEAN)")

    # Query for Beta code within Alpha repo
    cross_search_alpha = qdrant.search(query_vector=beta_vecs[0], repository_id=repo_alpha_id, limit=10)
    for hit in cross_search_alpha:
        assert "beta" not in hit.get("symbol", "").lower(), f"Cross-contamination detected in Alpha: {hit}"
    print(f"    - Cross-contamination Beta in Alpha: 0 matches (CLEAN)")

    # 5. Hybrid Search & RRF Reranking Test
    hybrid_results = pipeline.execute_hybrid_search(
        query="heavy matrix computation",
        repository_id=repo_alpha_id,
        indexed_points=[{"path": "services/alpha_core.py", "language": "python"}],
        symbols_index=[{"file": "services/alpha_core.py", "symbol": "alpha_compute_engine", "type": "class"}],
        dependency_graph={"internal_edges": [], "external_packages": []},
        limit=5,
    )
    print(f"[+] Hybrid RAG Search returned {len(hybrid_results)} ranked results:")
    for idx, r in enumerate(hybrid_results, 1):
        print(f"    {idx}. [{r.get('symbol')}] (score: {r.get('score'):.4f}) in {r.get('file_path')}")
    assert len(hybrid_results) > 0
    assert hybrid_results[0].get("symbol") == "alpha_compute_engine"

    # 6. Token Budget Truncation Test
    tight_budget = ContextBuilder.build_context(
        retrieved_snippets=hybrid_results,
        max_token_budget=50,
    )
    generous_budget = ContextBuilder.build_context(
        retrieved_snippets=hybrid_results,
        max_token_budget=2000,
    )
    print(f"[+] Token Budget Control:")
    print(f"    - Tight Budget Context Length (chars): {len(tight_budget['context_text'])} (estimated tokens: {tight_budget['total_tokens_used']})")
    print(f"    - Generous Budget Context Length (chars): {len(generous_budget['context_text'])} (estimated tokens: {generous_budget['total_tokens_used']})")
    assert tight_budget["total_tokens_used"] <= 60, f"Tight budget exceeded: {tight_budget['total_tokens_used']}"
    assert generous_budget["total_tokens_used"] <= 2000

    # Cleanup
    qdrant.clear_repository_points(repo_alpha_id)
    qdrant.clear_repository_points(repo_beta_id)
    print(f"[+] Cleaned up test repositories: {repo_alpha_id}, {repo_beta_id}")

    return {
        "status": "PASS",
        "collection": coll_name,
        "dimension": dim,
        "distance": dist,
        "isolation_verified": True,
        "cross_contamination_count": 0,
        "token_budget_verified": True,
        "top_ranked_symbol": hybrid_results[0].get("symbol"),
    }


if __name__ == "__main__":
    # Double Run Protocol: Run A + Run B
    res_a = run_phase_2_rag_certification("RUN_A")
    res_b = run_phase_2_rag_certification("RUN_B")

    print("\n========================================================")
    print("PHASE 2 DOUBLE EXECUTION VERIFICATION SUMMARY:")
    print(f"Run A Result: {res_a['status']} | Top Symbol: {res_a['top_ranked_symbol']}")
    print(f"Run B Result: {res_b['status']} | Top Symbol: {res_b['top_ranked_symbol']}")
    assert res_a["status"] == "PASS" and res_b["status"] == "PASS"
    print("========================================================")
    print("PHASE 2 RAG CERTIFICATION: >>> 100% PASS <<<")
    print("========================================================")
