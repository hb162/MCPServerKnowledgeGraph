# KG Multi-Project MCP — Hướng Dẫn Sử Dụng

## Cài Đặt

### 1. Cài từ source

```bash
cd /path/to/ExtensionKGMultiProject
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate    # Windows
pip install -e ".[dev]"
```

### 2. Chạy MCP server

```bash
kg-mcp   # hoặc: python -m kg_mcp.server
```

Server giao tiếp qua **stdio** — không cần mở port.

## Cấu Hình MCP Client

### Claude CLI (`~/.claude/mcp.json`)

```json
{
  "mcpServers": {
    "kg-mcp": {
      "command": "/path/to/.venv/bin/kg-mcp",
      "args": []
    }
  }
}
```

### VS Code + Copilot (`.vscode/mcp.json`)

```json
{
  "servers": {
    "kg-mcp": {
      "command": "/path/to/.venv/bin/kg-mcp",
      "args": []
    }
  }
}
```

### Cursor (`.cursor/mcp.json`)

```json
{
  "mcpServers": {
    "kg-mcp": {
      "command": "/path/to/.venv/bin/kg-mcp",
      "args": []
    }
  }
}
```

### Kiro (`.kiro/settings/mcp.json`)

```json
{
  "mcpServers": {
    "kg-mcp": {
      "command": "/path/to/.venv/bin/kg-mcp",
      "args": []
    }
  }
}
```

> **Lưu ý:** Thay `/path/to/.venv/bin/kg-mcp` bằng đường dẫn tuyệt đối đến file `kg-mcp` trong virtual environment.

## 5 Tools

| Tool | Mô tả | Tham số |
|------|--------|---------|
| `build_graph` | Quét workspace, xây dựng Knowledge Graph | `workspace_path: str` |
| `query_impact` | Truy vấn chuỗi tác động từ function/endpoint | `name: str`, `max_depth: int = 10` |
| `list_apis` | Liệt kê tất cả Flask endpoint | `project: str \| None` |
| `find_callers` | Tìm tất cả caller gọi đến 1 API | `api_url: str` |
| `graph_status` | Kiểm tra trạng thái graph | (không có) |

## Ví Dụ Sử Dụng

### Build graph

```
> build_graph(workspace_path="/Users/hoang/Desktop/sample-workspace")

BUILD OK | 0.1s
nodes: FlaskEndpoint=10 JavaTest=3 JavaTask=3 ConfigEntry=10 ...
xlinks: 10
projects: python-svc java-test
```

### Query impact

```
> query_impact(name="GetUser.get")

IMPACT: GetUser.get() → /api/v1/user/get_user
  src: python-svc/controllers/user_controller.py:25
CHAIN:
  → java-test/src/main/java/config/ApiConfig.java:8 user.getUser [calls_api]
  → java-test/src/test/java/tasks/UserTask.java:12 callGetUser() [resolves_to]
  → java-test/src/test/java/tests/UserTest.java:25 testGetUser() [test_calls]
SUMMARY: 4 files | 2 projects | depth=3
```

### List APIs

```
> list_apis()

APIS: 10 endpoints | 1 projects
[python-svc]
  GET   /api/v1/risk/get_risk               GetRisk.get()
  POST  /api/v1/user/create_user            CreateUser.post()
  ...
```

### Find callers

```
> find_callers(api_url="/api/v1/user/get_user")

CALLERS: /api/v1/user/get_user | 2 callers
  [Task] UserTask  java-test/src/test/java/tasks/UserTask.java:0
  [Test] UserTest  java-test/src/test/java/tests/UserTest.java:0
```

## Workspace Mẫu

Một sample workspace đã được tạo tại `~/Desktop/sample-workspace/` với:

- **python-svc**: 3 controller (user, risk, transaction) → 10 endpoints
- **java-test**: Test/Task/Qst/Entity cho mỗi domain + HOCON config

Xem file `~/Desktop/sample-workspace/agents.md` để biết hướng dẫn cho AI agent.

## Output Format

Tất cả output là **compact text** (không phải JSON) — tối ưu cho LLM context window:

- Mỗi dòng mang 1 ý nghĩa
- Dễ parse bằng regex hoặc split
- Tiết kiệm token

## Persistence

- Graph được lưu tự động tại `~/.kg-mcp/graph.pkl` sau mỗi lần build
- Khi server khởi động, tự động load graph từ pickle (nếu có)
- Workspace config lưu tại `~/.kg-mcp/workspace.json`

## Xử Lý Lỗi

| Tình huống | Hành vi |
|------------|---------|
| File Python syntax error | Log warning, bỏ qua, tiếp tục |
| File HOCON lỗi | Log error với vị trí, tiếp tục |
| Config key không tìm thấy | Log warning |
| Function/endpoint không tồn tại | Trả về gợi ý tên tương tự |
| Graph chưa build | Trả về hướng dẫn gọi build_graph |
| Pickle bị hỏng | Log warning, khởi động graph rỗng |

## Chạy Tests

```bash
# Unit + property tests
python -m pytest tests/ -v

# Với coverage
python -m pytest tests/ --cov=kg_mcp --cov-report=term-missing

# Chỉ property tests
python -m pytest tests/test_properties.py -v
```

## Yêu Cầu Hệ Thống

- Python 3.10+
- macOS / Linux / Windows
- Không cần internet (hoàn toàn local)
