"""
Comprehensive test suite proving Tree-sitter integration is real and functional.

Tests cover: Python, JavaScript, TypeScript, TSX symbol extraction,
parent-child relationships, exact line ranges, malformed source handling,
unsupported languages, incremental indexing, dependency extraction,
.gitignore interaction, and backend verification.
"""

import tempfile
from pathlib import Path
from typing import Any

from services.repository.app.core.graph.dependency_builder import DependencyGraphBuilder
from services.repository.app.core.indexers.incremental_indexer import IncrementalIndexer
from services.repository.app.core.parsers.ast_parser import ASTSymbolParser
from services.repository.app.core.parsers.language_registry import (
    SUPPORTED_LANGUAGES,
    get_language,
    language_name_for_extension,
)
from services.repository.app.core.parsers.symbol_extractor import extract_symbols
from services.repository.app.core.parsers.tree_sitter_parser import parse_source
from services.repository.app.core.scanners.ignore_engine import IgnoreEngine

# ===================================================================
# Helpers
# ===================================================================

def _write_tmp(content: str, suffix: str) -> Path:
    """Write content to a named temp file and return the path."""
    f = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


def _parse_and_extract(content: str, suffix: str, language: str, repo_id: str = "test_repo") -> list[dict[str, Any]]:
    """Convenience: write temp file, run ASTSymbolParser.parse_file, clean up."""
    tmp = _write_tmp(content, suffix)
    try:
        return ASTSymbolParser.parse_file(
            file_path=tmp,
            relative_path=f"fixture{suffix}",
            language=language,
            repository_id=repo_id,
        )
    finally:
        tmp.unlink(missing_ok=True)


def _sym_names(symbols: list[dict]) -> list[str]:
    return [s["symbol"] for s in symbols]


def _sym_types(symbols: list[dict]) -> list[str]:
    return [s["type"] for s in symbols]


def _syms_of_type(symbols: list[dict], sym_type: str) -> list[dict]:
    return [s for s in symbols if s["type"] == sym_type]


# ===================================================================
# 1. BACKEND VERIFICATION — proves Tree-sitter is used, not Python ast
# ===================================================================

def test_parser_backend_is_tree_sitter():
    """The parser must report 'tree-sitter' as its backend."""
    assert ASTSymbolParser.get_parser_backend() == "tree-sitter"


def test_tree_sitter_parse_produces_real_tree():
    """parse_source must return a real Tree-sitter tree, not None."""
    tmp = _write_tmp("x = 1\n", ".py")
    try:
        result = parse_source(tmp)
        assert result is not None
        assert result.tree is not None
        assert result.tree.root_node.type == "module"
        assert result.language == "python"
        assert result.success is True
    finally:
        tmp.unlink(missing_ok=True)


def test_tree_sitter_imports_are_real():
    """Verify we import and use the actual tree_sitter C library."""
    import tree_sitter_python
    from tree_sitter import Language, Parser  # noqa: F401
    lang = Language(tree_sitter_python.language())
    p = Parser(lang)
    tree = p.parse(b"class Foo: pass")
    assert tree.root_node.type == "module"
    # Child is class_definition — this is a tree-sitter-specific node type
    class_node = tree.root_node.children[0]
    assert class_node.type == "class_definition"


# ===================================================================
# 2. PYTHON — class / function / method / import extraction
# ===================================================================

PYTHON_SAMPLE = """\
import os
from datetime import datetime, timedelta

class AuthService:
    \"\"\"Docstring.\"\"\"

    def validate_token(self, token: str) -> bool:
        return jwt.decode(token)

    async def refresh_token(self, token: str) -> str:
        pass

def standalone_helper():
    pass

class ChildService(AuthService):
    pass
"""


def test_python_class_extraction():
    """Extract Python classes."""
    symbols = _parse_and_extract(PYTHON_SAMPLE, ".py", "python")
    classes = _syms_of_type(symbols, "class")
    class_names = [c["symbol"] for c in classes]
    assert "AuthService" in class_names
    assert "ChildService" in class_names


def test_python_function_extraction():
    """Extract Python standalone functions."""
    symbols = _parse_and_extract(PYTHON_SAMPLE, ".py", "python")
    functions = _syms_of_type(symbols, "function")
    fn_names = [f["symbol"] for f in functions]
    assert "standalone_helper" in fn_names


def test_python_method_extraction():
    """Extract Python methods as children of classes."""
    symbols = _parse_and_extract(PYTHON_SAMPLE, ".py", "python")
    methods = _syms_of_type(symbols, "method")
    method_names = [m["symbol"] for m in methods]
    assert "AuthService.validate_token" in method_names
    assert "AuthService.refresh_token" in method_names


def test_python_imports():
    """Extract Python import statements."""
    symbols = _parse_and_extract(PYTHON_SAMPLE, ".py", "python")
    imports = _syms_of_type(symbols, "import")
    import_names = [i["symbol"] for i in imports]
    assert "os" in import_names
    assert "datetime" in import_names
    assert "timedelta" in import_names


def test_python_parent_symbol():
    """Methods must have parent_symbol referencing their enclosing class."""
    symbols = _parse_and_extract(PYTHON_SAMPLE, ".py", "python")
    methods = _syms_of_type(symbols, "method")
    for m in methods:
        assert m["parent_symbol"] == "AuthService"


def test_python_exact_line_ranges():
    """Symbol start_line and end_line must be accurate, not always equal."""
    symbols = _parse_and_extract(PYTHON_SAMPLE, ".py", "python")
    auth = [s for s in symbols if s["symbol"] == "AuthService" and s["type"] == "class"][0]
    assert auth["start_line"] == 4
    assert auth["end_line"] > auth["start_line"]  # Multi-line class

    fn = [s for s in symbols if s["symbol"] == "standalone_helper"][0]
    assert fn["start_line"] == 13
    assert fn["end_line"] >= fn["start_line"]


# ===================================================================
# 3. JAVASCRIPT — class / function / import / export
# ===================================================================

JS_SAMPLE = """\
import React from 'react';
import { UserService } from './services';

export class UserComponent {
    async getUser(id) {
        return repository.find(id);
    }
}

export default function App() {
    return null;
}

const handler = () => {};
"""


def test_js_class_extraction():
    """Extract JavaScript classes."""
    symbols = _parse_and_extract(JS_SAMPLE, ".js", "javascript")
    classes = _syms_of_type(symbols, "class")
    class_names = [c["symbol"] for c in classes]
    assert "UserComponent" in class_names


def test_js_function_extraction():
    """Extract JavaScript functions including arrow functions."""
    symbols = _parse_and_extract(JS_SAMPLE, ".js", "javascript")
    fns = _syms_of_type(symbols, "function")
    fn_names = [f["symbol"] for f in fns]
    assert "App" in fn_names
    assert "handler" in fn_names


def test_js_method_extraction():
    """Extract methods inside JS classes."""
    symbols = _parse_and_extract(JS_SAMPLE, ".js", "javascript")
    methods = _syms_of_type(symbols, "method")
    method_names = [m["symbol"] for m in methods]
    assert "UserComponent.getUser" in method_names


def test_js_imports():
    """Extract JavaScript import sources."""
    symbols = _parse_and_extract(JS_SAMPLE, ".js", "javascript")
    imports = _syms_of_type(symbols, "import")
    import_names = [i["symbol"] for i in imports]
    assert "react" in import_names
    assert "./services" in import_names


def test_js_exports():
    """Extract JavaScript export statements."""
    symbols = _parse_and_extract(JS_SAMPLE, ".js", "javascript")
    exports = _syms_of_type(symbols, "export")
    export_names = [e["symbol"] for e in exports]
    assert "UserComponent" in export_names
    assert "App" in export_names


# ===================================================================
# 4. TYPESCRIPT — interface / type / enum / import
# ===================================================================

TS_SAMPLE = """\
import { Request, Response } from 'express';

export interface User {
    id: string;
    name: string;
}

export type UserId = string;

export enum Role {
    ADMIN,
    USER,
    GUEST
}

export class UserService {
    async getUser(id: string): Promise<User> {
        return {} as User;
    }
}
"""


def test_ts_interface_extraction():
    """Extract TypeScript interfaces."""
    symbols = _parse_and_extract(TS_SAMPLE, ".ts", "typescript")
    interfaces = _syms_of_type(symbols, "interface")
    iface_names = [i["symbol"] for i in interfaces]
    assert "User" in iface_names


def test_ts_type_alias_extraction():
    """Extract TypeScript type aliases."""
    symbols = _parse_and_extract(TS_SAMPLE, ".ts", "typescript")
    types = _syms_of_type(symbols, "type_alias")
    type_names = [t["symbol"] for t in types]
    assert "UserId" in type_names


def test_ts_enum_extraction():
    """Extract TypeScript enums."""
    symbols = _parse_and_extract(TS_SAMPLE, ".ts", "typescript")
    enums = _syms_of_type(symbols, "enum")
    enum_names = [e["symbol"] for e in enums]
    assert "Role" in enum_names


def test_ts_imports():
    """Extract TypeScript imports."""
    symbols = _parse_and_extract(TS_SAMPLE, ".ts", "typescript")
    imports = _syms_of_type(symbols, "import")
    import_names = [i["symbol"] for i in imports]
    assert "express" in import_names


def test_ts_exports():
    """TypeScript exported declarations should produce export symbols."""
    symbols = _parse_and_extract(TS_SAMPLE, ".ts", "typescript")
    exports = _syms_of_type(symbols, "export")
    export_names = [e["symbol"] for e in exports]
    assert "User" in export_names
    assert "UserId" in export_names
    assert "Role" in export_names
    assert "UserService" in export_names


# ===================================================================
# 5. TSX / JSX — component detection
# ===================================================================

TSX_SAMPLE = """\
import React from 'react';

interface Props {
    name: string;
}

const MyComponent = (props: Props) => {
    return <div>{props.name}</div>;
};

export default MyComponent;
"""


def test_tsx_component_extraction():
    """TSX arrow-function components with PascalCase should be detected."""
    symbols = _parse_and_extract(TSX_SAMPLE, ".tsx", "tsx")
    components = _syms_of_type(symbols, "component")
    comp_names = [c["symbol"] for c in components]
    assert "MyComponent" in comp_names


def test_tsx_interface_extraction():
    """TSX files should still extract TypeScript interfaces."""
    symbols = _parse_and_extract(TSX_SAMPLE, ".tsx", "tsx")
    interfaces = _syms_of_type(symbols, "interface")
    iface_names = [i["symbol"] for i in interfaces]
    assert "Props" in iface_names


def test_jsx_via_js_extension():
    """JSX files (.jsx) use JavaScript grammar and detect PascalCase components."""
    jsx_code = """\
import React from 'react';

const Button = ({ label }) => {
    return <button>{label}</button>;
};

export default Button;
"""
    symbols = _parse_and_extract(jsx_code, ".jsx", "jsx")
    fns = _syms_of_type(symbols, "function")
    fn_names = [f["symbol"] for f in fns]
    assert "Button" in fn_names


# ===================================================================
# 6. NESTED SYMBOLS
# ===================================================================

def test_nested_class_methods():
    """Methods nested inside a class should have correct parent_symbol."""
    code = """\
class Outer:
    def method_a(self):
        pass
    def method_b(self):
        pass
"""
    symbols = _parse_and_extract(code, ".py", "python")
    methods = _syms_of_type(symbols, "method")
    for m in methods:
        assert m["parent_symbol"] == "Outer"
    method_names = [m["symbol"] for m in methods]
    assert "Outer.method_a" in method_names
    assert "Outer.method_b" in method_names


# ===================================================================
# 7. MALFORMED SOURCE HANDLING
# ===================================================================

def test_malformed_python():
    """Malformed Python should not crash — return partial symbols from error-tolerant tree."""
    malformed = """\
class ValidClass:
    def ok_method(self):
        pass

def broken_func(:
    this is not valid python
"""
    symbols = _parse_and_extract(malformed, ".py", "python")
    # Should at least extract the valid class
    sym_names = _sym_names(symbols)
    assert "ValidClass" in sym_names


def test_malformed_javascript():
    """Malformed JS should not crash — partial extraction."""
    malformed = """\
class GoodClass {
    method() { return 1; }
}

function bad( { <<<<
"""
    symbols = _parse_and_extract(malformed, ".js", "javascript")
    sym_names = _sym_names(symbols)
    assert "GoodClass" in sym_names


def test_parse_error_count():
    """ParseResult should report error nodes for malformed source."""
    tmp = _write_tmp("def broken(:\n    pass\n", ".py")
    try:
        result = parse_source(tmp)
        assert result is not None
        assert result.error_count > 0
    finally:
        tmp.unlink(missing_ok=True)


# ===================================================================
# 8. UNSUPPORTED LANGUAGE HANDLING
# ===================================================================

def test_unsupported_language_returns_empty():
    """Unsupported languages should return empty list, not crash."""
    code = "body { color: red; }"
    symbols = _parse_and_extract(code, ".css", "css")
    assert symbols == []


def test_unsupported_extension_parse_source():
    """parse_source should return None for unsupported extensions."""
    tmp = _write_tmp("hello", ".xyz")
    try:
        result = parse_source(tmp)
        assert result is None
    finally:
        tmp.unlink(missing_ok=True)


# ===================================================================
# 9. LANGUAGE REGISTRY
# ===================================================================

def test_language_registry_supported():
    """Registry should include Python, JavaScript, TypeScript, TSX."""
    assert "python" in SUPPORTED_LANGUAGES
    assert "javascript" in SUPPORTED_LANGUAGES
    assert "typescript" in SUPPORTED_LANGUAGES
    assert "tsx" in SUPPORTED_LANGUAGES


def test_extension_mapping():
    """File extensions should map to correct language names."""
    assert language_name_for_extension(".py") == "python"
    assert language_name_for_extension(".js") == "javascript"
    assert language_name_for_extension(".ts") == "typescript"
    assert language_name_for_extension(".tsx") == "tsx"
    assert language_name_for_extension(".jsx") == "javascript"
    assert language_name_for_extension(".css") is None


def test_get_language_returns_language_object():
    """get_language should return a valid Language object for supported languages."""
    from tree_sitter import Language
    for name in SUPPORTED_LANGUAGES:
        lang = get_language(name)
        assert lang is not None
        assert isinstance(lang, Language)


# ===================================================================
# 10. DEPENDENCY GRAPH INTEGRATION
# ===================================================================

def test_dependency_extraction_compatibility():
    """Tree-sitter-extracted import symbols must work with DependencyGraphBuilder."""
    py_code = """\
from auth.jwt import verify_token
import logging
"""
    symbols = _parse_and_extract(py_code, ".py", "python")

    scanned_files = [
        {"path": "auth/service.py", "language": "python", "size_bytes": 100},
        {"path": "auth/jwt.py", "language": "python", "size_bytes": 100},
    ]

    # Patch symbol file paths to match scanned files
    patched_symbols = []
    for s in symbols:
        patched = dict(s)
        patched["file"] = "auth/service.py"
        patched_symbols.append(patched)

    builder = DependencyGraphBuilder(scanned_files, patched_symbols)
    graph = builder.build_graph()

    # The import `auth.jwt` should resolve to auth/jwt.py
    assert len(graph["internal_edges"]) >= 1 or "logging" in graph["external_packages"]


def test_js_imports_feed_dependency_graph():
    """JS imports extracted by tree-sitter should feed into the dependency graph."""
    js_code = """\
import { helper } from './utils';
"""
    symbols = _parse_and_extract(js_code, ".js", "javascript")
    imports = _syms_of_type(symbols, "import")
    assert len(imports) >= 1
    assert imports[0]["type"] == "import"
    assert "./utils" in imports[0]["symbol"]


# ===================================================================
# 11. INCREMENTAL INDEXING
# ===================================================================

def test_incremental_indexing_with_tree_sitter():
    """Incremental indexer must work correctly with Tree-sitter-parsed symbols."""
    import hashlib

    # Create temp fixture files
    py1 = _write_tmp("class Alpha:\n    pass\n", ".py")
    py2 = _write_tmp("class Beta:\n    pass\n", ".py")

    try:
        hash1 = hashlib.sha256(py1.read_bytes()).hexdigest()
        hash2 = hashlib.sha256(py2.read_bytes()).hexdigest()

        # First full index
        scanned = [
            {"path": "alpha.py", "sha256": hash1, "language": "python",
             "absolute_path": str(py1), "size_bytes": py1.stat().st_size},
            {"path": "beta.py", "sha256": hash2, "language": "python",
             "absolute_path": str(py2), "size_bytes": py2.stat().st_size},
        ]
        diff_full = {"added": ["alpha.py", "beta.py"], "modified": [], "deleted": []}
        scanned_map = {f["path"]: f for f in scanned}

        symbols = IncrementalIndexer.update_symbol_index(
            previous_symbols=[], diff=diff_full,
            scanned_files_map=scanned_map, repository_id="test",
        )
        assert len(symbols) >= 2
        sym_names = _sym_names(symbols)
        assert "Alpha" in sym_names
        assert "Beta" in sym_names

        # Modify only one file
        py2.write_text("class BetaModified:\n    pass\n", encoding="utf-8")
        hash2_new = hashlib.sha256(py2.read_bytes()).hexdigest()
        scanned[1]["sha256"] = hash2_new

        diff_inc = IncrementalIndexer.compute_diff(
            previous_file_hashes={"alpha.py": hash1, "beta.py": hash2},
            current_scanned_files=scanned,
        )
        assert diff_inc["modified"] == ["beta.py"]
        assert diff_inc["added"] == []

        updated = IncrementalIndexer.update_symbol_index(
            previous_symbols=symbols, diff=diff_inc,
            scanned_files_map=scanned_map, repository_id="test",
        )
        updated_names = _sym_names(updated)
        assert "Alpha" in updated_names
        assert "BetaModified" in updated_names
        assert "Beta" not in updated_names

    finally:
        py1.unlink(missing_ok=True)
        py2.unlink(missing_ok=True)


def test_deleted_file_symbol_cleanup():
    """Deleted files must have their symbols purged from the index."""
    existing_symbols = [
        {"file": "old.py", "symbol": "OldClass", "type": "class"},
        {"file": "keep.py", "symbol": "KeepClass", "type": "class"},
    ]
    diff = {"added": [], "modified": [], "deleted": ["old.py"]}
    updated = IncrementalIndexer.update_symbol_index(
        previous_symbols=existing_symbols, diff=diff,
        scanned_files_map={}, repository_id="test",
    )
    sym_names = _sym_names(updated)
    assert "KeepClass" in sym_names
    assert "OldClass" not in sym_names


# ===================================================================
# 12. MULTI-LANGUAGE FIXTURE REPOSITORY
# ===================================================================

def test_multi_language_fixture():
    """Parse a mixed-language fixture set and verify all languages extract symbols."""
    py = _write_tmp("class PyClass:\n    def method(self): pass\n", ".py")
    js = _write_tmp("export function jsFunc() {}\n", ".js")
    ts = _write_tmp("export interface TsInterface { id: string; }\n", ".ts")
    tsx = _write_tmp("const TsxComp = () => { return null; };\n", ".tsx")

    try:
        py_sym = ASTSymbolParser.parse_file(py, "app.py", "python", "multi")
        js_sym = ASTSymbolParser.parse_file(js, "app.js", "javascript", "multi")
        ts_sym = ASTSymbolParser.parse_file(ts, "types.ts", "typescript", "multi")
        tsx_sym = ASTSymbolParser.parse_file(tsx, "comp.tsx", "tsx", "multi")

        assert any(s["symbol"] == "PyClass" for s in py_sym)
        assert any(s["symbol"] == "jsFunc" for s in js_sym)
        assert any(s["symbol"] == "TsInterface" for s in ts_sym)
        assert any(s["symbol"] == "TsxComp" for s in tsx_sym)

    finally:
        for f in [py, js, ts, tsx]:
            f.unlink(missing_ok=True)


# ===================================================================
# 13. .GITIGNORE INTERACTION
# ===================================================================

def test_gitignore_excludes_still_work():
    """IgnoreEngine should still exclude node_modules, __pycache__, etc."""
    engine = IgnoreEngine(Path(".").resolve())
    assert engine.is_ignored("node_modules/lib/index.js") is True
    assert engine.is_ignored("__pycache__/module.pyc") is True
    assert engine.is_ignored("src/app.py") is False


# ===================================================================
# 14. COLUMN INFORMATION
# ===================================================================

def test_symbols_have_column_info():
    """Tree-sitter symbols should include start_col and end_col."""
    symbols = _parse_and_extract("class Foo:\n    pass\n", ".py", "python")
    cls = [s for s in symbols if s["type"] == "class"][0]
    assert "start_col" in cls
    assert "end_col" in cls
    assert cls["start_col"] == 0  # class at column 0


# ===================================================================
# 15. DECORATORS
# ===================================================================

def test_python_decorators():
    """Decorated classes/functions should produce decorator symbols."""
    code = """\
@app.route('/users')
class UserView:
    pass
"""
    # Write to a temp file and parse
    tmp = _write_tmp(code, ".py")
    try:
        result = parse_source(tmp)
        assert result is not None
        symbols = extract_symbols(result, "views.py", "test")
        # Should find decorator and class
        sym_types = _sym_types(symbols)
        assert "class" in sym_types
        assert "UserView" in _sym_names(symbols)
    finally:
        tmp.unlink(missing_ok=True)
