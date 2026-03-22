# KG Multi-Project MCP Server

MCP Server phân tích tác động API xuyên dự án (cross-project API impact analysis) cho workspace đa dự án. Xây dựng Knowledge Graph từ source code, cho phép AI client truy vấn: "Nếu tôi sửa API này, những file nào bị ảnh hưởng?"

## Tính năng

- **Phân tích Flask Route** — Trích xuất endpoint từ decorator `@app.route()`, `@api.route()`, v.v. bằng tree-sitter AST
- **Phân tích Java Serenity BDD** — Trích xuất chuỗi gọi Test → Task → Qst → Entity
- **Phân tích HOCON Config** — Ánh xạ config key → URL endpoint
- **Knowledge Graph** — Đồ thị có hướng in-memory (NetworkX) với URL exact matching xuyên dự án
- **Impact Analysis** — BFS traversal tìm tất cả file/function bị ảnh hưởng khi thay đổi 1 API
- **Compact Output** — Định dạng text tối ưu cho LLM context window

## Ngôn ngữ hỗ trợ

| Ngôn ngữ | Vai trò | Parser |
|----------|---------|--------|
| **Python** (Flask/Flask-RESTx) | API source | tree-sitter-python |
| **Java** (Serenity BDD) | Test consumer | tree-sitter-java |
| **HOCON** (.conf) | Config bridge | pyhocon |

> Hiện tại hỗ trợ workspace gồm Python Flask + Java Serenity BDD. Xem phần [Mở rộng ngôn ngữ](#mở-rộng-ngôn-ngữ) để thêm ngôn ngữ mới.

## Cài đặt

### Yêu cầu
- Python 3.10+
- macOS / Linux / Windows

### Từ source

```bash
git clone <repo-url>
cd ExtensionKGMultiProject
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows
pip install -e ".[dev]"
```

### Xác nhận cài đặt

```bash
kg-mcp --help
python -m pytest tests/ -v   # 77 tests
```

## Cấu hình MCP Client

Thêm vào file cấu hình MCP của client bạn dùng:

```json
{
  "mcpServers": {
    "kg-mcp": {
      "command": "/đường-dẫn-tuyệt-đối/.venv/bin/kg-mcp"
    }
  }
}
```

| Client | File cấu hình |
|--------|---------------|
| Kiro | `.kiro/settings/mcp.json` |
| VS Code + Copilot | `.vscode/mcp.json` |
| Cursor | `.cursor/mcp.json` |
| Claude CLI | `~/.claude/mcp.json` |

## 5 MCP Tools

| Tool | Mô tả |
|------|--------|
| `build_graph(workspace_path)` | Quét workspace, xây dựng Knowledge Graph |
| `query_impact(name)` | Truy vấn chuỗi tác động từ function/endpoint |
| `list_apis(project?)` | Liệt kê tất cả Flask endpoint |
| `find_callers(api_url)` | Tìm tất cả caller gọi đến 1 API |
| `graph_status()` | Kiểm tra trạng thái graph |

## Ví dụ

```
> build_graph(workspace_path="/path/to/workspace")
BUILD OK | 0.1s
nodes: FlaskEndpoint=10 JavaTest=3 JavaTask=3 ConfigEntry=10
xlinks: 10

> query_impact(name="GetUser.get")
IMPACT: GetUser.get() → /api/v1/user/get_user
  src: python-svc/controllers/user_controller.py:25
CHAIN:
  → java-test/src/main/java/config/ApiConfig.java:10 user.getUser [calls_api]
  → java-test/src/test/java/tasks/UserTask.java:0 UserTask [resolves_to]
  → java-test/src/test/java/tests/UserTest.java:0 UserTest [test_calls]
SUMMARY: 4 files | 2 projects | depth=4

> find_callers(api_url="/api/v1/user/get_user")
CALLERS: /api/v1/user/get_user | 2 callers
  [Task] UserTask  java-test/src/test/java/tasks/UserTask.java:0
  [Test] UserTest  java-test/src/test/java/tests/UserTest.java:0
```

## Cấu trúc dự án

```
src/kg_mcp/
├── server.py              # MCP Server entry point (stdio)
├── utils.py               # Cross-platform utilities
├── parsers/
│   ├── flask_parser.py    # Flask route parser (tree-sitter)
│   ├── java_parser.py     # Java Serenity BDD parser (tree-sitter)
│   └── config_parser.py   # HOCON config parser (pyhocon)
├── graph/
│   ├── models.py          # Data models + enums
│   ├── builder.py         # Graph builder + persistence
│   └── analyzer.py        # Impact analyzer + queries
└── output/
    └── formatter.py       # Compact text formatter
```

## Hướng dẫn phát triển

### Setup môi trường dev

```bash
git clone <repo-url>
cd ExtensionKGMultiProject
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Chạy tests

```bash
# Tất cả tests
python -m pytest tests/ -v

# Với coverage
python -m pytest tests/ --cov=kg_mcp --cov-report=term-missing

# Chỉ property tests
python -m pytest tests/test_properties.py -v
```

### Kiến trúc tầng

```
AI Client (stdio) → MCP Server → Tool Registry
                                    ├── Graph Builder → Parsers (Flask/Java/Config)
                                    ├── Impact Analyzer → NetworkX DiGraph
                                    └── Compact Formatter
```

### Thêm parser mới

1. Tạo file `src/kg_mcp/parsers/your_parser.py`
2. Implement interface: `parse_file()`, `parse_project()`
3. Thêm node type vào `graph/models.py`
4. Tích hợp vào `graph/builder.py` trong method `build()`
5. Viết tests trong `tests/`

### Mở rộng ngôn ngữ

Hệ thống có thể mở rộng cho các ngôn ngữ/framework khác:

| Ngôn ngữ | Framework | Cần implement |
|----------|-----------|---------------|
| TypeScript | Express/NestJS | Thêm `ts_parser.py` + tree-sitter-typescript |
| Go | Gin/Echo | Thêm `go_parser.py` + tree-sitter-go |
| C# | ASP.NET | Thêm `csharp_parser.py` + tree-sitter-c-sharp |
| Ruby | Rails | Thêm `ruby_parser.py` + tree-sitter-ruby |
| Kotlin | Spring Boot | Thêm `kotlin_parser.py` + tree-sitter-kotlin |

Mỗi parser cần:
- Trích xuất API endpoint (route/controller)
- Trích xuất function call chain
- Trả về dataclass tương thích với `GraphBuilder`

### Quy ước

- File naming: snake_case (Python convention)
- Mỗi file source < 200 dòng
- Log ra stderr (không ảnh hưởng stdio transport)
- Tất cả path dùng `pathlib.Path`, không string concatenation
- File I/O luôn `encoding="utf-8"`

## Tech Stack

| Component | Thư viện |
|-----------|---------|
| AST Parsing | tree-sitter, tree-sitter-python, tree-sitter-java |
| Config Parsing | pyhocon |
| Graph Engine | NetworkX |
| Persistence | pickle |
| MCP Protocol | mcp-python-sdk (stdio) |
| Testing | pytest, hypothesis, pytest-cov |

## License

MIT
