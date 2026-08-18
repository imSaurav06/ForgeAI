from typing import Any


class CodeRRFReranker:
    """
    Reciprocal Rank Fusion (RRF) and Multi-Signal Reranker for Code Search.
    Combines vector similarity, AST symbol matches, keyword hits, and dependency proximity.
    """

    @classmethod
    def rerank(
        cls,
        vector_results: list[dict[str, Any]],
        symbol_results: list[dict[str, Any]],
        keyword_results: list[dict[str, Any]],
        top_k: int = 10,
        rrf_k: int = 60,
    ) -> list[dict[str, Any]]:
        """
        Rerank multi-source search results using Reciprocal Rank Fusion (RRF).
        RRF Score = sum( 1.0 / (k + rank_i) ) for each result list.
        """
        scores: dict[str, float] = {}
        items_map: dict[str, dict[str, Any]] = {}

        def get_item_key(item: dict[str, Any]) -> str:
            return f"{item.get('file_path')}:{item.get('start_line')}:{item.get('symbol')}"

        def process_list(results: list[dict[str, Any]], weight: float = 1.0):
            for rank, item in enumerate(results, start=1):
                key = get_item_key(item)
                if key not in items_map:
                    items_map[key] = item
                rrf_score = weight * (1.0 / (rrf_k + rank))
                scores[key] = scores.get(key, 0.0) + rrf_score

        # Apply higher weight to symbol and vector matches
        process_list(vector_results, weight=1.2)
        process_list(symbol_results, weight=1.5)
        process_list(keyword_results, weight=0.8)

        # Sort by RRF score descending
        sorted_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)

        final_results: list[dict[str, Any]] = []
        for key in sorted_keys[:top_k]:
            item = dict(items_map[key])
            item["rrf_score"] = round(scores[key], 6)
            final_results.append(item)

        return final_results
