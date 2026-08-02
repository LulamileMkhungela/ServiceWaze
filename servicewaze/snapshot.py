"""Generate a static snapshot of the dashboard (data baked in) for offline preview.

Usage (while the server is running):
    python snapshot.py "Soweto"
Writes preview.html in the project root.
"""
import json
import os
import sys
import urllib.request
from urllib.parse import urlencode

from jinja2 import Environment, FileSystemLoader

BASE = os.environ.get("SNAPSHOT_URL", "http://127.0.0.1:8000")
QUERY = sys.argv[1] if len(sys.argv) > 1 else "Soweto"


def get(path):
    with urllib.request.urlopen(BASE + path, timeout=15) as r:
        return r.read().decode()


boot = {
    "status": json.loads(get("/api/status?" + urlencode({"q": QUERY}))),
    "feed": json.loads(get("/api/feed?limit=60")),
    "services": json.loads(get("/api/services")),
}

env = Environment(loader=FileSystemLoader("templates"))
html = env.get_template("index.html").render(request={}, boot=boot, static_mode=True)
with open("preview.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"Wrote preview.html ({len(html)} bytes) for: {boot['status']['place']['name']} "
      f"| feed items: {len(boot['feed']['items'])} | services: {len(boot['services']['services'])}")
