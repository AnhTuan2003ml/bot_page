# Bot FB — Tổng quan hệ thống, cấu trúc và cách sử dụng

README này mô tả kiến trúc tổng quan của hệ thống Bot Facebook, cách hệ thống xử lý tin nhắn, cách cấu hình Page/Chuyên môn AI/RAG/Data Table, và các nguyên tắc vận hành để tránh trả lời sai ngữ cảnh hoặc làm nghẽn DB.

---

## 1. Mục tiêu hệ thống

Hệ thống dùng để vận hành chatbot cho nhiều Facebook Page, mỗi Page có thể gắn với một **Chuyên môn AI** riêng như:

- Tư vấn biển số
- Tư vấn quần áo
- Tư vấn sản phẩm/dịch vụ khác

Mục tiêu chính:

- Nhận tin nhắn từ Facebook Messenger.
- Xác định Page và skill tương ứng.
- Lọc ý định qua RAG/knowledge của đúng skill.
- Chỉ search bảng dữ liệu khi thật sự cần.
- Trả lời ngắn, đúng ngành, đúng dữ liệu.
- Không tự bịa dữ liệu nếu DB không có.
- Không hỏi tên/xưng hô nếu không cần.
- Giảm đọc/ghi DB bằng cache và buffer.

---

## 2. Runtime flow tổng quát

Flow chuẩn nên là:

```text
Facebook Webhook
→ utils/handlers.py
→ message queue theo page_id + sender_id
→ services/runtime_context.py load Page + Expertise + Config
→ brain/pipeline.py xử lý message
→ parse training_content thành RAG records
→ RAG filter / intent router
→ merge entities với conversation state
→ quyết định có search data_table hay không
→ search structured data nếu cần
→ reply builder theo đúng skill/RAG/data
→ cập nhật state in-memory
→ flush DB định kỳ
→ gửi reply về Messenger
```

Nguyên tắc quan trọng:

```text
Message phải đi qua RAG/knowledge trước.
Không search data_table mặc định cho mọi tin nhắn.
Skill nào dùng đúng RAG/template/data_table của skill đó.
Không fallback chéo ngành.
```

---

## 3. Cấu trúc thư mục chính

```text
.
├── app.py
├── requirements.txt
├── ai_agent/
│   ├── model_client.py
│   └── providers/
│       ├── groq_provider.py
│       ├── openai_provider.py
│       └── ollama_provider.py
├── brain/
│   ├── pipeline.py
│   ├── response_writer.py
│   └── memory.py
├── database/
│   ├── plates.db
│   ├── page_manager.py
│   ├── expertise_manager.py
│   ├── dynamic_table_manager.py
│   ├── conversation_state_manager.py
│   ├── conversation_manager.py
│   ├── config_manager.py
│   └── message_stats_manager.py
├── services/
│   ├── runtime_context.py
│   ├── cache_service.py
│   └── dynamic_data_engine.py
├── utils/
│   ├── handlers.py
│   ├── message_queue.py
│   ├── config_service.py
│   ├── api_logger.py
│   ├── logger.py
│   ├── runtime_paths.py
│   └── security.py
├── web/
│   ├── routes/
│   └── services/
├── templates/
│   └── pages/
└── static/
```

### Vai trò từng nhóm thư mục

| Thành phần | Vai trò |
|---|---|
| `app.py` | Khởi tạo Flask app, webhook Facebook, DB tables, admin blueprint |
| `utils/handlers.py` | Nhận message/postback, lấy Page context, đẩy vào queue, gửi reply |
| `utils/message_queue.py` | Queue đa worker, đảm bảo cùng một khách được xử lý tuần tự |
| `services/runtime_context.py` | Load và cache Page, Expertise, runtime config |
| `brain/pipeline.py` | Trung tâm xử lý AI: intent, RAG, data search, reply, state |
| `ai_agent/` | Gọi model Groq/OpenAI/Ollama theo role intent/writer |
| `database/` | Quản lý SQLite tables: pages, expertises, dynamic data, state, logs |
| `web/routes/` | Route admin UI |
| `web/services/` | Logic cho admin pages/skills/config/logs/stats |
| `templates/` | Giao diện admin |

---

## 4. Các bảng dữ liệu quan trọng

### 4.1. `pages`

Lưu cấu hình từng Facebook Page.

Thông tin thường có:

- `page_id`
- `page_name`
- `page_access_token`
- `verify_token`
- `app_secret`
- `ai_skill`

`ai_skill` dùng để map sang chuyên môn AI trong bảng `expertises`.

Ví dụ:

```text
page_id=1080596045138185
ai_skill=tu_van_quan_ao
```

---

### 4.2. `expertises`

Lưu Chuyên môn AI.

Các field chính:

- `id`
- `key` hoặc skill key, ví dụ `tu_van_quan_ao`
- `name`, ví dụ `tư vấn quần áo`
- `persona_json`
- `training_content`
- `data_table`
- `data_fields_json`

Runtime map:

```text
page_id → pages.ai_skill → expertises → persona_json + training_content + data_table
```

---

### 4.3. `training_content`

Đây là nơi lưu RAG/knowledge/style của từng skill.

Nên lưu dạng JSONL, mỗi dòng là một record:

```jsonl
{"id":"style_sale_clothes_002","title":"Khi khách chào hoặc alo","content":"Khi khách nhắn hi/alo, trả lời: bên e tư vấn quần áo ạ, mình cần tìm áo, quần hay set đồ ạ.","tags":["chao_hoi","alo","quan_ao"]}
```

Nguyên tắc:

- Không nhét một prompt quá dài rồi hy vọng LLM tự chọn.
- Phải parse thành record.
- Retrieve đúng record theo message/tags/intent.
- Chỉ đưa knowledge_hits liên quan vào writer/reply builder.

---

### 4.4. `data_table`

Mỗi skill có thể trỏ tới một bảng dữ liệu nghiệp vụ riêng.

Ví dụ:

- `tu_van_bien_so`: biển số, giá, loại xe, tỉnh, trạng thái.
- `tu_van_quan_ao`: tên sản phẩm, loại, giá, size, màu, chất liệu, tồn kho.

Không hard-code schema. Nên detect field linh hoạt qua `data_fields_json` và tên cột.

---

### 4.5. `conversation_states`

Bảng lưu state ngữ cảnh nghiệp vụ theo từng khách/page/skill:

```sql
CREATE TABLE conversation_states (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id TEXT NOT NULL,
  sender_id TEXT NOT NULL,
  expertise_id INTEGER NOT NULL,
  state_json TEXT NOT NULL DEFAULT '{}',
  UNIQUE(page_id, sender_id, expertise_id)
)
```

Dùng để nhớ context như:

```json
{
  "selected_item": "",
  "selected_plate": "30A-123456",
  "selected_product": "",
  "selected_province": "Hà Nội",
  "product_type": "quần short",
  "vehicle_type": "ô tô",
  "size": "M",
  "color": "đen",
  "budget": "",
  "last_intent": "SEARCH_ITEM",
  "last_results": []
}
```

Không dùng bảng này để lưu:

```json
{
  "customer_name": "Tuấn",
  "pronoun": "anh",
  "gender": "nam"
}
```

State chỉ nên lưu thông tin nghiệp vụ ngắn hạn, giúp xử lý follow-up như:

- “thế xe máy thì sao”
- “giá sao”
- “còn không”
- “màu đen còn không”
- “20tr được không”

---

## 5. RAG / Knowledge flow

### 5.1. Parse RAG

`training_content` nên được parse thành list record:

```json
{
  "id": "style_sale_clothes_002",
  "title": "Khi khách chào hoặc alo",
  "content": "...",
  "tags": ["chao_hoi", "alo", "quan_ao"]
}
```

Nên cache parsed records theo:

```text
rag_records:{expertise_id}:{training_hash}
```

để không parse lại mỗi tin.

---

### 5.2. RAG filter trước intent/search

Với mỗi message:

```text
message
→ normalize
→ retrieve knowledge records
→ infer intent hint
→ decide need_data hint
→ analyzer LLM nếu cần
→ final intent
```

Ví dụ skill quần áo:

```text
hi
→ GREETING
→ knowledge: style_sale_clothes_002
→ no data search
→ reply: bên e tư vấn quần áo ạ, mình cần tìm áo, quần hay set đồ ạ
```

Ví dụ skill biển số:

```text
bên mình có biển Hà Nội không
→ SEARCH_PLATE
→ need_data=true
→ search data_table tu_van_bien_so
```

---

## 6. Intent chuẩn

Nên dùng bộ intent chung, tùy skill map thêm entity riêng.

```text
GREETING
SEARCH_ITEM
SEARCH_PLATE
ASK_PRICE
ASK_STATUS
ASK_STOCK
ASK_SIZE
ASK_COLOR
ASK_MATERIAL
ASK_FORM
ASK_MIX_MATCH
ASK_PROCEDURE
ASK_DISCOUNT
NEGOTIATE_PRICE
ASK_ZALO
ASK_SHIPPING
ASK_RETURN_POLICY
ORDER_INTENT
CONTACT
GENERAL_CHAT
OUT_OF_DOMAIN
UNKNOWN
```

Nguyên tắc:

- `GREETING`: không search data.
- `ASK_PROCEDURE`: không search data nếu chưa có item cụ thể.
- `ASK_DISCOUNT`: không search data nếu chưa có selected item.
- `SEARCH_ITEM`, `ASK_PRICE`, `ASK_STATUS`, `ASK_STOCK`: search data nếu có entity phù hợp.
- `NEGOTIATE_PRICE`: search data nếu có item/plate/product trong message hoặc state.

---

## 7. Reply builder

Reply builder phải dùng đúng skill hiện tại.

### 7.1. Không fallback global sai ngành

Không được dùng fallback kiểu:

```text
bên e tư vấn ạ, cần tìm loại nào hoặc khu vực nào ạ
```

Vì câu này sai cho nhiều skill.

Thay vào đó:

```text
Skill quần áo:
bên e tư vấn quần áo ạ, mình cần tìm áo, quần hay set đồ ạ

Skill biển số:
bên e tư vấn biển số ạ, cần tìm biển tỉnh nào ạ

Skill khác:
bên e hỗ trợ {expertise_name} ạ, mình cần tư vấn nội dung gì ạ
```

### 7.2. Greeting phải ưu tiên RAG

Nếu `knowledge_hits` có `style_sale_clothes_002`, greeting phải lấy câu từ record đó.

Ví dụ:

```text
bên e tư vấn quần áo ạ, mình cần tìm áo, quần hay set đồ ạ
```

Không gọi writer nếu đã có deterministic greeting.

---

## 8. Search data_table

### 8.1. Chỉ search khi cần

Không search data_table với:

```text
GREETING
GENERAL_CHAT
ASK_PROCEDURE nếu chưa có item
ASK_DISCOUNT nếu chưa có item
CONTACT
OUT_OF_DOMAIN
UNKNOWN
```

Search data_table với:

```text
SEARCH_ITEM
SEARCH_PLATE
ASK_PRICE
ASK_STATUS
ASK_STOCK
ASK_COLOR
ASK_SIZE nếu có sản phẩm cụ thể
NEGOTIATE_PRICE nếu có selected item
ORDER_INTENT nếu có item/product
```

---

### 8.2. Structured search trước full-text

Nên search bằng entity có cấu trúc trước:

```json
{
  "product_type": "quần short",
  "size": "M",
  "color": "đen",
  "province": "Hà Nội",
  "vehicle_type": "ô tô",
  "plate": "30A-123456"
}
```

Sau đó mới fallback full-text nếu entity chưa rõ.

---

## 9. Conversation state và follow-up

Ví dụ biển số:

```text
Khách: bên mình có biển Hà Nội không
Bot: 30A-123456 30tr, biển ô tô còn ạ

Khách: thế biển xe máy thì sao
```

Câu sau phải hiểu là:

```text
xe máy + Hà Nội
```

Vì state đang có:

```json
{
  "selected_province": "Hà Nội",
  "vehicle_type": "ô tô",
  "last_results": ["30A-123456"]
}
```

Reply nếu không có xe máy Hà Nội:

```text
hiện bên e chưa thấy biển xe máy Hà Nội ạ
bên e đang có biển ô tô 30A-123456 30tr ạ
```

---

## 10. Cache và giảm đọc DB

Hệ thống nên cache các phần sau:

| Cache key | Nội dung | TTL gợi ý |
|---|---|---:|
| `page:{page_id}` | Cấu hình Page | 5 phút |
| `expertise:{key}` | Expertise/persona/training/data_table | 5 phút |
| `rag_records:{expertise_id}:{hash}` | Parsed RAG records | 10 phút |
| `runtime_config:all` | Runtime config | 5 phút |
| `table_schema:{data_table}` | Schema/data fields | 10 phút |
| `catalog_summary:{expertise_id}:{data_table}` | Danh mục sản phẩm/tổng hợp | 5 phút |
| `data_search:{hash}` | Kết quả search lặp lại | 30-60 giây |

Không nên đọc page/expertise/config từ DB mỗi tin nếu cache còn hiệu lực.

---

## 11. Giảm ghi DB bằng buffer

Không nên ghi state/conversation log vào DB ngay từng message nếu traffic nhiều.

Khuyến nghị:

```text
process message
→ update state in-memory
→ mark dirty
→ flush batch mỗi 5-15 giây
```

### 11.1. State buffer

Key:

```text
(page_id, sender_id, expertise_id)
```

Value:

```json
{
  "state": {},
  "dirty": true,
  "last_updated": "...",
  "last_flushed": "..."
}
```

Flush bằng batch upsert:

```sql
INSERT INTO conversation_states(page_id, sender_id, expertise_id, state_json)
VALUES (?, ?, ?, ?)
ON CONFLICT(page_id, sender_id, expertise_id)
DO UPDATE SET state_json = excluded.state_json;
```

### 11.2. Conversation log buffer

Nếu cần lưu hội thoại, cũng nên buffer:

```text
conversation_log_buffer.append(record)
flush mỗi 5-15 giây hoặc khi >= 50 records
```

Nếu không cần lưu từng message lâu dài, có thể tắt bằng config:

```text
ENABLE_CONVERSATION_DB_LOG=false
```

---

## 12. Không ghi file runtime conversation

Không nên tự tạo:

```text
data/conversations/
data/domains/
data/*.jsonl runtime
```

Trừ khi bật config rõ ràng.

Khuyến nghị config mặc định:

```text
ENABLE_FILE_CONVERSATION_LOG=false
```

Nếu `false`, tuyệt đối không tạo thư mục/file conversation runtime.

---

## 13. SQLite tuning

Nếu dùng SQLite, nên bật:

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=NORMAL;
```

Nguyên tắc:

- Một writer lock cho batch write.
- Không mở quá nhiều connection ghi đồng thời.
- Retry nếu gặp `database is locked`.
- Tránh ghi DB synchronous trong path xử lý message.

---

## 14. Cấu hình model AI

Hệ thống có thể dùng nhiều provider:

- Groq
- OpenAI
- Ollama

Các provider nằm trong:

```text
ai_agent/providers/
```

`ai_agent/model_client.py` chọn model theo role:

- `intent`: phân tích ý định/entity.
- `writer`: viết câu trả lời nếu cần.

Khuyến nghị:

- Greeting, no-data, data reply, negotiation reply nên deterministic, không cần gọi writer.
- Chỉ gọi writer khi cần diễn đạt general chat hoặc tư vấn mềm.
- Không để writer tự bịa sản phẩm/giá/tồn kho nếu không có data rows.

---

## 15. Admin UI

Các trang admin nằm ở:

```text
templates/pages/
web/routes/
web/services/
```

Một số trang chính:

| Trang | Chức năng |
|---|---|
| `/admin/pages` | Quản lý Page Facebook, token, verify token, skill |
| `/admin/skills` | Quản lý Chuyên môn AI |
| `/admin/skill-data` | Quản lý dữ liệu của skill/data_table |
| `/admin/settings` | Runtime config/model/API keys |
| `/admin/api-logs` | Log API incoming/outgoing |
| `/admin/message-stats` | Thống kê tin nhắn |

---

## 16. Cách chạy local

### 16.1. Cài dependency

```bash
pip install -r requirements.txt
```

### 16.2. Chạy app

```bash
python app.py
```

Mặc định app mở admin tại:

```text
http://localhost:5000/admin/pages
```

### 16.3. Kết nối Facebook webhook

Webhook endpoint:

```text
GET  /webhook  dùng verify token
POST /webhook  nhận message event
```

Cần cấu hình trên Facebook Developer:

- Callback URL
- Verify token theo Page
- Page access token
- App secret nếu dùng signature verification

---

## 17. Cách thêm một skill mới

### Bước 1: Tạo Expertise

Trong admin hoặc DB, tạo record:

```json
{
  "key": "tu_van_quan_ao",
  "name": "tư vấn quần áo",
  "persona_json": {},
  "training_content": "JSONL RAG records",
  "data_table": "tu_van_quan_ao",
  "data_fields_json": {}
}
```

### Bước 2: Thêm RAG records

Ví dụ greeting:

```jsonl
{"id":"style_sale_clothes_002","title":"Khi khách chào hoặc alo","content":"Khi khách nhắn hi/alo, trả lời: 'bên e tư vấn quần áo ạ, mình cần tìm áo, quần hay set đồ ạ'.","tags":["chao_hoi","alo","quan_ao"]}
```

### Bước 3: Tạo data_table

Ví dụ bảng quần áo:

```text
id
ten_san_pham
loai
size
mau
gia
chat_lieu
trang_thai
mo_ta
```

### Bước 4: Gắn skill vào Page

Trong `pages.ai_skill`:

```text
tu_van_quan_ao
```

### Bước 5: Clear cache

Sau khi update skill/RAG/config:

```text
clear expertise cache
clear rag_records cache
clear runtime_context/page cache nếu đổi skill
```

---

## 18. Cache invalidation khi admin cập nhật

Khi admin sửa các mục sau:

- `persona_json`
- `training_content`
- `data_table`
- `data_fields_json`
- `page.ai_skill`
- provider/model/config

Cần clear:

```text
expertise:
rag_records:
runtime_context:
page:
catalog_summary:
table_schema:
runtime_config:
```

Log khuyến nghị:

```text
[CACHE_INVALIDATE] expertise_id=2 keys=expertise:,rag_records:,catalog_summary:
```

---

## 19. Test case khuyến nghị

### 19.1. Skill quần áo

```text
User: hi
Expected: bên e tư vấn quần áo ạ, mình cần tìm áo, quần hay set đồ ạ
```

```text
User: bên mình tư vấn sản phẩm gì
Expected: bên e tư vấn và bán quần áo ạ, hỗ trợ chọn mẫu, size, màu, chất liệu và phối đồ ạ
```

```text
User: tôi muốn mua quần short được không
Expected:
- intent=SEARCH_ITEM
- product_type=quần short
- should_search_data=True
- nếu không có data: hiện bên e chưa thấy mẫu quần short phù hợp ạ...
```

```text
User: tôi là nam cao 1m75 nặng 50kg thì áo sơ mi mặc size gì
Expected:
- intent=ASK_SIZE
- tư vấn tham khảo, không cam kết chắc chắn nếu thiếu bảng size
```

### 19.2. Skill biển số

```text
User: hi
Expected: bên e tư vấn biển số ạ, cần tìm biển tỉnh nào ạ
```

```text
User: bên mình có biển Hà Nội không
Expected:
- intent=SEARCH_PLATE
- should_search_data=True
- trả dữ liệu biển Hà Nội nếu có
```

```text
User: thế biển xe máy thì sao
Expected:
- dùng lại selected_province từ state trước đó
- không hỏi lại tỉnh nếu đã biết
```

```text
User: bên e fix giá và hỗ trợ sang tên không
Expected:
- multi-intent ASK_DISCOUNT + ASK_PROCEDURE
- trả đủ 2 ý
```

```text
User: biển này 30A-123457 lấy 20tr nhé
Expected:
- intent=NEGOTIATE_PRICE
- offer_price=20tr
- search row để biết giá gốc
- reply theo rule hỗ trợ giá, không chỉ báo lại data
```

---

## 20. Checklist vận hành

Trước khi chạy thật:

- [ ] Page đã có `page_access_token` đúng.
- [ ] Page đã map đúng `ai_skill`.
- [ ] Expertise có `training_content` JSONL hợp lệ.
- [ ] Expertise có `data_table` đúng nếu cần search dữ liệu.
- [ ] Greeting RAG đúng domain.
- [ ] Không còn fallback chung sai ngành.
- [ ] Không hỏi tên/xưng hô nếu không cần.
- [ ] Không tự tạo `data/conversations` nếu config tắt.
- [ ] Cache invalidation hoạt động khi admin sửa skill.
- [ ] DB write được buffer/batch nếu traffic cao.
- [ ] SQLite bật WAL/busy_timeout nếu dùng SQLite.
- [ ] Không log token/API key ra console/file.

---

## 21. Các lỗi thường gặp và cách kiểm tra

### Lỗi: Greeting vẫn trả “bên e tư vấn ạ...”

Nguyên nhân thường gặp:

- Reply builder đang dùng fallback global.
- RAG hit đúng nhưng build_greeting_reply không lấy content từ knowledge hit.
- Cache RAG/template chưa clear.

Cách kiểm tra log:

```text
rag_intent=GREETING
knowledge_ids=['style_sale_clothes_002']
reply_mode=GREETING_REPLY
```

Nếu log đã hit đúng RAG mà reply sai, lỗi nằm ở reply builder/template fallback.

---

### Lỗi: “tôi muốn mua quần short được không” thành GENERAL_CHAT

Nguyên nhân:

- RAG/intent chưa nhận product keyword.
- Entity schema thiếu `product_type`.
- Normalize chưa xử lý lỗi dính chữ như `đượckhông`.

Cần đảm bảo:

```text
intent=SEARCH_ITEM
entities.product_type=quần short
should_search_data=True
```

---

### Lỗi: “hi” search ra dữ liệu sản phẩm/biển số

Nguyên nhân:

- `should_search_data()` còn return true mặc định khi có data_table.

Cần sửa:

```text
GREETING → should_search_data=False
```

---

### Lỗi: DB bị locked/nghẽn

Nguyên nhân:

- Ghi conversation/state đồng bộ mỗi message.
- Nhiều connection ghi SQLite cùng lúc.

Cách xử lý:

- Buffer state/log.
- Batch flush.
- WAL + busy_timeout.
- Một writer lock cho batch write.

---

## 22. Nguyên tắc bảo mật

Không commit/chia sẻ:

- Page access token
- App secret
- API key Groq/OpenAI
- File DB thật có token

Không log token ra:

- console
- debug log
- API log

Nếu lỡ chia sẻ token thật, cần revoke/rotate ngay.

---

## 23. Tóm tắt kiến trúc đúng

```text
Page
→ ai_skill
→ Expertise đúng skill
→ Parse RAG đúng skill
→ RAG filter trước
→ Intent/entity
→ Merge state nghiệp vụ
→ Search data_table nếu cần
→ Reply builder đúng skill
→ State/log buffer
→ Flush DB định kỳ
```

Không dùng:

```text
fallback global sai ngành
search data_table mọi message
ghi DB/file từng tin nhắn
profile name/pronoun không cần thiết
```
