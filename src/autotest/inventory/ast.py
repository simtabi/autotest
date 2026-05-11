"""tree-sitter-backed source-file walker.

Reads a source file and emits a flat list of testable units (public methods,
top-level functions). The output is intentionally language-agnostic -- the
language adapter supplies the tree-sitter ``Language`` and tells us which
node types correspond to "testable unit," and this module returns a uniform
``DiscoveredUnit`` shape that the rest of the pipeline consumes.

Why per-language grammars instead of tree-sitter-language-pack:

The language-pack ships its own C bindings that are incompatible with the
public ``tree_sitter`` Python module's ``Parser`` / ``Language`` types
(verified against 1.8.0 on macOS arm64). The first-party per-language
packages (``tree-sitter-php``, ``tree-sitter-javascript``, etc.) work
cleanly and let us pick the grammar at adapter load time.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language, Node, Parser


@dataclass(frozen=True, slots=True)
class DiscoveredUnit:
    """One testable unit discovered in a source file.

    Holds enough context to (a) decide whether it's already covered and
    (b) build a prompt for the generator without re-reading the file.
    """

    file: Path
    name: str              # class::method for OO langs, just `fn_name` otherwise
    kind: str              # "method" | "function"
    visibility: str        # "public" | "protected" | "private"  -- adapter-defined
    start_line: int        # 1-based
    end_line: int          # 1-based, inclusive
    source: str            # the full source of the unit, dedented
    parent: str | None     # containing class / module name, if any
    signature: str         # e.g. "public function foo(int $x): bool"
    docblock: str | None   # leading docblock, if present


@dataclass(frozen=True, slots=True)
class AstRules:
    """Per-language rules that drive the walker.

    Adapters configure these constants once and the walker doesn't need to
    know anything else about the language. New languages plug in by adding
    an ``AstRules`` instance.
    """

    language: Language                  # tree-sitter Language object
    class_node_types: tuple[str, ...]   # nodes that introduce a class/namespace
    method_node_types: tuple[str, ...]  # nodes that introduce a method/function
    name_field: str                     # field name for the identifier child
    visibility_node_types: tuple[str, ...] = ()  # e.g. ("visibility_modifier",)
    docblock_node_types: tuple[str, ...] = ("comment",)


def discover(source_path: Path, rules: AstRules) -> list[DiscoveredUnit]:
    """Walk ``source_path`` and return every testable unit it contains.

    The walker is conservative: it only returns units whose visibility is
    ``"public"`` (or absent, treated as public). Internal helpers are left
    out because there is no point generating tests for code the consumer
    cannot call directly.
    """
    source_bytes = source_path.read_bytes()
    parser = Parser(rules.language)
    tree = parser.parse(source_bytes)
    return list(_walk(tree.root_node, source_bytes, source_path, rules, parent=None))


def _walk(
    node: Node,
    source: bytes,
    source_path: Path,
    rules: AstRules,
    parent: str | None,
) -> Iterable[DiscoveredUnit]:
    """Depth-first walk yielding units; recurses into class bodies."""
    if node.type in rules.class_node_types:
        class_name = _identifier(node, rules.name_field, source) or "<anonymous>"
        for child in node.children:
            yield from _walk(child, source, source_path, rules, parent=class_name)
        return

    if node.type in rules.method_node_types:
        visibility = _visibility(node, source, rules) or "public"
        if visibility != "public":
            return
        name = _identifier(node, rules.name_field, source) or "<anonymous>"
        unit = DiscoveredUnit(
            file=source_path,
            name=f"{parent}::{name}" if parent else name,
            kind="method" if parent else "function",
            visibility=visibility,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            source=_slice(source, node).decode("utf-8", errors="replace"),
            parent=parent,
            signature=_signature(node, source),
            docblock=_leading_docblock(node, source, rules),
        )
        yield unit
        return

    for child in node.children:
        yield from _walk(child, source, source_path, rules, parent=parent)


def _identifier(node: Node, field: str, source: bytes) -> str | None:
    """Resolve the identifier child by tree-sitter field name, falling back
    to a plain ``name`` / ``identifier`` descendant if the field-style
    lookup misses (grammars are inconsistent about field naming)."""
    ident = node.child_by_field_name(field)
    if ident is not None:
        return _slice(source, ident).decode("utf-8")
    for child in node.children:
        if child.type in ("name", "identifier"):
            return _slice(source, child).decode("utf-8")
    return None


def _visibility(node: Node, source: bytes, rules: AstRules) -> str | None:
    """Look for a visibility modifier among the method's children.

    PHP attaches visibility as a sibling token (``visibility_modifier``);
    JS bakes it into the method name (``#private``). Adapters set
    ``visibility_node_types`` to whatever fits their language.
    """
    for child in node.children:
        if child.type in rules.visibility_node_types:
            return _slice(source, child).decode("utf-8", errors="ignore").strip()
    return None


def _signature(node: Node, source: bytes) -> str:
    """Return the first non-empty line of the unit as a stand-in for the
    full signature. Good enough for prompt context; cheap to compute."""
    text = _slice(source, node).decode("utf-8", errors="replace")
    for line in text.splitlines():
        if line.strip():
            return line.strip()
    return ""


def _leading_docblock(node: Node, source: bytes, rules: AstRules) -> str | None:
    """Walk backwards from the unit to find the nearest preceding comment.

    Stops at the first non-comment sibling so unrelated comments earlier in
    the file don't get attached.
    """
    sibling = node.prev_sibling
    if sibling is None or sibling.type not in rules.docblock_node_types:
        return None
    return _slice(source, sibling).decode("utf-8", errors="replace")


def _slice(source: bytes, node: Node) -> bytes:
    """Return the source bytes for ``node``."""
    return source[node.start_byte : node.end_byte]
