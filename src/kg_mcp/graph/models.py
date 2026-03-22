"""Data models and enums for the Knowledge Graph."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class NodeType(Enum):
    PROJECT = "Project"
    FILE = "File"
    FUNCTION = "Function"
    FLASK_ENDPOINT = "FlaskEndpoint"
    CONFIG_ENTRY = "ConfigEntry"
    JAVA_TASK = "JavaTask"
    JAVA_TEST = "JavaTest"
    JAVA_QST = "JavaQst"
    JAVA_ENTITY = "JavaEntity"


class EdgeType(Enum):
    DEFINES = "defines"
    HANDLES = "handles"
    CALLS_API = "calls_api"
    TEST_CALLS = "test_calls"
    RESOLVES_TO = "resolves_to"
    USES_ENTITY = "uses_entity"
    CALLED_BY = "called_by"


class FileType(Enum):
    TEST = "Test"
    TASK = "Task"
    QST = "Qst"
    ENTITY = "Entity"
    CONFIG = "Config"


# --- Parser output models ---


@dataclass
class FlaskEndpoint:
    function_name: str
    file_path: str
    line_number: int
    http_method: str
    route_path: str
    full_url: str
    namespace: str | None = None


@dataclass
class MethodInfo:
    name: str
    line_number: int
    calls: list[str] = field(default_factory=list)


@dataclass
class JavaNode:
    class_name: str
    file_path: str
    file_type: FileType
    methods: list[MethodInfo] = field(default_factory=list)


@dataclass
class ConfigReference:
    java_file: str
    config_key: str
    line_number: int


@dataclass
class ResolvedConfig:
    config_key: str
    resolved_url: str
    conf_file: str
    java_file: str
    line_number: int


@dataclass
class FunctionCall:
    caller: str
    callee: str
    file_path: str
    line_number: int


# --- Graph query result models ---


@dataclass
class ImpactStep:
    name: str
    file_path: str
    line_number: int
    edge_type: str


@dataclass
class ImpactChain:
    steps: list[ImpactStep] = field(default_factory=list)


@dataclass
class ImpactSummary:
    total_files: int
    total_projects: int
    max_depth: int


@dataclass
class ImpactResult:
    source_name: str
    source_url: str | None
    source_file: str
    source_line: int
    chains: list[ImpactChain] = field(default_factory=list)
    summary: ImpactSummary = field(
        default_factory=lambda: ImpactSummary(0, 0, 0)
    )


@dataclass
class CallerInfo:
    caller_name: str
    caller_type: str  # Task, Test, Qst
    file_path: str
    line_number: int


@dataclass
class ApiInfo:
    http_method: str
    full_url: str
    function_name: str
    file_path: str
    project: str


@dataclass
class GraphStatus:
    is_built: bool
    node_counts: dict[str, int] | None = None
    edge_counts: dict[str, int] | None = None
    last_build_time: datetime | None = None
    projects: list[str] = field(default_factory=list)
    pickle_size_bytes: int | None = None
    pickle_save_time: datetime | None = None


@dataclass
class BuildResult:
    success: bool
    node_counts: dict[str, int] = field(default_factory=dict)
    edge_counts: dict[str, int] = field(default_factory=dict)
    cross_project_links: int = 0
    build_duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class GraphState:
    """Persisted state for pickle serialization."""
    graph: object  # nx.DiGraph - avoid import here
    version: str
    build_time: datetime
    projects: list[str]
    workspace_path: str
