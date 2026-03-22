"""Flask route parser using tree-sitter Python grammar."""

import logging
import sys
from pathlib import Path

import tree_sitter_python as tspython
from tree_sitter import Language, Node, Parser

from kg_mcp.graph.models import FlaskEndpoint, FunctionCall

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stderr))

PY_LANGUAGE = Language(tspython.language())

FLASK_APP_VARS = {"app", "appWT", "appWN", "api", "apiInt"}
HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


class FlaskParser:
    def __init__(self) -> None:
        self._parser = Parser(PY_LANGUAGE)

    def _parse_source(self, source: bytes) -> Node:
        return self._parser.parse(source).root_node

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_file(self, file_path: Path) -> list[FlaskEndpoint]:
        """Parse a single Python file and return Flask endpoints."""
        try:
            source = file_path.read_bytes()
            root = self._parse_source(source)
            text = source.decode("utf-8", errors="replace")
            return self._extract_endpoints(root, text, str(file_path))
        except Exception as exc:
            logger.debug("Skipping %s: %s", file_path, exc)
            return []

    def resolve_namespace(self, init_file: Path) -> dict[str, str]:
        """Return mapping: module_file_stem -> namespace_path from __init__.py."""
        if not init_file.exists():
            return {}
        try:
            source = init_file.read_bytes()
            root = self._parse_source(source)
            text = source.decode("utf-8", errors="replace")
            return self._extract_namespace_map(root, text, init_file.parent)
        except Exception as exc:
            logger.debug("Cannot resolve namespace from %s: %s", init_file, exc)
            return {}

    def extract_internal_calls(
        self, source_code: str, file_path: str
    ) -> list[FunctionCall]:
        """Extract function calls within functions defined in the file."""
        try:
            source = source_code.encode("utf-8")
            root = self._parse_source(source)
            defined = self._collect_defined_functions(root, source_code)
            return self._extract_calls(root, source_code, file_path, defined)
        except Exception as exc:
            logger.debug("Cannot extract calls from %s: %s", file_path, exc)
            return []

    def parse_project(
        self, project_path: Path
    ) -> tuple[list[FlaskEndpoint], list[FunctionCall]]:
        """Parse all Python files in a project directory."""
        init_file = project_path / "__init__.py"
        ns_map = self.resolve_namespace(init_file)  # stem -> path_prefix

        endpoints: list[FlaskEndpoint] = []
        calls: list[FunctionCall] = []

        for py_file in sorted(project_path.rglob("*.py")):
            file_endpoints = self.parse_file(py_file)
            if file_endpoints:
                stem = py_file.stem
                prefix = ns_map.get(stem, "")
                for ep in file_endpoints:
                    ep.full_url = (prefix + ep.route_path) if prefix else ep.route_path
                    ep.namespace = prefix or None
                endpoints.extend(file_endpoints)

            source = py_file.read_text(errors="replace")
            calls.extend(self.extract_internal_calls(source, str(py_file)))

        return endpoints, calls

    # ------------------------------------------------------------------
    # Tree-sitter helpers
    # ------------------------------------------------------------------

    def _node_text(self, node: Node, source: str) -> str:
        return source[node.start_byte:node.end_byte]

    def _extract_endpoints(
        self, root: Node, source: str, file_path: str
    ) -> list[FlaskEndpoint]:
        endpoints: list[FlaskEndpoint] = []

        def visit(node: Node) -> None:
            if node.type == "decorated_definition":
                # Decorators are children of decorated_definition,
                # the actual func/class is a sibling child
                decs = self._get_decorators(node, source)
                inner = None
                for child in node.children:
                    if child.type in ("function_definition", "class_definition"):
                        inner = child
                        break
                if inner and decs:
                    self._process_decorated(inner, decs, file_path, source, endpoints)
            for child in node.children:
                visit(child)

        visit(root)
        return endpoints

    def _process_decorated(
        self, node: Node, decs: list[tuple[str, str, list[str]]],
        file_path: str, source: str, endpoints: list[FlaskEndpoint],
    ) -> None:
        for app_var, route_path, methods in decs:
            if app_var not in FLASK_APP_VARS:
                continue
            name_node = node.child_by_field_name("name")
            func_name = self._node_text(name_node, source) if name_node else "unknown"
            line = node.start_point[0] + 1

            if node.type == "class_definition":
                class_methods = self._get_class_http_methods(node, source)
                for method_name, method_line in class_methods:
                    endpoints.append(FlaskEndpoint(
                        function_name=f"{func_name}.{method_name}",
                        file_path=file_path,
                        line_number=method_line,
                        http_method=method_name.upper(),
                        route_path=route_path,
                        full_url=route_path,
                    ))
            else:
                http_method = (methods[0] if methods else "GET").upper()
                endpoints.append(FlaskEndpoint(
                    function_name=func_name,
                    file_path=file_path,
                    line_number=line,
                    http_method=http_method,
                    route_path=route_path,
                    full_url=route_path,
                ))

    def _get_decorators(
        self, node: Node, source: str
    ) -> list[tuple[str, str, list[str]]]:
        """Return list of (app_var, route_path, methods) for route decorators."""
        results = []
        for child in node.children:
            if child.type != "decorator":
                continue
            dec_text = self._node_text(child, source)
            # Match patterns like @app.route(...) or @api.route(...)
            for var in FLASK_APP_VARS:
                prefix = f"@{var}.route("
                if not dec_text.startswith(prefix):
                    continue
                route_path = self._extract_string_arg(child, source, 0) or "/"
                methods = self._extract_methods_arg(child, source)
                results.append((var, route_path, methods))
        return results

    def _extract_string_arg(self, node: Node, source: str, index: int) -> str | None:
        """Extract the string value of the Nth positional argument in a call."""
        for call in self._find_nodes(node, "call"):
            args_node = call.child_by_field_name("arguments")
            if not args_node:
                continue
            positional = [c for c in args_node.children if c.type not in (",", "(", ")")]
            if index < len(positional):
                raw = self._node_text(positional[index], source).strip("'\"")
                return raw
        return None

    def _extract_methods_arg(self, node: Node, source: str) -> list[str]:
        """Extract the methods=['GET', 'POST'] list from a decorator."""
        dec_text = self._node_text(node, source)
        import re
        m = re.search(r"methods\s*=\s*\[([^\]]*)\]", dec_text)
        if not m:
            return []
        return [s.strip().strip("'\"") for s in m.group(1).split(",") if s.strip()]

    def _get_class_http_methods(
        self, class_node: Node, source: str
    ) -> list[tuple[str, int]]:
        """Get HTTP method handlers (get/post/etc.) from a Resource class."""
        result = []
        body = class_node.child_by_field_name("body")
        if not body:
            return result
        for child in body.children:
            if child.type != "function_definition":
                continue
            name_node = child.child_by_field_name("name")
            if not name_node:
                continue
            name = self._node_text(name_node, source).lower()
            if name in HTTP_METHODS:
                result.append((name, child.start_point[0] + 1))
        return result

    def _extract_namespace_map(
        self, root: Node, source: str, base_dir: Path
    ) -> dict[str, str]:
        """Parse add_namespace() calls and map module stems to path prefixes."""
        import re
        ns_map: dict[str, str] = {}
        # Collect imports: var_name -> module stem
        imports = self._collect_imports(root, source)

        for call in self._find_nodes(root, "call"):
            call_text = self._node_text(call, source)
            m = re.match(r"(\w+)\.add_namespace\(", call_text)
            if not m:
                continue
            args_node = call.child_by_field_name("arguments")
            if not args_node:
                continue
            args = [c for c in args_node.children if c.type not in (",", "(", ")")]
            if not args:
                continue
            ns_var = self._node_text(args[0], source).strip()
            path_match = re.search(r"path\s*=\s*['\"]([^'\"]+)['\"]", call_text)
            if not path_match:
                continue
            path_prefix = path_match.group(1)
            # Resolve ns_var -> module stem via imports
            # imports maps name → parent_module_stem
            # Case 1: `from .pkg.mod import sym` → sym → mod (module_stem=mod)
            # Case 2: `from .pkg import mod` → mod → pkg (module_stem=pkg),
            #         but ns_var IS the module stem, so also try ns_var itself
            module_stem = imports.get(ns_var)
            if module_stem:
                ns_map[module_stem] = path_prefix
            # Also map ns_var directly as module stem (handles Case 2)
            if ns_var != module_stem:
                ns_map[ns_var] = path_prefix
        return ns_map

    def _collect_imports(self, root: Node, source: str) -> dict[str, str]:
        """Return mapping: imported_name -> module stem.

        `from .controllers import user_controller` → user_controller → user_controller
        `from .controllers.user_controller import user_ns` → user_ns → user_controller
        """
        result: dict[str, str] = {}
        for node in self._find_nodes(root, "import_from_statement"):
            text = self._node_text(node, source)
            import re
            m = re.match(r"from\s+([\w.]+)\s+import\s+(.+)", text)
            if not m:
                continue
            module_stem = m.group(1).split(".")[-1]
            names = [n.strip() for n in m.group(2).split(",")]
            for name in names:
                clean = name.strip()
                alias_m = re.match(r"(\w+)\s+as\s+(\w+)", clean)
                if alias_m:
                    result[alias_m.group(2)] = alias_m.group(1)
                else:
                    # Map imported name to the parent module's last segment
                    result[clean] = module_stem
        return result

    def _collect_defined_functions(self, root: Node, source: str) -> set[str]:
        names: set[str] = set()
        for node in self._find_nodes(root, "function_definition"):
            name_node = node.child_by_field_name("name")
            if name_node:
                names.add(self._node_text(name_node, source))
        return names

    def _extract_calls(
        self,
        root: Node,
        source: str,
        file_path: str,
        defined: set[str],
    ) -> list[FunctionCall]:
        calls: list[FunctionCall] = []
        for func_node in self._find_nodes(root, "function_definition"):
            name_node = func_node.child_by_field_name("name")
            if not name_node:
                continue
            caller = self._node_text(name_node, source)
            for call_node in self._find_nodes(func_node, "call"):
                fn_node = call_node.child_by_field_name("function")
                if not fn_node:
                    continue
                callee = self._node_text(fn_node, source).split(".")[-1]
                if callee in defined and callee != caller:
                    calls.append(FunctionCall(
                        caller=caller,
                        callee=callee,
                        file_path=file_path,
                        line_number=call_node.start_point[0] + 1,
                    ))
        return calls

    def _find_nodes(self, root: Node, node_type: str) -> list[Node]:
        result: list[Node] = []
        stack = [root]
        while stack:
            node = stack.pop()
            if node.type == node_type:
                result.append(node)
            stack.extend(reversed(node.children))
        return result
