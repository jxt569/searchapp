import asyncio
import html
import json
import re
import sqlite3
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DB_PATH = "rag.sqlite3"
HOST = "127.0.0.1"
PORT = 8000
CHUNK_SIZE = 900
OVERLAP = 150

STOPWORDS = {
    "a","an","and","are","as","at","be","because","been","but","by","can","could",
    "did","do","does","for","from","had","has","have","he","her","his","i","if",
    "in","is","it","its","me","my","not","of","on","or","our","she","so","that",
    "the","their","them","then","there","they","this","to","too","use","used",
    "was","we","were","what","when","where","which","who","why","will","with","you","your"
}

INDEX = """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Async Stdlib RAG</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 1100px; margin: 40px auto; padding: 0 16px; line-height: 1.5; }
    textarea, input { width: 100%; box-sizing: border-box; font: inherit; }
    textarea { min-height: 180px; }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    button { padding: 10px 14px; font: inherit; cursor: pointer; }
    .card { border: 1px solid #ddd; border-radius: 10px; padding: 16px; margin-top: 16px; }
    pre { white-space: pre-wrap; word-wrap: break-word; }
    small { color: #666; }
  </style>
</head>
<body>
  <h1>Async Stdlib RAG</h1>
  <p><small>Paste documents, ingest them, then ask questions.</small></p>

  <div class="row">
    <div class="card">
      <h2>Ingest</h2>
      <textarea id="doc" placeholder="Paste source text here..."></textarea>
      <button onclick="ingest()">Ingest</button>
      <div id="ingestStatus"></div>
    </div>

    <div class="card">
      <h2>Ask</h2>
      <input id="question" placeholder="Ask a question..." />
      <button onclick="ask()">Ask</button>
      <div id="askStatus"></div>
    </div>
  </div>

  <div class="card">
    <h2>Answer</h2>
    <pre id="answer"></pre>
  </div>

  <div class="card">
    <h2>Top chunks</h2>
    <div id="chunks"></div>
  </div>

<script>
async function ingest() {
  const text = document.getElementById('doc').value;
  const res = await fetch('/ingest', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text})
  });
  const data = await res.json();
  document.getElementById('ingestStatus').textContent = data.ok ? `Ingested ${data.chunks} chunks.` : data.error;
}

async function ask() {
  const question = document.getElementById('question').value;
  const res = await fetch('/ask', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({question})
  });
  const data = await res.json();
  document.getElementById('answer').textContent = data.answer || '';
  document.getElementById('askStatus').textContent = data.ok ? `Used ${data.top_k} chunks.` : data.error;

  const chunks = document.getElementById('chunks');
  chunks.innerHTML = '';
  for (const item of data.matches || []) {
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<strong>Score:</strong> ${item.score.toFixed(3)}<br><small>${item.source}</small><pre>${item.text}</pre>`;
    chunks.appendChild(div);
  }
}
</script>
</body>
</html>
"""

def tokenize(text):
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in STOPWORDS]

def chunk_text(text, size=CHUNK_SIZE, overlap=OVERLAP):
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        j = min(n, i + size)
        chunks.append(text[i:j].strip())
        if j >= n:
            break
        i = max(j - overlap, i + 1)
    return [c for c in chunks if c]

def score_chunk(question_tokens, chunk_tokens):
    if not question_tokens or not chunk_tokens:
        return 0.0
    q = {}
    for t in question_tokens:
        q[t] = q.get(t, 0) + 1
    c = {}
    for t in chunk_tokens:
        c[t] = c.get(t, 0) + 1
    score = 0.0
    for t, qc in q.items():
        if t in c:
            score += qc * c[t]
    return score / (len(chunk_tokens) ** 0.5)

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chunks(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            text TEXT NOT NULL,
            tokens TEXT NOT NULL,
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn

def ingest_text(text, source="paste"):
    parts = chunk_text(text)
    if not parts:
        return 0
    conn = db()
    now = time.time()
    with conn:
        for part in parts:
            tokens = " ".join(tokenize(part))
            conn.execute(
                "INSERT INTO chunks(source, text, tokens, created_at) VALUES(?,?,?,?)",
                (source, part, tokens, now),
            )
    conn.close()
    return len(parts)

def retrieve(question, top_k=5):
    q_tokens = tokenize(question)
    conn = db()
    cur = conn.execute("SELECT source, text, tokens FROM chunks")
    rows = cur.fetchall()
    conn.close()
    scored = []
    for source, text, tokens in rows:
        s = score_chunk(q_tokens, tokens.split())
        if s > 0:
            scored.append({"source": source, "text": text, "score": s})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]

def make_answer(question, matches):
    if not matches:
        return "I couldn't find relevant context in the indexed documents."
    context = "\n\n".join(f"- {m['text']}" for m in matches)
    return (
        f"Question: {question}\n\n"
        f"Relevant context:\n{context}\n\n"
        "Answer:\n"
        "Based on the retrieved context above, summarize the direct facts and cite the most relevant chunk(s)."
    )

def http_response(status, content_type, body):
    reason = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}.get(status, "OK")
    headers = [
        f"HTTP/1.1 {status} {reason}",
        f"Content-Type: {content_type}; charset=utf-8",
        f"Content-Length: {len(body.encode('utf-8'))}",
        "Connection: close",
        "",
        ""
    ]
    return "\r\n".join(headers).encode("utf-8") + body.encode("utf-8")

async def handle_client(reader, writer):
    try:
        raw = await reader.read(10_000_000)
        if not raw:
            writer.close()
            await writer.wait_closed()
            return
        head, _, body = raw.partition(b"\r\n\r\n")
        lines = head.decode("utf-8", "ignore").split("\r\n")
        method, target, _ = lines[0].split(" ", 2)
        path = urlparse(target).path

        if method == "GET" and path == "/":
            resp = http_response(200, "text/html", INDEX)
        elif method == "POST" and path in {"/ingest", "/ask"}:
            try:
                data = json.loads(body.decode("utf-8"))
            except Exception:
                resp = http_response(400, "application/json", json.dumps({"ok": False, "error": "Invalid JSON"}))
            else:
                if path == "/ingest":
                    text = data.get("text", "")
                    count = await asyncio.to_thread(ingest_text, text, "paste")
                    resp = http_response(200, "application/json", json.dumps({"ok": True, "chunks": count}))
                else:
                    question = data.get("question", "").strip()
                    if not question:
                        resp = http_response(400, "application/json", json.dumps({"ok": False, "error": "Question is empty"}))
                    else:
                        matches = await asyncio.to_thread(retrieve, question, 5)
                        answer = make_answer(question, matches)
                        resp = http_response(200, "application/json", json.dumps({
                            "ok": True,
                            "answer": answer,
                            "matches": matches,
                            "top_k": len(matches)
                        }))
        else:
            resp = http_response(404, "application/json", json.dumps({"ok": False, "error": "Not found"}))

        writer.write(resp)
        await writer.drain()
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

async def main():
    Path(DB_PATH).touch(exist_ok=True)
    db().close()
    server = await asyncio.start_server(handle_client, HOST, PORT)
    async with server:
        print(f"Serving on http://{HOST}:{PORT}")
        await server.serve_forever()

if __name__ == "__main__":
    asyncio.run(main())