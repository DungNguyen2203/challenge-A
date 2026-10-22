"""Giao diện web cho Challenge A. Chạy: python web.py  rồi mở http://127.0.0.1:8000

Chỉ dùng thư viện chuẩn. Memory vẫn nằm trong memory.json; nút "Session mới" xoá history chat
nhưng giữ memory, đúng tình huống "sang session mới" của đề bài.
"""
import json
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

import agent
from agent import MemoryStore

PORT = 8000
S = {}  # session hiện tại (app chạy local cho một người dùng)


def new_session():
    store = MemoryStore()
    client, messages = agent.open_session(store)
    S.update(id="web-" + datetime.now().strftime("%H%M%S"), client=client, messages=messages,
             injected=store.render())


def state():
    return {"session": S["id"], "injected": S["injected"], "entries": MemoryStore().entries}


PAGE = """<!doctype html><html lang="vi"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Challenge A: persistent memory</title>
<style>
:root{--bg:#fff;--fg:#1c1c1e;--mut:#6b7280;--line:#e5e7eb;--card:#f6f7f9;--acc:#2563eb}
@media(prefers-color-scheme:dark){:root{--bg:#16181d;--fg:#e8e8ea;--mut:#9aa0aa;--line:#2b2f37;--card:#20232b;--acc:#6ea0ff}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:1200px;margin:0 auto;padding:16px;height:100vh}
@media(max-width:800px){main{grid-template-columns:1fr;height:auto}}
section{display:flex;flex-direction:column;min-height:0;border:1px solid var(--line);border-radius:10px;padding:12px}
h2{margin:0 0 8px;font-size:15px}small,.mut{color:var(--mut)}
#chat,#side{flex:1;overflow:auto;min-height:200px}
.m{white-space:pre-wrap;margin:6px 0;padding:8px 10px;border-radius:8px;background:var(--card)}
.m.u{background:var(--acc);color:#fff}.m.t{font:13px ui-monospace,monospace;color:var(--mut)}
pre{white-space:pre-wrap;background:var(--card);padding:8px;border-radius:8px;font:13px/1.4 ui-monospace,monospace;margin:4px 0 12px}
form{display:flex;gap:8px;margin-top:8px}input{flex:1;padding:8px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--fg);font:inherit}
button{padding:8px 12px;border:1px solid var(--line);border-radius:8px;background:var(--card);color:var(--fg);font:inherit;cursor:pointer}
button.p{background:var(--acc);color:#fff;border-color:var(--acc)}button:disabled{opacity:.5}
.e{padding:6px 8px;border-left:3px solid var(--acc);margin:4px 0;background:var(--card);border-radius:0 6px 6px 0}
.e.old{border-color:var(--mut);text-decoration:line-through;color:var(--mut)}
.bar{display:flex;gap:8px;align-items:center;justify-content:space-between;margin-bottom:8px}
</style>
<main>
<section><div class="bar"><h2>Chat <small id="sid"></small></h2><button id="new">Session mới</button></div>
<div id="chat"></div>
<form id="f"><input id="q" placeholder="Nhập tin nhắn..." autocomplete="off" autofocus><button class="p" id="go">Gửi</button></form></section>
<section><div class="bar"><h2>Memory</h2><button id="reset">Xoá memory</button></div>
<div id="side"><b>Đã inject vào context lúc mở session này</b>
<pre id="inj"></pre><b>Toàn bộ memory (<span id="n"></span>)</b><div id="ents"></div></div></section>
</main>
<script>
const $=id=>document.getElementById(id);
const add=(cls,txt)=>{const d=document.createElement('div');d.className='m '+cls;d.textContent=txt;$('chat').append(d);$('chat').scrollTop=1e9};
function draw(s){
  $('sid').textContent='('+s.session+')';$('inj').textContent=s.injected;$('n').textContent=s.entries.length;
  $('ents').replaceChildren(...s.entries.map(e=>{const d=document.createElement('div');
    d.className='e'+(e.status==='active'?'':' old');
    d.textContent=(e.status==='active'?'ĐANG DÙNG ':e.status==='superseded'?'CŨ ':'ĐÃ QUÊN ')+'['+e.key+'] '+e.value+'  (ghi ở '+e.source_session+')'
      +(e.status==='superseded'?' → đã bị quy ước mới thay thế ở '+e.superseded_in_session:e.status==='forgotten'?' → đã quên ở '+e.forgotten_in_session:'');return d}));
}
async function api(path,body){const r=await fetch(path,{method:body===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
$('f').onsubmit=async ev=>{ev.preventDefault();const q=$('q').value.trim();if(!q)return;$('q').value='';
  add('u',q);$('go').disabled=true;
  try{const j=await api('/api/chat',{prompt:q});j.log.forEach(l=>add('t',l));add('',j.reply);draw(j.state)}
  catch(e){add('t','Lỗi: '+e.message)}finally{$('go').disabled=false;$('q').focus()}};
$('new').onclick=async()=>{$('chat').replaceChildren();draw(await api('/api/new-session',{}));add('t','Session mới: history trống, memory được nạp lại từ memory.json')};
$('reset').onclick=async()=>{if(confirm('Xoá toàn bộ memory.json?'))draw(await api('/api/reset-memory',{}))};
api('/api/state').then(draw);
</script></html>"""


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False))

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._json(state())
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            if self.path == "/api/new-session":
                new_session()
                self._json(state())
            elif self.path == "/api/reset-memory":
                agent.MEMORY_FILE.unlink(missing_ok=True)
                new_session()
                self._json(state())
            elif self.path == "/api/chat":
                store = MemoryStore()
                reply, log = agent.turn(S["client"], store, S["messages"], body["prompt"], S["id"])
                self._json({"reply": reply, "log": log, "state": state()})
            else:
                self._json({"error": "not found"}, 404)
        except Exception as e:  # lỗi API/mạng trả về cho UI hiển thị, không làm sập server
            self._json({"error": f"{type(e).__name__}: {e}"}, 500)


if __name__ == "__main__":
    new_session()
    print(f"Mở http://127.0.0.1:{PORT}")
    HTTPServer(("127.0.0.1", PORT), H).serve_forever()
