"""ServiceWaze audit: clickability + data presence check."""
import json
import re
import urllib.request

s = open("templates/index.html").read()
js = s.split("<script>")[1].split("</script>")[0]

print("=== CLICKABILITY AUDIT ===")
onclicks = re.findall(r'onclick="([^"]+)"', s)
called = set()
for oc in onclicks:
    for m in re.finditer(r"([A-Za-z_$][\w$]*)\s*\(", oc):
        called.add(m.group(1))
defined = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", js))
defined |= set(re.findall(r"^(\w+)\s*=\s*(?:async\s*)?\(", js, re.M))
missing = called - defined - {"t"}
print("inline onclick handlers:", len(onclicks))
print("functions called by clicks:", sorted(called))
print("MISSING (dead buttons):", sorted(missing) or "NONE ✓")

ids_html = set(re.findall(r'id="([^"]+)"', s))
refs = set(re.findall(r'getElementById\("([^"]+)"\)', js))
print("referenced ids missing in HTML:", sorted(refs - ids_html) or "NONE ✓")

hrefs = re.findall(r'href="([^"]+)"', s)
print("static hrefs:", len(hrefs), "| tel:", sum(1 for h in hrefs if h.startswith("tel:")),
      "| wa.me:", sum(1 for h in hrefs if "wa.me" in h),
      "| http:", sum(1 for h in hrefs if h.startswith("http")))

print("\n=== JS SANITY ===")
print("braces:", js.count("{"), js.count("}"), "| parens:", js.count("("), js.count(")"))

print("\n=== LIVE API DATA CHECKS ===")
base = "http://127.0.0.1:8000"
def check(path, label=None):
    try:
        d = json.loads(urllib.request.urlopen(base + path, timeout=30).read())
        if label:
            print(f"  OK  {path} -> {label}: {d}")
        else:
            print(f"  OK  {path}")
    except Exception as e:
        print(f"  FAIL {path} -> {e}")
check("/api/health", "health")
check("/api/status?q=Soweto", "place/weather/air")
check("/api/feed?limit=80", "merged items")
check("/api/services", "service categories")
check("/api/areas?q=durban", "geocode")

print("\n=== NEWS RELEVANCE SAMPLE (top 15 of merged feed) ===")
d = json.loads(urllib.request.urlopen(base + "/api/feed?limit=80", timeout=30).read())
for i in d["items"][:15]:
    print(f"  [{i['category']:11}] {i['title'][:70]}")
