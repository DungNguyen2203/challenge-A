# Challenge A: persistent memory

Bài này làm một agent nhớ được quy ước của dự án qua nhiều session, và khi quy ước đổi thì các session sau dùng quy ước mới. Code nằm hết trong `agent.py`.

## Thiết kế

Mình trả lời lần lượt mấy câu gợi ý trong slide:

| Câu hỏi | Cách làm |
|---|---|
| Lưu ở đâu? | File `memory.json`. Mỗi entry có `key`, `value`, `status` (active / superseded / forgotten), `source_session`, `created_at`, `superseded_by`, `superseded_at` |
| Ai ghi? | Agent tự gọi tool `remember(key, value)` hoặc `forget(key)` |
| Khi nào nạp? | Lúc mở session, các entry active được đưa vào system prompt trong khối `<project_memory>` |
| Quy ước đổi thì sao? | Entry cũ cùng `key` được chuyển sang `superseded`, vẫn giữ nguồn và thời điểm. Mỗi key chỉ có 1 entry active |
| Kiểm chứng thế nào? | Session nào cũng in khối `[INJECTED MEMORY]` ra trước khi gọi LLM |

Trong khối inject mình có ghi kèm key, và phần mô tả tool dặn model dùng lại key cũ khi đổi quy ước. Nếu không làm vậy, model dễ tạo key mới (ví dụ `db` thay vì `database`), và khi đó memory sẽ có hai quy ước cùng active.

## Cách chạy

```bash
python -m pip install openai
```

```bash
python agent.py --selftest
```

Lệnh này kiểm tra phần lưu memory và phần inject, không cần API key.

```bash
python agent.py --demo
```

Demo gọi DeepSeek (model `deepseek-flash`, qua API tương thích OpenAI), nên cần key. Tạo file `.env` cạnh `agent.py` với một dòng `DEEPSEEK_API_KEY=sk-...`. File `.env` đã có trong `.gitignore` nên không bị đẩy lên repo.

Demo chạy 4 process riêng, giữa các process chỉ có `memory.json` là dùng chung:

1. S1 chốt quy ước: PostgreSQL, TypeScript, route kebab-case số nhiều, auth bằng JWT. Agent gọi `remember` để lưu lại.
2. S2 là session mới (chứng minh 1). Khối inject có đủ 4 quy ước và agent viết code theo đúng các quy ước đó.
3. S3 đổi auth sang session cookie. Entry `auth=JWT` chuyển sang superseded.
4. S4 là session mới (chứng minh 2). Khối inject chỉ còn session cookie, và middleware agent viết ra dùng cookie.

Cuối demo chương trình in ra toàn bộ `memory.json`, có cả entry JWT cũ. Kết quả lần chạy thật nằm trong `demo_output.txt`, còn `memory.json` là memory sau lần chạy đó.

## Giao diện web

Nếu không muốn gõ lệnh thì chạy `python web.py` rồi mở http://127.0.0.1:8000. Bên trái là khung chat, bên phải là phần memory: khối đã inject vào context lúc mở session và danh sách toàn bộ entry (entry bị thay thế được gạch ngang kèm session đã thay nó).

Nút "Session mới" xoá history chat nhưng vẫn giữ `memory.json`, nên có thể tự làm lại 2 chứng minh trên giao diện: chốt quy ước, bấm Session mới rồi hỏi, sau đó đổi quy ước, bấm Session mới và hỏi lại. Nút "Xoá memory" đưa `memory.json` về rỗng để làm lại từ đầu. Web dùng chung `memory.json` và cùng một agent với bản dòng lệnh. File `.env.example` là mẫu cho file `.env`.

Ngoài ra còn `python agent.py` để chat, `python agent.py --say "..."` để hỏi một câu, và `python agent.py --show-memory` để xem toàn bộ memory.

## Giới hạn

Mỗi session nạp hết memory active vào context. Với vài chục quy ước thì không sao, nhưng nếu memory lớn hơn thì nên đổi sang kiểu file index cộng các file theo chủ đề, hoặc dùng SQLite với một tool `search_memory` để chỉ nạp phần cần dùng.
