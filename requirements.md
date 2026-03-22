# Tài liệu Yêu cầu

## Giới thiệu

MCP Server phân tích tác động API xuyên dự án (cross-project API impact analysis) cho workspace đa dự án. Server được xây dựng bằng Python, sử dụng tree-sitter để phân tích AST, NetworkX để xây dựng đồ thị phụ thuộc, và giao tiếp qua giao thức MCP (stdio). Mục tiêu chính là phát hiện cách thay đổi một API/function trong dự án Python Flask ảnh hưởng đến các dự án Java Serenity BDD trong cùng workspace.

## Thuật ngữ

- **MCP_Server**: Server MCP chạy local qua stdio, cung cấp 5 tool cho AI client (VS Code/Kiro/Cursor) để phân tích tác động API xuyên dự án
- **Knowledge_Graph**: Đồ thị có hướng in-memory (NetworkX) chứa các node (Project, File, Function, FlaskEndpoint, ConfigEntry, JavaTask, JavaTest, JavaQst, JavaEntity) và edge (defines, handles, calls_api, test_calls, resolves_to, uses_entity, called_by)
- **Flask_Parser**: Module phân tích mã nguồn Python Flask, trích xuất endpoint từ decorator @app.route(), @appWT.route(), @appWN.route(), @api.route(), @apiInt.route() và giải quyết URL đầy đủ từ add_namespace() trong __init__.py
- **Java_Parser**: Module phân tích mã nguồn Java Serenity BDD, trích xuất chuỗi gọi Test → Task → Qst → Entity
- **Config_Parser**: Module phân tích file cấu hình HOCON (.conf), ánh xạ key-value thành URL endpoint
- **Graph_Builder**: Module xây dựng Knowledge_Graph từ kết quả của Flask_Parser, Java_Parser và Config_Parser, thực hiện URL matching giữa Flask endpoint và Java config
- **Impact_Analyzer**: Module truy vấn Knowledge_Graph để tìm chuỗi tác động (impact chain) từ một function/endpoint đến tất cả các file/function bị ảnh hưởng
- **Impact_Chain**: Chuỗi tác động từ một Flask endpoint đến các file Java liên quan, theo thứ tự: Flask endpoint → Config → Task → Test → Qst → Entity
- **URL_Matcher**: Thành phần so khớp chính xác (exact match) giữa URL đầy đủ của Flask endpoint và URL được giải quyết từ file cấu hình Java
- **Compact_Output**: Định dạng text tối ưu cho LLM context window, không phải JSON

## Yêu cầu

### Yêu cầu 1: Phân tích Flask Route

**User Story:** Là một developer, tôi muốn hệ thống phân tích tất cả Flask endpoint trong dự án Python, để tôi có thể biết được danh sách API đầy đủ với URL đã được giải quyết.

#### Tiêu chí chấp nhận

1. WHEN một dự án Python Flask được quét, THE Flask_Parser SHALL trích xuất tất cả endpoint từ các decorator @app.route(), @appWT.route(), @appWN.route(), @api.route(), @apiInt.route() bằng tree-sitter AST parsing
2. WHEN một endpoint được tìm thấy, THE Flask_Parser SHALL giải quyết URL đầy đủ bằng cách kết hợp path từ add_namespace() trong __init__.py với path trong decorator route
3. WHEN Flask_Parser hoàn thành quét một file, THE Flask_Parser SHALL tạo node FlaskEndpoint trong Knowledge_Graph với thông tin: file path, line number, function name, HTTP method, và full URL
4. IF một file Python không chứa Flask route decorator, THEN THE Flask_Parser SHALL bỏ qua file đó mà không tạo lỗi
5. IF file __init__.py không tồn tại hoặc không chứa add_namespace(), THEN THE Flask_Parser SHALL sử dụng path từ decorator route làm URL đầy đủ
6. THE Flask_Parser SHALL phân tích chuỗi gọi hàm nội bộ (internal function call chain) từ handler function của endpoint đến các function khác trong cùng dự án

### Yêu cầu 2: Phân tích Java Serenity BDD

**User Story:** Là một developer, tôi muốn hệ thống phân tích cấu trúc dự án Java Serenity BDD, để tôi có thể theo dõi chuỗi gọi từ Test đến Entity.

#### Tiêu chí chấp nhận

1. WHEN một dự án Java Serenity BDD được quét, THE Java_Parser SHALL phân tích các file *Test.java, *Task.java, *Qst.java, *Entity.java bằng tree-sitter AST parsing
2. WHEN một file *Task.java được phân tích, THE Java_Parser SHALL trích xuất các method gọi API và liên kết với URL từ constant hoặc config
3. WHEN một file *Test.java được phân tích, THE Java_Parser SHALL trích xuất các method call đến *Task.java và tạo edge test_calls trong Knowledge_Graph
4. WHEN một file *Qst.java được phân tích, THE Java_Parser SHALL trích xuất các method liên quan đến query/validation và tạo edge called_by trong Knowledge_Graph
5. WHEN một file *Entity.java được phân tích, THE Java_Parser SHALL trích xuất thông tin entity và tạo edge uses_entity trong Knowledge_Graph
6. IF một file Java không khớp với pattern *Test.java, *Task.java, *Qst.java, hoặc *Entity.java, THEN THE Java_Parser SHALL bỏ qua file đó mà không tạo lỗi

### Yêu cầu 3: Phân tích file cấu hình HOCON

**User Story:** Là một developer, tôi muốn hệ thống phân tích file cấu hình HOCON để ánh xạ key thành URL endpoint, để tôi có thể liên kết Java config với Flask API.

#### Tiêu chí chấp nhận

1. WHEN một file .conf (HOCON) được quét, THE Config_Parser SHALL phân tích file thành cấu trúc key-value sử dụng thư viện pyhocon
2. WHEN Config_Parser tìm thấy một cặp key-value chứa URL path, THE Config_Parser SHALL tạo node ConfigEntry trong Knowledge_Graph với thông tin: config key, resolved URL, file path, và line number
3. WHEN một file *Config.java chứa lời gọi conf.getString("key"), THE Config_Parser SHALL giải quyết key thành URL tương ứng từ file .conf và tạo edge resolves_to trong Knowledge_Graph
4. IF file .conf có cú pháp không hợp lệ, THEN THE Config_Parser SHALL ghi log lỗi với tên file và vị trí lỗi, sau đó tiếp tục xử lý các file còn lại
5. IF một config key không tìm thấy trong file .conf, THEN THE Config_Parser SHALL ghi log cảnh báo với tên key và file Java tham chiếu

### Yêu cầu 4: Xây dựng Knowledge Graph

**User Story:** Là một developer, tôi muốn hệ thống xây dựng đồ thị phụ thuộc xuyên dự án, để tôi có thể truy vấn mối quan hệ giữa các thành phần.

#### Tiêu chí chấp nhận

1. WHEN tool build_graph được gọi, THE Graph_Builder SHALL quét tất cả dự án trong workspace và xây dựng Knowledge_Graph hoàn chỉnh
2. THE Knowledge_Graph SHALL chứa các loại node: Project, File, Function, FlaskEndpoint, ConfigEntry, JavaTask, JavaTest, JavaQst, JavaEntity
3. THE Knowledge_Graph SHALL chứa các loại edge: defines, handles, calls_api, test_calls, resolves_to, uses_entity, called_by
4. WHEN Graph_Builder hoàn thành xây dựng, THE Graph_Builder SHALL thực hiện URL matching chính xác (exact match) giữa FlaskEndpoint full URL và ConfigEntry resolved URL để tạo edge calls_api
5. WHEN Knowledge_Graph được xây dựng xong, THE Graph_Builder SHALL lưu trữ graph state bằng pickle để có thể tải lại mà không cần quét lại
6. IF workspace không chứa dự án nào, THEN THE Graph_Builder SHALL trả về thông báo rõ ràng cho biết không tìm thấy dự án
7. THE Graph_Builder SHALL xử lý workspace chứa 2-3 dự án với hàng trăm đến hàng nghìn file mỗi dự án trong thời gian hợp lý

### Yêu cầu 5: Truy vấn tác động (Impact Query)

**User Story:** Là một developer, tôi muốn truy vấn tác động của một function/endpoint đến các dự án khác, để tôi có thể đánh giá phạm vi ảnh hưởng trước khi thay đổi code.

#### Tiêu chí chấp nhận

1. WHEN tool query_impact được gọi với tên function hoặc endpoint URL, THE Impact_Analyzer SHALL trả về Impact_Chain đầy đủ từ endpoint đến tất cả file/function bị ảnh hưởng
2. THE Impact_Analyzer SHALL trả về kết quả dạng Compact_Output tối ưu cho LLM context window, bao gồm: tên function, URL, file path, line number, loại quan hệ, và summary (số file, số project, max depth)
3. WHEN không tìm thấy tác động nào, THE Impact_Analyzer SHALL trả về thông báo rõ ràng cho biết không có file nào bị ảnh hưởng
4. IF function/endpoint không tồn tại trong Knowledge_Graph, THEN THE Impact_Analyzer SHALL trả về thông báo lỗi kèm gợi ý các function/endpoint tương tự (nếu có)

### Yêu cầu 6: Liệt kê API (List APIs)

**User Story:** Là một developer, tôi muốn xem danh sách tất cả Flask endpoint trong workspace, để tôi có cái nhìn tổng quan về các API hiện có.

#### Tiêu chí chấp nhận

1. WHEN tool list_apis được gọi, THE MCP_Server SHALL trả về danh sách tất cả FlaskEndpoint trong Knowledge_Graph, bao gồm: HTTP method, full URL, function name, và file path
2. THE MCP_Server SHALL nhóm kết quả theo dự án và sắp xếp theo URL alphabetically
3. IF Knowledge_Graph chưa được xây dựng, THEN THE MCP_Server SHALL trả về thông báo yêu cầu chạy build_graph trước

### Yêu cầu 7: Tìm caller của API (Find Callers)

**User Story:** Là một developer, tôi muốn tìm tất cả nơi gọi đến một API cụ thể, để tôi biết được phạm vi sử dụng của API đó.

#### Tiêu chí chấp nhận

1. WHEN tool find_callers được gọi với URL hoặc tên endpoint, THE Impact_Analyzer SHALL trả về danh sách tất cả caller (JavaTask, JavaTest, JavaQst) gọi đến API đó
2. THE Impact_Analyzer SHALL trả về kết quả dạng Compact_Output bao gồm: caller function name, file path, line number, và loại caller (Task/Test/Qst)
3. IF API không tồn tại trong Knowledge_Graph, THEN THE Impact_Analyzer SHALL trả về thông báo lỗi kèm gợi ý các API tương tự (nếu có)
4. IF Knowledge_Graph chưa được xây dựng, THEN THE MCP_Server SHALL trả về thông báo yêu cầu chạy build_graph trước

### Yêu cầu 8: Kiểm tra trạng thái Graph (Graph Status)

**User Story:** Là một developer, tôi muốn kiểm tra trạng thái hiện tại của Knowledge Graph, để tôi biết graph đã được xây dựng chưa và chứa bao nhiêu dữ liệu.

#### Tiêu chí chấp nhận

1. WHEN tool graph_status được gọi, THE MCP_Server SHALL trả về thông tin: số lượng node theo từng loại, số lượng edge theo từng loại, thời gian build gần nhất, và danh sách dự án đã quét
2. IF Knowledge_Graph chưa được xây dựng, THEN THE MCP_Server SHALL trả về trạng thái "not_built" kèm hướng dẫn chạy build_graph
3. WHEN graph đã được lưu bằng pickle, THE MCP_Server SHALL hiển thị kích thước file pickle và thời gian lưu

### Yêu cầu 9: MCP Server và Transport

**User Story:** Là một developer, tôi muốn MCP server hoạt động qua stdio transport, để AI client có thể tự động quản lý server mà không cần cấu hình phức tạp.

#### Tiêu chí chấp nhận

1. THE MCP_Server SHALL giao tiếp qua stdio transport sử dụng mcp-python-sdk
2. THE MCP_Server SHALL đăng ký 5 tool: build_graph, query_impact, list_apis, find_callers, graph_status theo đúng giao thức MCP
3. THE MCP_Server SHALL cài đặt được qua pip install và cấu hình qua file mcp.json
4. THE MCP_Server SHALL hoạt động hoàn toàn local, không thực hiện bất kỳ lời gọi API bên ngoài nào
5. IF MCP_Server nhận được request không hợp lệ, THEN THE MCP_Server SHALL trả về mã lỗi MCP chuẩn kèm thông báo mô tả lỗi
6. THE MCP_Server SHALL ghi log hoạt động vào stderr để không ảnh hưởng đến giao tiếp stdio

### Yêu cầu 10: Persistence và khôi phục trạng thái

**User Story:** Là một developer, tôi muốn Knowledge Graph được lưu trữ và khôi phục giữa các phiên làm việc, để tôi không phải build lại graph mỗi lần khởi động server.

#### Tiêu chí chấp nhận

1. WHEN Knowledge_Graph được xây dựng xong, THE Graph_Builder SHALL tự động lưu graph state vào file pickle
2. WHEN MCP_Server khởi động, THE MCP_Server SHALL tự động tải graph state từ file pickle nếu file tồn tại
3. IF file pickle bị hỏng hoặc không tương thích, THEN THE MCP_Server SHALL ghi log cảnh báo và khởi động với graph rỗng
4. THE MCP_Server SHALL lưu cấu hình workspace (danh sách dự án, đường dẫn) vào file JSON riêng biệt

### Yêu cầu 11: Chuỗi giải quyết URL (URL Resolution Chain)

**User Story:** Là một developer, tôi muốn hệ thống giải quyết URL đầy đủ qua 5 bước, để đảm bảo matching chính xác giữa Flask endpoint và Java config.

#### Tiêu chí chấp nhận

1. THE Flask_Parser SHALL giải quyết Flask route bằng cách kết hợp: namespace path từ add_namespace() + route path từ decorator → full URL
2. THE Config_Parser SHALL giải quyết HOCON config bằng cách: đọc file .conf → tạo key-value map với URL path
3. THE Config_Parser SHALL giải quyết Java Config → Constant bằng cách: trích xuất conf.getString("key") → ánh xạ sang URL từ bước 2
4. THE URL_Matcher SHALL thực hiện exact match giữa Flask full URL và Java config resolved URL để tạo liên kết xuyên dự án
5. THE Java_Parser SHALL giải quyết chuỗi gọi Java: Test → Task → Qst → Entity bằng cách phân tích method call trong từng file

### Yêu cầu 12: Tương thích đa nền tảng (Cross-Platform Compatibility)

**User Story:** Là một developer, tôi muốn MCP server hoạt động trên Windows, macOS, và Linux, và tương thích với các phiên bản Kiro cũ cũng như các AI client khác, để tôi có thể sử dụng trên bất kỳ môi trường nào.

#### Tiêu chí chấp nhận

1. THE MCP_Server SHALL hoạt động trên Windows, macOS, và Linux mà không cần thay đổi cấu hình
2. THE MCP_Server SHALL sử dụng pathlib.Path thay vì string concatenation cho tất cả đường dẫn file, đảm bảo xử lý đúng path separator trên mọi OS
3. THE MCP_Server SHALL lưu cache tại thư mục phù hợp với từng OS: `~/.kg-mcp/` trên macOS/Linux, `%APPDATA%/kg-mcp/` trên Windows
4. THE MCP_Server SHALL tương thích với Kiro (tất cả phiên bản hỗ trợ MCP), VS Code + Copilot, Cursor, và Claude CLI
5. THE MCP_Server SHALL sử dụng mcp-python-sdk phiên bản ổn định (không dùng pre-release) để đảm bảo tương thích ngược
6. IF tree-sitter grammar không khả dụng trên một nền tảng, THEN THE MCP_Server SHALL ghi log lỗi rõ ràng với hướng dẫn cài đặt cho nền tảng đó
7. THE MCP_Server SHALL xử lý encoding UTF-8 cho tất cả file I/O, đảm bảo đọc được source code chứa ký tự Unicode trên mọi OS
8. THE pyproject.toml SHALL khai báo rõ ràng các nền tảng được hỗ trợ (Windows, macOS, Linux) và phiên bản Python tối thiểu (3.10+)

### Yêu cầu 13: Serialization đồ thị

**User Story:** Là một developer, tôi muốn đồ thị được serialize/deserialize chính xác, để dữ liệu không bị mất giữa các phiên làm việc.

#### Tiêu chí chấp nhận

1. THE Graph_Builder SHALL serialize Knowledge_Graph thành file pickle bao gồm tất cả node, edge, và metadata
2. THE Graph_Builder SHALL deserialize file pickle thành Knowledge_Graph với đầy đủ node, edge, và metadata giống hệt trước khi serialize
3. FOR ALL Knowledge_Graph hợp lệ, serialize rồi deserialize rồi serialize SHALL tạo ra kết quả tương đương với lần serialize đầu tiên (round-trip property)
4. IF file pickle được tạo bởi phiên bản cũ hơn của MCP_Server, THEN THE Graph_Builder SHALL phát hiện sự không tương thích và yêu cầu build lại graph
