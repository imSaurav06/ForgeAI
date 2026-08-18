"""
Symbol Extractor — walks Tree-sitter syntax trees and extracts structured
symbol records compatible with the existing ForgeAI indexing pipeline.

Supported symbol types: class, function, method, interface, enum, type_alias,
import, export, decorator, component, variable.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tree_sitter import Node

from services.repository.app.core.parsers.tree_sitter_parser import ParseResult

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_symbols(
    parse_result: ParseResult,
    relative_path: str,
    repository_id: str = "repo",
) -> list[dict[str, Any]]:
    """
    Extract all structured symbols from a Tree-sitter ``ParseResult``.

    Returns a list of symbol dicts compatible with ``SymbolItem`` and the
    existing dependency / indexing pipeline.
    """
    if parse_result.tree is None:
        return []

    lang = parse_result.language
    root = parse_result.tree.root_node
    src = parse_result.source_bytes

    if lang == "python":
        return _extract_python(root, src, relative_path, repository_id)
    elif lang in ("javascript", "typescript", "tsx"):
        return _extract_js_ts(root, src, relative_path, lang, repository_id)
    return []


# ===================================================================
# PYTHON
# ===================================================================

def _extract_python(
    root: Node,
    src: bytes,
    relative_path: str,
    repository_id: str,
) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []

    def _visit(node: Node, parent_class: str | None = None) -> None:
        ntype = node.type

        # ---- imports ----
        if ntype == "import_statement":
            _handle_python_import(node, src, symbols, relative_path, repository_id)

        elif ntype == "import_from_statement":
            _handle_python_import_from(node, src, symbols, relative_path, repository_id)

        # ---- class ----
        elif ntype == "class_definition":
            class_name = _named_child_text(node, "identifier", src) or ""
            bases = _python_class_bases(node, src)
            base_str = f"({', '.join(bases)})" if bases else ""
            signature = f"class {class_name}{base_str}"

            # Decorators
            _extract_python_decorators(node, src, symbols, relative_path, repository_id, class_name)

            symbols.append(_sym(
                repository_id, relative_path, class_name, "class", "python",
                node, signature, parent_symbol=None,
            ))
            # Recurse into class body
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    _visit(child, parent_class=class_name)
            return  # Don't generic-visit again

        # ---- function / method ----
        elif ntype == "function_definition":
            fn_name = _named_child_text(node, "identifier", src) or ""
            is_method = parent_class is not None
            sym_type = "method" if is_method else "function"
            sym_name = f"{parent_class}.{fn_name}" if is_method else fn_name
            params = _python_params(node, src)
            signature = f"def {fn_name}({params})"

            # Decorators on standalone functions
            if not is_method:
                _extract_python_decorators(node, src, symbols, relative_path, repository_id, fn_name)

            symbols.append(_sym(
                repository_id, relative_path, sym_name, sym_type, "python",
                node, signature, parent_symbol=parent_class,
            ))
            # Don't recurse into nested functions' children for symbols (keep it flat)
            return

        # ---- decorated_definition wraps classes / functions ----
        elif ntype == "decorated_definition":
            for child in node.children:
                _visit(child, parent_class)
            return

        # Generic children
        for child in node.children:
            _visit(child, parent_class)

    _visit(root)
    return symbols


def _handle_python_import(
    node: Node, src: bytes, symbols: list, relative_path: str, repository_id: str,
) -> None:
    """Handle `import foo, bar.baz` statements."""
    for child in node.children:
        if child.type == "dotted_name":
            name = child.text.decode("utf-8", errors="ignore")
            symbols.append(_sym(
                repository_id, relative_path, name, "import", "python",
                node, f"import {name}", parent_symbol=None,
            ))
        elif child.type == "aliased_import":
            dotted = _first_named_child_of_type(child, "dotted_name")
            name = dotted.text.decode("utf-8", errors="ignore") if dotted else child.text.decode("utf-8", errors="ignore")
            symbols.append(_sym(
                repository_id, relative_path, name, "import", "python",
                node, f"import {name}", parent_symbol=None,
            ))


def _handle_python_import_from(
    node: Node, src: bytes, symbols: list, relative_path: str, repository_id: str,
) -> None:
    """Handle `from module import name1, name2` statements."""
    module_node = node.child_by_field_name("module_name")
    if module_node is None:
        # Try to find the dotted_name or relative_import child
        for child in node.children:
            if child.type in ("dotted_name", "relative_import"):
                module_node = child
                break
    module = module_node.text.decode("utf-8", errors="ignore") if module_node else ""

    # Collect imported names
    for child in node.children:
        if child.type == "dotted_name" and child != module_node:
            name = child.text.decode("utf-8", errors="ignore")
            symbols.append(_sym(
                repository_id, relative_path, name, "import", "python",
                node, f"from {module} import {name}", parent_symbol=None,
            ))
        elif child.type == "aliased_import":
            dotted = _first_named_child_of_type(child, "dotted_name")
            if dotted is None:
                dotted = _first_named_child_of_type(child, "identifier")
            name = dotted.text.decode("utf-8", errors="ignore") if dotted else ""
            if name:
                symbols.append(_sym(
                    repository_id, relative_path, name, "import", "python",
                    node, f"from {module} import {name}", parent_symbol=None,
                ))
        elif child.type == "import_prefix":
            continue  # relative dots, module_node handles this
        elif child.type == "wildcard_import":
            symbols.append(_sym(
                repository_id, relative_path, "*", "import", "python",
                node, f"from {module} import *", parent_symbol=None,
            ))


def _extract_python_decorators(
    node: Node, src: bytes, symbols: list, relative_path: str, repository_id: str, target_name: str,
) -> None:
    """Extract decorators from a decorated parent node if present."""
    parent = node.parent
    if parent and parent.type == "decorated_definition":
        for child in parent.children:
            if child.type == "decorator":
                dec_text = child.text.decode("utf-8", errors="ignore").strip()
                symbols.append(_sym(
                    repository_id, relative_path, dec_text, "decorator", "python",
                    child, dec_text, parent_symbol=target_name,
                ))


def _python_class_bases(node: Node, src: bytes) -> list[str]:
    """Extract base class names from a class_definition's argument_list."""
    bases: list[str] = []
    arg_list = node.child_by_field_name("superclasses")
    if arg_list:
        for child in arg_list.children:
            if child.is_named:
                bases.append(child.text.decode("utf-8", errors="ignore"))
    return bases


def _python_params(node: Node, src: bytes) -> str:
    """Get the raw parameter text for a function_definition."""
    params_node = node.child_by_field_name("parameters")
    if params_node:
        inner = params_node.text.decode("utf-8", errors="ignore")
        # Strip surrounding parens
        if inner.startswith("(") and inner.endswith(")"):
            return inner[1:-1]
        return inner
    return ""


# ===================================================================
# JAVASCRIPT / TYPESCRIPT / TSX
# ===================================================================

def _extract_js_ts(
    root: Node,
    src: bytes,
    relative_path: str,
    language: str,
    repository_id: str,
) -> list[dict[str, Any]]:
    symbols: list[dict[str, Any]] = []

    def _visit(node: Node, parent_class: str | None = None, is_exported: bool = False) -> None:
        ntype = node.type

        # ---- imports ----
        if ntype == "import_statement":
            _handle_js_import(node, src, symbols, relative_path, language, repository_id)

        # ---- export ----
        elif ntype == "export_statement":
            _handle_js_export(node, src, symbols, relative_path, language, repository_id)
            return  # _handle_js_export recurses internally

        # ---- class declaration ----
        elif ntype == "class_declaration":
            cls_name = _class_name(node, src)
            extends = _js_extends(node, src)
            ext_str = f" extends {extends}" if extends else ""
            signature = f"class {cls_name}{ext_str}"
            symbols.append(_sym(
                repository_id, relative_path, cls_name, "class", language,
                node, signature, parent_symbol=None,
            ))
            if is_exported:
                symbols.append(_sym(
                    repository_id, relative_path, cls_name, "export", language,
                    node, f"export class {cls_name}", parent_symbol=None,
                ))
            body = _first_named_child_of_type(node, "class_body")
            if body:
                for child in body.children:
                    _visit(child, parent_class=cls_name)
            return

        # ---- method definition (inside class body) ----
        elif ntype == "method_definition":
            method_name = _named_child_text(node, "property_identifier", src) or ""
            sym_name = f"{parent_class}.{method_name}" if parent_class else method_name
            params = _js_params(node, src)
            signature = f"{method_name}({params})"
            symbols.append(_sym(
                repository_id, relative_path, sym_name, "method", language,
                node, signature, parent_symbol=parent_class,
            ))
            return

        # ---- function declaration ----
        elif ntype == "function_declaration":
            fn_name = _named_child_text(node, "identifier", src) or ""
            params = _js_params(node, src)
            signature = f"function {fn_name}({params})"
            symbols.append(_sym(
                repository_id, relative_path, fn_name, "function", language,
                node, signature, parent_symbol=None,
            ))
            if is_exported:
                symbols.append(_sym(
                    repository_id, relative_path, fn_name, "export", language,
                    node, f"export function {fn_name}", parent_symbol=None,
                ))
            return

        # ---- arrow function assigned to const/let/var ----
        elif ntype == "lexical_declaration":
            _handle_js_lexical(node, src, symbols, relative_path, language, repository_id, is_exported)
            return

        # ---- TypeScript: interface ----
        elif ntype == "interface_declaration":
            iface_name = _named_child_text(node, "type_identifier", src) or ""
            symbols.append(_sym(
                repository_id, relative_path, iface_name, "interface", language,
                node, f"interface {iface_name}", parent_symbol=None,
            ))
            if is_exported:
                symbols.append(_sym(
                    repository_id, relative_path, iface_name, "export", language,
                    node, f"export interface {iface_name}", parent_symbol=None,
                ))
            return

        # ---- TypeScript: type alias ----
        elif ntype == "type_alias_declaration":
            type_name = _named_child_text(node, "type_identifier", src) or ""
            symbols.append(_sym(
                repository_id, relative_path, type_name, "type_alias", language,
                node, f"type {type_name}", parent_symbol=None,
            ))
            if is_exported:
                symbols.append(_sym(
                    repository_id, relative_path, type_name, "export", language,
                    node, f"export type {type_name}", parent_symbol=None,
                ))
            return

        # ---- TypeScript: enum ----
        elif ntype == "enum_declaration":
            enum_name = _named_child_text(node, "identifier", src) or ""
            symbols.append(_sym(
                repository_id, relative_path, enum_name, "enum", language,
                node, f"enum {enum_name}", parent_symbol=None,
            ))
            if is_exported:
                symbols.append(_sym(
                    repository_id, relative_path, enum_name, "export", language,
                    node, f"export enum {enum_name}", parent_symbol=None,
                ))
            return

        # Generic children
        for child in node.children:
            _visit(child, parent_class)

    _visit(root)
    return symbols


def _handle_js_import(
    node: Node, src: bytes, symbols: list, relative_path: str, language: str, repository_id: str,
) -> None:
    """Extract import source and imported names from JS/TS import statements."""
    source_str = ""
    for child in node.children:
        if child.type == "string":
            frag = _first_named_child_of_type(child, "string_fragment")
            source_str = frag.text.decode("utf-8", errors="ignore") if frag else child.text.decode("utf-8", errors="ignore").strip("'\"")
            break

    if source_str:
        symbols.append(_sym(
            repository_id, relative_path, source_str, "import", language,
            node, node.text.decode("utf-8", errors="ignore").strip(), parent_symbol=None,
        ))


def _handle_js_export(
    node: Node, src: bytes, symbols: list, relative_path: str, language: str, repository_id: str,
) -> None:
    """Handle export statements — recurse into the exported declaration."""
    for child in node.children:
        if child.type in (
            "class_declaration", "function_declaration", "lexical_declaration",
            "interface_declaration", "type_alias_declaration", "enum_declaration",
        ):
            # Visit the inner declaration with is_exported=True
            _extract_js_ts_inner = _visit_export_child
            _extract_js_ts_inner(
                child, src, symbols, relative_path, language, repository_id,
                parent_class=None, is_exported=True,
            )
            return
        elif child.type == "identifier":
            # `export default SomeIdentifier;`
            name = child.text.decode("utf-8", errors="ignore")
            symbols.append(_sym(
                repository_id, relative_path, name, "export", language,
                node, f"export default {name}", parent_symbol=None,
            ))
            return

    # Fallback — export without a recognisable declaration
    text = node.text.decode("utf-8", errors="ignore").strip()
    if text:
        symbols.append(_sym(
            repository_id, relative_path, text[:60], "export", language,
            node, text[:120], parent_symbol=None,
        ))


def _visit_export_child(
    node: Node, src: bytes, symbols: list, relative_path: str, language: str, repository_id: str,
    parent_class: str | None = None, is_exported: bool = False,
) -> None:
    """Visit a single declaration node that was inside an export statement."""
    ntype = node.type

    if ntype == "class_declaration":
        cls_name = _class_name(node, src)
        extends = _js_extends(node, src)
        ext_str = f" extends {extends}" if extends else ""
        symbols.append(_sym(
            repository_id, relative_path, cls_name, "class", language,
            node, f"class {cls_name}{ext_str}", parent_symbol=None,
        ))
        if is_exported:
            symbols.append(_sym(
                repository_id, relative_path, cls_name, "export", language,
                node, f"export class {cls_name}", parent_symbol=None,
            ))
        body = _first_named_child_of_type(node, "class_body")
        if body:
            for child in body.children:
                _visit_export_child(child, src, symbols, relative_path, language, repository_id, parent_class=cls_name)
        return

    if ntype == "method_definition":
        method_name = _named_child_text(node, "property_identifier", src) or ""
        sym_name = f"{parent_class}.{method_name}" if parent_class else method_name
        params = _js_params(node, src)
        symbols.append(_sym(
            repository_id, relative_path, sym_name, "method", language,
            node, f"{method_name}({params})", parent_symbol=parent_class,
        ))
        return

    if ntype == "function_declaration":
        fn_name = _named_child_text(node, "identifier", src) or ""
        params = _js_params(node, src)
        symbols.append(_sym(
            repository_id, relative_path, fn_name, "function", language,
            node, f"function {fn_name}({params})", parent_symbol=None,
        ))
        if is_exported:
            symbols.append(_sym(
                repository_id, relative_path, fn_name, "export", language,
                node, f"export function {fn_name}", parent_symbol=None,
            ))
        return

    if ntype == "lexical_declaration":
        _handle_js_lexical(node, src, symbols, relative_path, language, repository_id, is_exported)
        return

    if ntype == "interface_declaration":
        iface_name = _named_child_text(node, "type_identifier", src) or ""
        symbols.append(_sym(
            repository_id, relative_path, iface_name, "interface", language,
            node, f"interface {iface_name}", parent_symbol=None,
        ))
        if is_exported:
            symbols.append(_sym(
                repository_id, relative_path, iface_name, "export", language,
                node, f"export interface {iface_name}", parent_symbol=None,
            ))
        return

    if ntype == "type_alias_declaration":
        type_name = _named_child_text(node, "type_identifier", src) or ""
        symbols.append(_sym(
            repository_id, relative_path, type_name, "type_alias", language,
            node, f"type {type_name}", parent_symbol=None,
        ))
        if is_exported:
            symbols.append(_sym(
                repository_id, relative_path, type_name, "export", language,
                node, f"export type {type_name}", parent_symbol=None,
            ))
        return

    if ntype == "enum_declaration":
        enum_name = _named_child_text(node, "identifier", src) or ""
        symbols.append(_sym(
            repository_id, relative_path, enum_name, "enum", language,
            node, f"enum {enum_name}", parent_symbol=None,
        ))
        if is_exported:
            symbols.append(_sym(
                repository_id, relative_path, enum_name, "export", language,
                node, f"export enum {enum_name}", parent_symbol=None,
            ))
        return


def _handle_js_lexical(
    node: Node, src: bytes, symbols: list, relative_path: str, language: str,
    repository_id: str, is_exported: bool = False,
) -> None:
    """Handle `const/let/var name = ... ` declarations — detect arrow functions and components."""
    for child in node.children:
        if child.type == "variable_declarator":
            name_node = _first_named_child_of_type(child, "identifier")
            if name_node is None:
                continue
            var_name = name_node.text.decode("utf-8", errors="ignore")

            # Check if the value is an arrow function
            value_node = child.child_by_field_name("value")
            if value_node and value_node.type == "arrow_function":
                params = _js_params(value_node, src)
                symbols.append(_sym(
                    repository_id, relative_path, var_name, "function", language,
                    node, f"const {var_name} = ({params}) => {{...}}",
                    parent_symbol=None,
                ))
                if is_exported:
                    symbols.append(_sym(
                        repository_id, relative_path, var_name, "export", language,
                        node, f"export const {var_name}", parent_symbol=None,
                    ))
                # Detect React component (name starts with uppercase)
                if var_name and var_name[0].isupper():
                    symbols.append(_sym(
                        repository_id, relative_path, var_name, "component", language,
                        node, f"const {var_name} = (...) => ...",
                        parent_symbol=None,
                    ))
            else:
                # Regular variable/constant
                symbols.append(_sym(
                    repository_id, relative_path, var_name, "variable", language,
                    node, f"const {var_name} = ...",
                    parent_symbol=None,
                ))
                if is_exported:
                    symbols.append(_sym(
                        repository_id, relative_path, var_name, "export", language,
                        node, f"export const {var_name}", parent_symbol=None,
                    ))


# ===================================================================
# HELPERS
# ===================================================================

def _sym(
    repository_id: str,
    relative_path: str,
    symbol: str,
    sym_type: str,
    language: str,
    node: Node,
    signature: str,
    parent_symbol: str | None,
) -> dict[str, Any]:
    """Build a normalised symbol dict compatible with the existing pipeline."""
    return {
        "repository_id": repository_id,
        "file": relative_path,
        "symbol": symbol,
        "type": sym_type,
        "language": language,
        "start_line": node.start_point[0] + 1,
        "end_line": node.end_point[0] + 1,
        "start_col": node.start_point[1],
        "end_col": node.end_point[1],
        "signature": signature,
        "parent_symbol": parent_symbol,
    }


def _named_child_text(node: Node, child_type: str, src: bytes) -> str | None:
    """Return the text of the first named child matching ``child_type``."""
    for child in node.children:
        if child.type == child_type:
            return child.text.decode("utf-8", errors="ignore")
    return None


def _first_named_child_of_type(node: Node, child_type: str) -> Node | None:
    """Return the first named child matching ``child_type``, or None."""
    for child in node.children:
        if child.type == child_type:
            return child
    return None


def _class_name(node: Node, src: bytes) -> str:
    """Extract class name from a class_declaration node."""
    for child in node.children:
        if child.type in ("identifier", "type_identifier"):
            return child.text.decode("utf-8", errors="ignore")
    return ""


def _js_extends(node: Node, src: bytes) -> str:
    """Extract extends clause from a JS/TS class_declaration."""
    heritage = node.child_by_field_name("heritage") or _first_named_child_of_type(node, "class_heritage")
    if heritage:
        return heritage.text.decode("utf-8", errors="ignore").replace("extends ", "").strip()
    return ""


def _js_params(node: Node, src: bytes) -> str:
    """Get parameter text from formal_parameters or parameters."""
    for child in node.children:
        if child.type in ("formal_parameters", "parameters"):
            inner = child.text.decode("utf-8", errors="ignore")
            if inner.startswith("(") and inner.endswith(")"):
                return inner[1:-1]
            return inner
    return ""
