"""Заглушка web-процесса для Scalingo (scale web:0 после деплоя)."""

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

port = int(os.environ.get("PORT", "5000"))
ThreadingHTTPServer(("", port), SimpleHTTPRequestHandler).serve_forever()