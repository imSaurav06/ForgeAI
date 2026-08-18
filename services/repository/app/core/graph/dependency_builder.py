from collections import defaultdict
from typing import Any


class DependencyGraphBuilder:
    """
    Dependency Graph Analyzer building static dependency relationships across scanned source files.
    Identifies internal module links, external packages, circular dependencies, and orphan files.
    """

    def __init__(self, scanned_files: list[dict[str, Any]], symbols: list[dict[str, Any]]) -> None:
        self.scanned_files = scanned_files
        self.file_paths = {f["path"] for f in scanned_files}
        self.symbols = symbols

    def build_graph(self) -> dict[str, Any]:
        """Construct full dependency graph structure."""
        nodes: list[str] = sorted(self.file_paths)
        internal_edges: list[dict[str, str]] = []
        external_packages: set[str] = set()

        # Build adjacency maps for cycle and orphan detection
        adjacency: dict[str, set[str]] = defaultdict(set)
        in_degree: dict[str, int] = defaultdict(int)

        # Index imports by file
        file_imports = defaultdict(list)
        for s in self.symbols:
            if s.get("type") == "import":
                file_imports[s["file"]].append(s["symbol"])

        for file_path in self.file_paths:
            imports = file_imports.get(file_path, [])
            for imp in imports:
                target_file = self._resolve_internal_import(file_path, imp)
                if target_file and target_file in self.file_paths:
                    if target_file != file_path:
                        internal_edges.append({"source": file_path, "target": target_file})
                        adjacency[file_path].add(target_file)
                        in_degree[target_file] += 1
                else:
                    top_pkg = imp.split(".")[0].split("/")[0].strip("@")
                    if top_pkg and not top_pkg.startswith("."):
                        external_packages.add(top_pkg)

        # Detect Circular Dependencies
        circular_dependencies = self._find_circular_dependencies(adjacency)

        # Detect Orphan Files
        referenced_files = {e["target"] for e in internal_edges} | {e["source"] for e in internal_edges}
        orphan_files = [f for f in nodes if f not in referenced_files]

        return {
            "nodes": nodes,
            "internal_edges": internal_edges,
            "external_packages": sorted(external_packages),
            "circular_dependencies": circular_dependencies,
            "orphan_files": orphan_files,
        }

    def _resolve_internal_import(self, current_file: str, import_name: str) -> str | None:
        """Resolve python/js import string to relative repository file path."""
        clean_imp = import_name.replace(".", "/")

        # Match exact file path candidates
        candidates = [
            f"{clean_imp}.py",
            f"{clean_imp}/__init__.py",
            f"{clean_imp}.js",
            f"{clean_imp}.ts",
            f"{clean_imp}.tsx",
            f"{clean_imp}/index.js",
            f"{clean_imp}/index.ts",
        ]

        for cand in candidates:
            if cand in self.file_paths:
                return cand

        # Partial module path matching
        for f in self.file_paths:
            if f.endswith(f"/{clean_imp}.py") or f.endswith(f"/{clean_imp}.ts") or f.endswith(f"/{clean_imp}.js"):
                return f

        return None

    def _find_circular_dependencies(self, adjacency: dict[str, set[str]]) -> list[list[str]]:
        """Find simple cycles in module dependency adjacency graph using DFS."""
        cycles: list[list[str]] = []
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in adjacency.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    if cycle not in cycles and len(cycle) > 2:
                        cycles.append(cycle)

            path.pop()
            rec_stack.remove(node)

        for node in sorted(adjacency.keys()):
            if node not in visited:
                dfs(node)

        return cycles
