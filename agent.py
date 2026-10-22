"""Challenge A: agent với persistent memory.

- Lưu ở đâu: memory.json (JSON, mỗi entry có key, value, status, nguồn, thời điểm).
- Ai ghi: agent tự gọi tool `remember` / `forget`.
- Khi nào nạp: lúc mở session, mọi entry active được inject vào system prompt (và in ra màn hình).
- Khi quy ước đổi: entry cũ không bị xoá, mà bị đánh dấu superseded (kèm thời điểm, session nguồn, entry thay thế).

Chạy:
  python agent.py --selftest          # kiểm tra memory store + injection, không cần API
  python agent.py                     # chat 1 session (thoát: exit)
  python agent.py --say "..."         # 1 session, 1 câu hỏi
  python agent.py --demo              # 4 session riêng biệt chứng minh 1 & 2 (cần DEEPSEEK_API_KEY)
  python agent.py --show-memory       # in toàn bộ memory, kể cả entry đã bị thay thế
"""
import argparse, json, os, subprocess, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# Nạp DEEPSEEK_API_KEY từ .env cạnh file này (.env nằm trong .gitignore, không được commit).
ENV_FILE = Path(__file__).with_name(".env")
if ENV_FILE.exists():
    for line in ENV_FILE.read_text("utf-8").splitlines():
        k, sep, v = line.partition("=")
        if sep and not k.strip().startswith("#"):
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

MEMORY_FILE = Path(os.environ.get("AGENT_MEMORY_FILE", Path(__file__).with_name("memory.json")))
MODEL = "deepseek-flash"  # hoặc "deepseek-v4-pro"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Memory store ----------
class MemoryStore:
    def __init__(self, path=MEMORY_FILE):
        self.path = Path(path)
        self.entries = json.loads(self.path.read_text("utf-8")) if self.path.exists() else []

    def _save(self):
        # Ghi file tạm rồi os.replace, để nếu bị ngắt giữa chừng thì memory.json cũ vẫn còn nguyên.
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(self.entries, ensure_ascii=False, indent=2), "utf-8")
        try:
            os.replace(tmp, self.path)
        except OSError:  # một số thư mục bị sandbox chặn rename: ghi thẳng, file tạm vẫn còn làm bản dự phòng
            self.path.write_text(tmp.read_text("utf-8"), "utf-8")

    def active(self):
        return [e for e in self.entries if e["status"] == "active"]

    def remember(self, key, value, session):
        key = key.strip().lower()
        old = next((e for e in self.active() if e["key"] == key), None)
        if old and old["value"] == value:
            return f"Không đổi: [{key}] đã là '{value}'."
        new = {"id": uuid.uuid4().hex[:8], "key": key, "value": value, "status": "active",
               "created_at": now(), "source_session": session}
        if old:  # xung đột: không append mù quáng, đánh dấu entry cũ đã bị thay thế
            old.update(status="superseded", superseded_at=now(), superseded_by=new["id"],
                       superseded_in_session=session)
            new["supersedes"] = old["id"]
        self.entries.append(new)
        self._save()
        return f"Đã thay [{key}]: '{old['value']}' -> '{value}'." if old else f"Đã lưu [{key}] = '{value}'."

    def forget(self, key, session):
        key = key.strip().lower()
        old = next((e for e in self.active() if e["key"] == key), None)
        if not old:
            return f"Không có memory active nào với key [{key}]."
        old.update(status="forgotten", forgotten_at=now(), forgotten_in_session=session)
        self._save()
        return f"Đã quên [{key}]."

    def render(self):
        """Khối text được inject vào context lúc mở session."""
        rows = [f"- [{e['key']}] {e['value']}  (từ {e['source_session']}, {e['created_at']})"
                for e in sorted(self.active(), key=lambda e: e["key"])]
        return "\n".join(rows) or "(chưa có memory nào)"


# ---------- Agent ----------
TOOLS = [
    {"type": "function", "function": {
        "name": "remember",
        "description": (
            "Lưu một quy ước/quyết định/sở thích lâu dài của dự án để các session sau còn nhớ. "
            "Gọi khi user thống nhất hoặc thay đổi một quy ước. Nếu quy ước đã có trong <project_memory>, "
            "PHẢI dùng lại đúng key đó: giá trị cũ sẽ tự bị đánh dấu superseded. "
            "Không lưu chuyện vặt, dữ liệu tạm hay nội dung chỉ dùng trong session này."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Chủ đề ngắn, ổn định, snake_case, vd: database, language, api_naming, auth"},
                "value": {"type": "string", "description": "Quy ước hiện hành, viết đủ ý để đọc lại không cần ngữ cảnh"},
            },
            "required": ["key", "value"],
        },
    }},
    {"type": "function", "function": {
        "name": "forget",
        "description": "Bỏ một quy ước không còn áp dụng mà không có quy ước thay thế.",
        "parameters": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    }},
]


def call_tool(store, name, raw_args, session):
    # Tham số do model sinh ra: kiểm tra trước khi ghi vào memory.
    try:
        args = json.loads(raw_args or "{}")
    except json.JSONDecodeError:
        return f"Lỗi: arguments không phải JSON hợp lệ: {raw_args!r}"
    if name == "remember" and isinstance(args.get("key"), str) and isinstance(args.get("value"), str):
        return store.remember(args["key"], args["value"], session)
    if name == "forget" and isinstance(args.get("key"), str):
        return store.forget(args["key"], session)
    return f"Lỗi: tool hoặc tham số không hợp lệ: {name}({raw_args})"

SYSTEM = """Bạn là coding agent của một dự án phần mềm. Trả lời bằng tiếng Việt, ngắn gọn.

<project_memory> là các quy ước đã thống nhất từ những session trước. Đây là nguồn sự thật hiện hành:
luôn làm theo, kể cả khi user không nhắc lại. Khi user thống nhất một quy ước mới hoặc đổi quy ước cũ,
gọi tool `remember` (dùng lại key có sẵn nếu đổi quy ước cũ) rồi mới trả lời.

<project_memory>
{memory}
</project_memory>"""


def open_session(store):
    """Mở session mới: history rỗng, memory active được inject vào system prompt. Trả về (client, messages)."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
    return client, [{"role": "system", "content": SYSTEM.format(memory=store.render())}]


def turn(client, store, messages, prompt, session):
    """Một lượt chat (có thể gồm nhiều vòng tool call). Trả về (câu trả lời, danh sách log tool)."""
    messages.append({"role": "user", "content": prompt})
    log = []
    while True:
        msg = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS).choices[0].message
        # Gửi lại nguyên message (kể cả reasoning_content của thinking mode) để vòng tool call không bị lỗi.
        messages.append(msg.model_dump(exclude_none=True))
        if not msg.tool_calls:
            return msg.content or "", log
        for c in msg.tool_calls:
            out = call_tool(store, c.function.name, c.function.arguments, session)
            log.append(f"[tool {c.function.name}] {out}")
            messages.append({"role": "tool", "tool_call_id": c.id, "content": out})


def run_session(prompts, session):
    store = MemoryStore()
    print(f"\n========== {session} ==========")
    print("[INJECTED MEMORY]\n" + store.render() + "\n[/INJECTED MEMORY]")
    client, messages = open_session(store)
    for prompt in prompts:
        print(f"\nUSER> {prompt}")
        reply, log = turn(client, store, messages, prompt, session)
        for line in log:
            print("  " + line)
        print("AGENT> " + reply)


def chat():
    session = "session-" + datetime.now().strftime("%Y%m%d-%H%M%S")

    def prompts():
        while (line := input("\nUSER> ").strip()).lower() not in ("exit", "quit"):
            if line:
                yield line

    run_session(prompts(), session)


# Mỗi session là một process riêng: chỉ memory.json được truyền qua, không có history.
DEMO = [
    ("S1-thong-nhat", "Chốt quy ước dự án: database PostgreSQL, ngôn ngữ TypeScript, "
                      "API route dạng kebab-case số nhiều (vd /user-profiles), authentication dùng JWT."),
    ("S2-chung-minh-1", "Viết ngắn route handler đăng nhập (chỉ phần khung). "
                        "Nói rõ bạn dùng database, ngôn ngữ, kiểu route và cơ chế auth nào."),
    ("S3-doi-quy-uoc", "Team quyết định bỏ JWT, chuyển authentication sang session cookie (httpOnly, lưu session trong PostgreSQL)."),
    ("S4-chung-minh-2", "Viết ngắn middleware kiểm tra user đã đăng nhập. Nói rõ cơ chế auth bạn dùng."),
]


def demo():
    if MEMORY_FILE.exists():
        MEMORY_FILE.unlink()  # demo bắt đầu từ memory rỗng
    for session, prompt in DEMO:
        subprocess.run([sys.executable, __file__, "--session", session, "--say", prompt], check=True)
    print("\n========== MEMORY CUỐI CÙNG (kể cả entry bị thay thế) ==========")
    print(MEMORY_FILE.read_text("utf-8"))


# ---------- Self-check (không gọi API) ----------
def selftest():
    import tempfile as tf
    path = Path(tf.mkdtemp()) / "memory.json"
    s = MemoryStore(path)
    s.remember("database", "PostgreSQL", "S1")
    s.remember("Auth", "JWT", "S1")

    # Chứng minh 1: process mới (store mới đọc từ đĩa) thấy quy ước cũ trong khối inject
    injected = MemoryStore(path).render()
    assert "[database] PostgreSQL" in injected and "[auth] JWT" in injected, injected

    # Chứng minh 2: đổi quy ước -> chỉ còn 1 entry active cho key, entry cũ giữ dấu vết
    s = MemoryStore(path)
    assert "Không đổi" in s.remember("auth", "JWT", "S2")  # ghi lại cùng giá trị không tạo bản trùng
    s.remember("auth", "Session cookie", "S3")
    s = MemoryStore(path)
    auth = [e for e in s.entries if e["key"] == "auth"]
    active = [e for e in auth if e["status"] == "active"]
    old = next(e for e in auth if e["status"] == "superseded")
    assert len(active) == 1 and active[0]["value"] == "Session cookie"
    assert old["value"] == "JWT" and old["source_session"] == "S1"
    assert old["superseded_in_session"] == "S3" and old["superseded_by"] == active[0]["id"]
    injected = s.render()
    assert "Session cookie" in injected and "JWT" not in injected, injected

    # Tham số tool do model sinh ra: JSON hỏng hoặc thiếu field không được làm hỏng memory
    assert call_tool(s, "remember", "{bad json", "S4").startswith("Lỗi")
    assert call_tool(s, "remember", '{"key": "auth"}', "S4").startswith("Lỗi")
    assert "Đã lưu" in call_tool(s, "remember", '{"key": "language", "value": "TypeScript"}', "S4")

    s.forget("database", "S4")
    assert "database" not in MemoryStore(path).render()
    s.remember("note", "tiếng Việt có dấu", "S4")
    assert "tiếng Việt có dấu" in MemoryStore(path).render()
    print("selftest OK\n[INJECTED MEMORY]\n" + MemoryStore(path).render())


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--selftest", action="store_true")
    p.add_argument("--demo", action="store_true")
    p.add_argument("--show-memory", action="store_true")
    p.add_argument("--say")
    p.add_argument("--session", default=None)
    a = p.parse_args()
    if a.selftest:
        selftest()
    elif a.demo:
        demo()
    elif a.show_memory:
        print(MEMORY_FILE.read_text("utf-8") if MEMORY_FILE.exists() else "[]")
    elif a.say:
        run_session([a.say], a.session or "session-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    else:
        chat()
