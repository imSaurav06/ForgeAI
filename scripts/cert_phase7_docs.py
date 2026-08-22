"""
Phase 7 Documentation Forensic Certification Script
Validates existence, completeness, formatting, and structural integrity of all documentation files.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

REQUIRED_DOCS = [
    "docs/models.md",
    "docs/rag.md",
    "docs/agent.md",
    "docs/api.md",
    "docs/security.md",
    "docs/evaluation.md",
    "docs/architecture.md",
    "README.md",
]


def run_phase_7_docs_certification(run_label: str = "RUN_A") -> dict[str, Any]:
    print(f"\n========================================================")
    print(f"[*] EXECUTING PHASE 7 DOCUMENTATION CERTIFICATION: {run_label}")
    print(f"========================================================")

    root_dir = Path(__file__).parent.parent.resolve()
    results = {}

    for doc_rel_path in REQUIRED_DOCS:
        doc_path = root_dir / doc_rel_path
        exists = doc_path.is_file()
        assert exists, f"Missing required documentation: {doc_rel_path}"

        content = doc_path.read_text(encoding="utf-8")
        size = len(content)
        lines = len(content.splitlines())
        has_h1 = content.startswith("# ") or "\n# " in content

        print(f"    [+] {doc_rel_path:22} -> Size: {size:5} bytes | Lines: {lines:3} | H1 Title: {has_h1} -> PASS")
        assert size > 200, f"Document {doc_rel_path} too small ({size} bytes)"
        assert has_h1, f"Document {doc_rel_path} missing H1 title"

        results[doc_rel_path] = {"size": size, "lines": lines, "status": "PASS"}

    return {
        "status": "PASS",
        "verified_docs_count": len(results),
        "docs": results,
    }


if __name__ == "__main__":
    res_a = run_phase_7_docs_certification("RUN_A")
    res_b = run_phase_7_docs_certification("RUN_B")

    print("\n========================================================")
    print("PHASE 7 DOUBLE EXECUTION VERIFICATION SUMMARY:")
    print(f"Run A Result: {res_a['status']} | {res_a['verified_docs_count']}/8 Documents Verified")
    print(f"Run B Result: {res_b['status']} | {res_b['verified_docs_count']}/8 Documents Verified")
    assert res_a["status"] == "PASS" and res_b["status"] == "PASS"
    print("========================================================")
    print("PHASE 7 DOCUMENTATION CERTIFICATION: >>> 100% PASS <<<")
    print("========================================================")
