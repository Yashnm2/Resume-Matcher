import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import time


MASTER = json.loads(
    Path(__file__)
    .resolve()
    .parents[2]
    .joinpath("apps/backend/e2e_monitor/fixtures/master.json")
    .read_text(encoding="utf-8")
)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.rstrip("/") == "/v1/models":
            self._json({"object": "list", "data": [{"id": "resume-test-model", "object": "model"}]})
        else:
            self._json({"status": "ok"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        messages = payload.get("messages", [])
        prompt = "\n".join(str(message.get("content", "")) for message in messages)
        if "JSON extraction engine" in prompt or "personalInfo" in prompt:
            content = json.dumps(MASTER)
        else:
            content = "OK"
        self._json(
            {
                "id": "chatcmpl-resume-test",
                "object": "chat.completion",
                "created": int(time()),
                "model": "resume-test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 100, "completion_tokens": 100, "total_tokens": 200},
            }
        )

    def log_message(self, format, *args):
        return

    def _json(self, payload, status=200):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 19000), Handler).serve_forever()
