"""Java file parser using tree-sitter to extract class/method/call info."""

import logging
import sys
from pathlib import Path

import tree_sitter_java as tsjava
from tree_sitter import Language, Node, Parser

from kg_mcp.graph.models import FileType, JavaNode, MethodInfo

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))

JAVA_LANGUAGE = Language(tsjava.language())

_SUFFIX_MAP: list[tuple[str, FileType]] = [
    ("Test.java", FileType.TEST),
    ("Task.java", FileType.TASK),
    ("Qst.java", FileType.QST),
    ("Entity.java", FileType.ENTITY),
    ("Config.java", FileType.CONFIG),
]


class JavaParser:
    def __init__(self) -> None:
        self._parser = Parser(JAVA_LANGUAGE)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_file(self, file_path: Path) -> FileType | None:
        name = file_path.name
        for suffix, file_type in _SUFFIX_MAP:
            if name.endswith(suffix):
                return file_type
        return None

    def parse_file(self, file_path: Path) -> JavaNode | None:
        file_type = self.classify_file(file_path)
        if file_type is None:
            return None
        try:
            source = file_path.read_bytes()
            tree = self._parser.parse(source)
            class_node = self._find_first(tree.root_node, "class_declaration")
            if class_node is None:
                logger.debug("No class_declaration in %s", file_path)
                return None
            # Use child_by_field_name to get the actual class name,
            # not an annotation identifier like @ExtendWith
            name_node = class_node.child_by_field_name("name")
            class_name = self._node_text(name_node, source) or file_path.stem
            methods = self._extract_methods(class_node, source)
            return JavaNode(
                class_name=class_name,
                file_path=str(file_path),
                file_type=file_type,
                methods=methods,
            )
        except Exception as exc:
            logger.error("Failed to parse %s: %s", file_path, exc)
            return None

    def extract_method_calls(self, method_node: Node, source: bytes) -> list[str]:
        calls: list[str] = []
        self._collect_calls(method_node, source, calls)
        return calls

    def parse_project(self, project_path: Path) -> list[JavaNode]:
        nodes: list[JavaNode] = []
        for java_file in project_path.rglob("*.java"):
            node = self.parse_file(java_file)
            if node is not None:
                nodes.append(node)
        return nodes

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _find_first(self, node: Node, kind: str) -> Node | None:
        if node.type == kind:
            return node
        for child in node.children:
            result = self._find_first(child, kind)
            if result is not None:
                return result
        return None

    def _find_all(self, node: Node, kind: str) -> list[Node]:
        results: list[Node] = []
        if node.type == kind:
            results.append(node)
        for child in node.children:
            results.extend(self._find_all(child, kind))
        return results

    def _node_text(self, node: Node | None, source: bytes) -> str:
        if node is None:
            return ""
        return source[node.start_byte:node.end_byte].decode(errors="replace")

    def _extract_methods(self, class_node: Node, source: bytes) -> list[MethodInfo]:
        methods: list[MethodInfo] = []
        for method_node in self._find_all(class_node, "method_declaration"):
            name_node = method_node.child_by_field_name("name")
            name = self._node_text(name_node, source)
            line = method_node.start_point[0] + 1
            calls = self.extract_method_calls(method_node, source)
            methods.append(MethodInfo(name=name, line_number=line, calls=calls))
        return methods

    def _collect_calls(self, node: Node, source: bytes, calls: list[str]) -> None:
        if node.type == "method_invocation":
            # method_invocation: [object '.'] method_name '(' args ')'
            # The method name is the last identifier before the argument_list
            name = self._invocation_method_name(node, source)
            if name:
                calls.append(name)
        for child in node.children:
            self._collect_calls(child, source, calls)

    def _invocation_method_name(self, node: Node, source: bytes) -> str:
        """Return the method name from a method_invocation node."""
        # tree-sitter Java: method_invocation has a 'name' field
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return self._node_text(name_node, source)
        # Fallback: last identifier before argument_list
        last_ident = ""
        for child in node.children:
            if child.type == "argument_list":
                break
            if child.type == "identifier":
                last_ident = self._node_text(child, source)
        return last_ident
