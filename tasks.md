# Kế hoạch Triển khai: KG Multi-Project MCP

## Tổng quan

Triển khai MCP Server phân tích tác động API xuyên dự án bằng Python. Các bước được sắp xếp theo thứ tự: thiết lập dự án → data models → parsers → graph builder → impact analyzer → formatter → MCP server → tích hợp. Mỗi bước xây dựng trên bước trước, đảm bảo không có code bị treo.

## Tasks

- [ ] 1. Thiết lập cấu trúc dự án và data models
  - [ ] 1.1 Tạo cấu trúc thư mục và pyproject.toml
    - Tạo thư mục `src/kg_mcp/`, `src/kg_mcp/parsers/`, `src/kg_mcp/graph/`, `src/kg_mcp/output/`, `tests/`
    - Tạo tất cả file `__init__.py`
    - Tạo `pyproject.toml` với dependencies: `mcp`, `networkx`, `tree-sitter`, `tree-sitter-python`, `tree-sitter-java`, `pyhocon`, `platformdirs`
    - Khai báo Python 3.10+, entry point cho MCP server, và dev dependencies (`pytest`, `hypothesis`, `pytest-cov`)
    - _Yêu cầu: 9.3, 12.8_

  - [ ] 1.2 Implement data models và enums (`src/kg_mcp/graph/models.py`)
    - Implement `NodeType`, `EdgeType`, `FileType` enums
    - Implement tất cả dataclass: `FlaskEndpoint`, `JavaNode`, `MethodInfo`, `ConfigReference`, `ResolvedConfig`, `FunctionCall`
    - Implement persistence models: `GraphState`, `BuildResult`, `ImpactResult`, `ImpactChain`, `ImpactStep`, `ImpactSummary`, `GraphStatus`, `CallerInfo`, `ApiInfo`
    - _Yêu cầu: 4.2, 4.3_

  - [ ] 1.3 Implement hàm tiện ích cross-platform (`src/kg_mcp/utils.py`)
    - Implement `get_cache_dir()` trả về thư mục cache phù hợp OS (macOS/Linux: `~/.kg-mcp/`, Windows: `%APPDATA%/kg-mcp/`)
    - Implement `normalize_path()` chuyển file path thành relative POSIX format
    - Tất cả file I/O sử dụng `encoding="utf-8"` explicitly
    - _Yêu cầu: 12.1, 12.2, 12.3, 12.7_

  - [ ]* 1.4 Viết property test cho cross-platform path normalization
    - **Property 14: Cross-platform path normalization**
    - Dùng Hypothesis generate random paths với mixed separators (`/` và `\`), kiểm tra `normalize_path()` luôn trả về POSIX format
    - **Validates: Yêu cầu 12.1, 12.2, 12.3, 12.7**

- [ ] 2. Implement Flask Parser
  - [ ] 2.1 Implement `FlaskParser` (`src/kg_mcp/parsers/flask_parser.py`)
    - Implement `__init__` khởi tạo tree-sitter parser với Python grammar
    - Implement `parse_file()` trích xuất endpoint từ decorator `@app.route()`, `@appWT.route()`, `@appWN.route()`, `@api.route()`, `@apiInt.route()` bằng tree-sitter AST
    - Implement `resolve_namespace()` đọc `add_namespace()` từ `__init__.py` và trả về dict namespace → path
    - Implement `parse_project()` quét tất cả file `.py` trong dự án, kết hợp namespace + route → full URL
    - Implement `extract_internal_calls()` trích xuất function call chain từ handler function
    - Bỏ qua file không chứa Flask route decorator mà không tạo lỗi
    - Nếu `__init__.py` không tồn tại hoặc không chứa `add_namespace()`, sử dụng route path làm full URL
    - _Yêu cầu: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 2.2 Viết property test cho Flask route extraction
    - **Property 1: Flask route extraction tạo đầy đủ thông tin**
    - Dùng Hypothesis generate Python source với random route decorators, kiểm tra mỗi FlaskEndpoint chứa đầy đủ: file path, line number, function name, HTTP method, full URL
    - **Validates: Yêu cầu 1.1, 1.3**

  - [ ]* 2.3 Viết property test cho Flask URL resolution
    - **Property 2: Flask URL resolution kết hợp namespace và route**
    - Dùng Hypothesis generate random namespace path + route path pairs, kiểm tra full URL = namespace + route (hoặc chỉ route nếu không có namespace)
    - **Validates: Yêu cầu 1.2, 1.5, 11.1**

  - [ ]* 2.4 Viết property test cho internal function call chain
    - **Property 13: Internal function call chain extraction**
    - Dùng Hypothesis generate Python source với random function calls, kiểm tra Flask_Parser trích xuất đúng danh sách function được gọi
    - **Validates: Yêu cầu 1.6**

- [ ] 3. Implement Java Parser
  - [ ] 3.1 Implement `JavaParser` (`src/kg_mcp/parsers/java_parser.py`)
    - Implement `__init__` khởi tạo tree-sitter parser với Java grammar
    - Implement `classify_file()` phân loại file theo suffix: `*Test.java` → Test, `*Task.java` → Task, `*Qst.java` → Qst, `*Entity.java` → Entity, `None` cho file không khớp
    - Implement `parse_file()` trích xuất class info, method info, và method calls bằng tree-sitter AST
    - Implement `extract_method_calls()` trích xuất method call chain: Test → Task → Qst → Entity
    - Implement `parse_project()` quét tất cả file `.java`, phân loại và parse, trả về `ParseResult`
    - Bỏ qua file không khớp pattern mà không tạo lỗi
    - _Yêu cầu: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 3.2 Viết property test cho Java file classification
    - **Property 3: Java file classification theo suffix**
    - Dùng Hypothesis generate random filenames, kiểm tra `classify_file()` trả về đúng FileType theo suffix
    - **Validates: Yêu cầu 2.1, 2.6**

  - [ ]* 3.3 Viết property test cho Java call chain edges
    - **Property 4: Java call chain extraction tạo đúng edge**
    - Dùng Hypothesis generate Java source với random method calls, kiểm tra đúng edge types được tạo
    - **Validates: Yêu cầu 2.2, 2.3, 2.4, 2.5, 11.5**

- [ ] 4. Implement Config Parser
  - [ ] 4.1 Implement `ConfigParser` (`src/kg_mcp/parsers/config_parser.py`)
    - Implement `parse_hocon()` parse file `.conf` bằng pyhocon → key-value map
    - Implement `parse_java_config()` trích xuất `conf.getString("key")` từ `*Config.java` bằng tree-sitter
    - Implement `resolve_config_to_url()` ánh xạ config key → URL endpoint từ HOCON map
    - Ghi log lỗi nếu HOCON syntax không hợp lệ (tên file + vị trí lỗi), tiếp tục xử lý file còn lại
    - Ghi log cảnh báo nếu config key không tìm thấy trong file `.conf`
    - _Yêu cầu: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 4.2 Viết property test cho HOCON config parsing
    - **Property 5: HOCON config parsing tạo ConfigEntry đầy đủ**
    - Dùng Hypothesis generate random HOCON key-value pairs, kiểm tra ConfigEntry chứa đầy đủ thông tin
    - **Validates: Yêu cầu 3.1, 3.2, 11.2**

  - [ ]* 4.3 Viết property test cho Java config resolution
    - **Property 6: Java config resolution ánh xạ key sang URL**
    - Dùng Hypothesis generate matching Java config + HOCON pairs, kiểm tra key được giải quyết thành URL chính xác
    - **Validates: Yêu cầu 3.3, 11.3**

- [ ] 5. Checkpoint - Kiểm tra parsers
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 6. Implement Graph Builder
  - [ ] 6.1 Implement `GraphBuilder` (`src/kg_mcp/graph/builder.py`)
    - Implement `__init__` khởi tạo NetworkX DiGraph và 3 parser instances
    - Implement `add_flask_endpoints()` tạo node FlaskEndpoint + Function + File + Project và edge defines/handles trong graph
    - Implement `add_java_nodes()` tạo node JavaTask/JavaTest/JavaQst/JavaEntity và edge test_calls/called_by/uses_entity
    - Implement `add_config_entries()` tạo node ConfigEntry và edge resolves_to
    - Implement `link_by_url()` thực hiện URL exact matching giữa FlaskEndpoint full URL và ConfigEntry resolved URL → tạo edge calls_api
    - Implement `build()` orchestrate 3 parser, gọi add methods, gọi link_by_url, trả về BuildResult
    - Implement `save()` serialize GraphState (graph + metadata) bằng pickle
    - Implement `load()` deserialize GraphState từ pickle, kiểm tra version compatibility
    - Trả về thông báo rõ ràng nếu workspace rỗng
    - Nếu pickle bị hỏng hoặc version mismatch, log warning và trả về False
    - _Yêu cầu: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 10.1, 10.3, 10.4, 13.1, 13.4_

  - [ ]* 6.2 Viết property test cho URL exact matching
    - **Property 7: URL exact matching chỉ tạo edge cho URL khớp chính xác**
    - Dùng Hypothesis generate random URL pairs (matching + non-matching), kiểm tra chỉ exact match tạo edge
    - **Validates: Yêu cầu 4.4, 11.4**

  - [ ]* 6.3 Viết property test cho graph serialization round-trip
    - **Property 8: Graph serialization round-trip**
    - Dùng Hypothesis generate random NetworkX DiGraph, kiểm tra serialize → deserialize → serialize tạo kết quả tương đương
    - **Validates: Yêu cầu 4.5, 10.1, 13.1, 13.2, 13.3**

- [ ] 7. Implement Impact Analyzer
  - [ ] 7.1 Implement `ImpactAnalyzer` (`src/kg_mcp/graph/analyzer.py`)
    - Implement `__init__` nhận NetworkX DiGraph
    - Implement `query_impact()` dùng BFS traversal tìm tất cả node reachable từ node nguồn, trả về ImpactResult với impact chains và summary
    - Implement `find_callers()` tìm tất cả caller (JavaTask, JavaTest, JavaQst) có edge trỏ đến API URL
    - Implement `list_apis()` trả về tất cả FlaskEndpoint, nhóm theo project, sắp xếp theo URL alphabetically
    - Implement `suggest_similar()` dùng `difflib.SequenceMatcher` (threshold 0.6) gợi ý tên tương tự khi không tìm thấy
    - Trả về thông báo rõ ràng khi không tìm thấy tác động hoặc function/endpoint không tồn tại
    - _Yêu cầu: 5.1, 5.2, 5.3, 5.4, 6.1, 6.2, 7.1, 7.3_

  - [ ]* 7.2 Viết property test cho impact chain traversal
    - **Property 9: Impact chain traversal tìm tất cả node bị ảnh hưởng**
    - Dùng Hypothesis generate random directed graphs với known reachable sets, kiểm tra query_impact trả về đúng tập node reachable
    - **Validates: Yêu cầu 5.1**

  - [ ]* 7.3 Viết property test cho list_apis ordering
    - **Property 11: list_apis trả về danh sách đúng thứ tự**
    - Dùng Hypothesis generate random endpoint lists, kiểm tra kết quả nhóm theo project và sắp xếp theo URL
    - **Validates: Yêu cầu 6.1, 6.2**

  - [ ]* 7.4 Viết property test cho find_callers completeness
    - **Property 12: find_callers trả về tất cả caller**
    - Dùng Hypothesis generate random graphs với known caller sets, kiểm tra find_callers trả về đúng tập caller
    - **Validates: Yêu cầu 7.1**

- [ ] 8. Implement Compact Formatter
  - [ ] 8.1 Implement `CompactFormatter` (`src/kg_mcp/output/formatter.py`)
    - Implement `format_impact()` format ImpactResult thành compact text: IMPACT header, CHAIN steps, SUMMARY
    - Implement `format_callers()` format danh sách CallerInfo thành compact text
    - Implement `format_api_list()` format danh sách ApiInfo thành compact text nhóm theo project
    - Implement `format_status()` format GraphStatus thành compact text với node/edge counts, build time, projects, pickle info
    - _Yêu cầu: 5.2, 7.2, 8.1, 8.3_

  - [ ]* 8.2 Viết property test cho compact output completeness
    - **Property 10: Compact output chứa đầy đủ thông tin bắt buộc**
    - Dùng Hypothesis generate random result objects, kiểm tra output chứa tất cả trường bắt buộc
    - **Validates: Yêu cầu 5.2, 7.2, 8.1, 8.3**

- [ ] 9. Checkpoint - Kiểm tra core engine
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Implement MCP Server và tích hợp
  - [ ] 10.1 Implement MCP Server (`src/kg_mcp/server.py`)
    - Implement entry point với mcp-python-sdk stdio transport
    - Đăng ký 5 tool: `build_graph`, `query_impact`, `list_apis`, `find_callers`, `graph_status` theo giao thức MCP
    - Tự động load graph state từ pickle khi khởi động (nếu file tồn tại)
    - Kiểm tra graph đã build chưa trước khi xử lý query (trả về thông báo yêu cầu build_graph nếu chưa)
    - Trả về MCP error code chuẩn cho request không hợp lệ
    - Ghi log hoạt động vào stderr
    - Lưu workspace config vào file JSON riêng biệt
    - Hoạt động hoàn toàn local, không gọi API bên ngoài
    - _Yêu cầu: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 10.2, 10.3, 10.4, 6.3, 7.4, 8.2_

  - [ ] 10.2 Tạo test fixtures workspace mẫu
    - Tạo thư mục `tests/fixtures/test_workspace/` với cấu trúc:
      - `python-svc/__init__.py` chứa `add_namespace()` definitions
      - `python-svc/controllers/user_controller.py` chứa `@app.route()` endpoints và internal function calls
      - `java-test/src/test/java/` chứa `UserTest.java`, `UserTask.java`, `UserQst.java`, `UserEntity.java`
      - `java-test/src/main/resources/application.conf` chứa HOCON config
      - `java-test/src/main/java/config/ApiConfig.java` chứa `conf.getString()` references
    - _Yêu cầu: 1.1, 2.1, 3.1, 4.1_

  - [ ] 10.3 Viết integration tests end-to-end
    - Test build graph từ test workspace → kiểm tra node/edge counts đúng
    - Test query_impact → kiểm tra impact chain đầy đủ từ Flask endpoint đến Java files
    - Test list_apis → kiểm tra danh sách endpoint đúng và đúng thứ tự
    - Test find_callers → kiểm tra tìm đúng tất cả caller
    - Test graph_status → kiểm tra thông tin trạng thái đúng
    - Test persistence: save → load → query cho kết quả giống nhau
    - Test error cases: graph chưa build, function không tồn tại, workspace rỗng
    - _Yêu cầu: 4.1, 5.1, 6.1, 7.1, 8.1, 10.1, 10.2_

- [ ] 11. Final checkpoint - Kiểm tra toàn bộ
  - Ensure all tests pass, ask the user if questions arise.

## Ghi chú

- Các task đánh dấu `*` là optional và có thể bỏ qua để triển khai MVP nhanh hơn
- Mỗi task tham chiếu đến yêu cầu cụ thể để đảm bảo traceability
- Checkpoint đảm bảo kiểm tra tăng dần sau mỗi nhóm thành phần
- Property tests kiểm tra thuộc tính phổ quát, unit tests kiểm tra ví dụ cụ thể và edge case
