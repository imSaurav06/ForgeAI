from typing import Any


class ContextBuilder:
    """
    Context Builder constructing optimized repository prompt context
    using retrieved code snippets, symbols, imports, and dependencies
    while enforcing strict token budgeting limits.
    """

    # Approximate token estimator (1 token ~= 4 chars)
    CHAR_PER_TOKEN: float = 4.0

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """Estimate token count for string text."""
        return int(len(text) / cls.CHAR_PER_TOKEN) + 1

    @classmethod
    def build_context(
        cls,
        retrieved_snippets: list[dict[str, Any]],
        max_token_budget: int = 4096,
        include_imports: bool = True,
        include_dependencies: bool = True,
    ) -> dict[str, Any]:
        """
        Assemble structured context string from retrieved snippets while strictly
        enforcing max_token_budget.
        """
        context_blocks: list[str] = []
        total_tokens = 0
        used_snippets: list[dict[str, Any]] = []

        # System header block
        header = "=== RETRIEVED REPOSITORY CONTEXT ===\n"
        total_tokens += cls.estimate_tokens(header)

        for snippet_item in retrieved_snippets:
            file_path = snippet_item.get("file_path", "unknown")
            start_line = snippet_item.get("start_line", 1)
            end_line = snippet_item.get("end_line", 1)
            symbol = snippet_item.get("symbol", "")
            code_text = snippet_item.get("snippet", "")

            block_str = (
                f"--- File: {file_path} (Lines {start_line}-{end_line}) "
                f"{'Symbol: ' + symbol if symbol else ''} ---\n"
                f"{code_text}\n\n"
            )
            block_tokens = cls.estimate_tokens(block_str)

            if total_tokens + block_tokens > max_token_budget:
                # Truncate snippet if room permits
                remaining_tokens = max_token_budget - total_tokens
                if remaining_tokens > 50:
                    remaining_chars = int(remaining_tokens * cls.CHAR_PER_TOKEN)
                    truncated_code = code_text[:remaining_chars] + "\n... [Truncated due to token budget]"
                    block_str = f"--- File: {file_path} (Lines {start_line}-{end_line}) ---\n{truncated_code}\n\n"
                    context_blocks.append(block_str)
                    total_tokens += cls.estimate_tokens(block_str)
                    used_snippets.append(snippet_item)
                break

            context_blocks.append(block_str)
            total_tokens += block_tokens
            used_snippets.append(snippet_item)

        final_context_text = header + "".join(context_blocks)

        return {
            "context_text": final_context_text.strip(),
            "total_tokens_used": total_tokens,
            "max_token_budget": max_token_budget,
            "snippet_count": len(used_snippets),
            "snippets": used_snippets,
        }
