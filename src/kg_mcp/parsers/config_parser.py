"""Parse HOCON config files and Java *Config.java files to resolve config keys to URLs."""

import logging
from pathlib import Path

import tree_sitter_java as tsjava
from pyhocon import ConfigException, ConfigFactory
from tree_sitter import Language, Parser

from kg_mcp.graph.models import ConfigReference, ResolvedConfig

logger = logging.getLogger(__name__)

JAVA_LANGUAGE = Language(tsjava.language())


def _flatten_hocon(config, prefix: str = "") -> dict[str, str]:
    """Recursively flatten a nested HOCON ConfigTree into dot-separated key-value pairs."""
    result: dict[str, str] = {}
    for key, value in config.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if hasattr(value, "items"):
            result.update(_flatten_hocon(value, full_key))
        else:
            result[full_key] = str(value)
    return result


def _walk_nodes(node, node_type: str):
    """Yield all descendant nodes matching node_type."""
    if node.type == node_type:
        yield node
    for child in node.children:
        yield from _walk_nodes(child, node_type)


class ConfigParser:
    def __init__(self) -> None:
        self._parser = Parser(JAVA_LANGUAGE)

    def parse_hocon(self, conf_path: Path) -> dict[str, str]:
        """Parse a HOCON .conf file and return flattened key → value map."""
        try:
            config = ConfigFactory.parse_file(str(conf_path))
            return _flatten_hocon(config)
        except ConfigException as exc:
            logger.error("Invalid HOCON syntax in %s: %s", conf_path, exc)
            return {}
        except Exception as exc:
            logger.error("Failed to parse HOCON file %s: %s", conf_path, exc)
            return {}

    def parse_java_config(self, java_file: Path) -> list[ConfigReference]:
        """Extract conf.getString(\"key\") calls from a Java *Config.java file."""
        try:
            source = java_file.read_bytes()
        except OSError as exc:
            logger.error("Cannot read Java file %s: %s", java_file, exc)
            return []

        tree = self._parser.parse(source)
        references: list[ConfigReference] = []

        for node in _walk_nodes(tree.root_node, "method_invocation"):
            children = node.children
            # Expect: identifier(conf) . identifier(getString) argument_list
            if len(children) < 4:
                continue
            receiver = children[0]
            method = children[2]
            arg_list = children[3]

            if (
                receiver.type != "identifier"
                or receiver.text != b"conf"
                or method.type != "identifier"
                or method.text != b"getString"
            ):
                continue

            # Extract first string literal from argument_list
            string_node = next(
                (n for n in _walk_nodes(arg_list, "string_literal")), None
            )
            if string_node is None:
                continue

            raw = string_node.text.decode("utf-8", errors="replace")
            config_key = raw.strip('"').strip("'")
            line_number = node.start_point[0] + 1  # 1-based

            references.append(
                ConfigReference(
                    java_file=str(java_file),
                    config_key=config_key,
                    line_number=line_number,
                )
            )

        return references

    def resolve_config_to_url(
        self,
        references: list[ConfigReference],
        hocon_map: dict[str, str],
    ) -> list[ResolvedConfig]:
        """Resolve each ConfigReference to a URL via the HOCON map."""
        resolved: list[ResolvedConfig] = []
        for ref in references:
            url = hocon_map.get(ref.config_key)
            if url is None:
                logger.warning(
                    "Config key '%s' not found in .conf file (referenced in %s:%d)",
                    ref.config_key,
                    ref.java_file,
                    ref.line_number,
                )
                continue
            resolved.append(
                ResolvedConfig(
                    config_key=ref.config_key,
                    resolved_url=url,
                    conf_file="",  # filled by caller with actual conf path
                    java_file=ref.java_file,
                    line_number=ref.line_number,
                )
            )
        return resolved

    def parse_project_configs(
        self, project_path: Path
    ) -> tuple[dict[str, str], list[ResolvedConfig]]:
        """Parse all .conf and *Config.java files under project_path.

        Returns:
            (hocon_map, resolved_configs) where hocon_map is the merged flattened
            HOCON map from all .conf files found in the project.
        """
        hocon_map: dict[str, str] = {}
        conf_file_map: dict[str, str] = {}  # key → source conf file path

        for conf_path in project_path.rglob("*.conf"):
            partial = self.parse_hocon(conf_path)
            for key, value in partial.items():
                hocon_map[key] = value
                conf_file_map[key] = str(conf_path)

        all_references: list[ConfigReference] = []
        for java_path in project_path.rglob("*Config.java"):
            all_references.extend(self.parse_java_config(java_path))

        resolved: list[ResolvedConfig] = []
        for ref in all_references:
            url = hocon_map.get(ref.config_key)
            if url is None:
                logger.warning(
                    "Config key '%s' not found in any .conf file (referenced in %s:%d)",
                    ref.config_key,
                    ref.java_file,
                    ref.line_number,
                )
                continue
            resolved.append(
                ResolvedConfig(
                    config_key=ref.config_key,
                    resolved_url=url,
                    conf_file=conf_file_map.get(ref.config_key, ""),
                    java_file=ref.java_file,
                    line_number=ref.line_number,
                )
            )

        return hocon_map, resolved
