"""Bundle saved Nimble + Gemini results (and sponsor logos) into the demo page.

Writes mockup/index.html (artifact source) and docs/index.html (GitHub Pages).
"""
import base64
import json
import os
import re
from datetime import datetime, timedelta

ROOT = __file__.rsplit("/pipeline/", 1)[0]
load = lambda p: json.load(open(f"{ROOT}/{p}"))
story = load("data/raw/ff_story_1430919.json")
news = load("data/raw/ff_news_vx10.json")
g_story = load("data/extracted/ff_story_1430919.json")
g_news = load("data/extracted/ff_news.json")

md = story["data"]["markdown"]
fetched = datetime.strptime(story["metadata"]["query_time"][:19], "%Y-%m-%dT%H:%M:%S")

COMMENT = re.compile(
    r"(?:\[([^\]\n]+)\]\(https://www\.forexfactory\.com/[^)\s]+\)|^(Trader#\w+))\s*\n\s*\n"
    r"([^\n]*ago)\s*\n\s*\n\[Permalink\]\([^)]+/comment/(\d+)[^)]*\)\s*\n"
    r"(.*?)(?=\n\[!\[\]|\nhttps://www\.forexfactory\.com/[a-z0-9*._-]+\s*\n|\nTrader#\w+\s*\n|\Z)",
    re.S | re.M)


def absolute(rel: str) -> str:
    h = re.search(r"(\d+) hr", rel)
    m = re.search(r"(\d+) min", rel)
    delta = timedelta(hours=int(h.group(1)) if h else 0, minutes=int(m.group(1)) if m else 0)
    return (fetched - delta).strftime("%Y-%m-%dT%H:%MZ")


def clean(body: str) -> str:
    body = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)|!\[[^\]]*\]\([^)]*\)", "[image]", body, flags=re.S)
    body = re.sub(r"Attached Image \(click to enlarge\)", "", body)
    lines = [l.strip() for l in body.split("\n")]
    drop = re.compile(r"^(Reply|\d+|View \d+ (more )?repl.*|Hide repl.*|Collapse Replies|Expand Replies)?$")
    return "\n".join(l for l in lines if not drop.match(l)).strip()


kept = {o.get("comment_id"): o for o in g_story["opinions"]}
skipped = {}
for s in g_story["skipped"]:
    skipped.setdefault(s["author"], []).append(s["reason"])

thread = []
for m in COMMENT.finditer(md):
    cid = m.group(4)
    author = m.group(1) or m.group(2)
    item = {"id": cid, "author": author, "relative": m.group(3).strip(), "at": absolute(m.group(3)), "text": clean(m.group(5))}
    if cid in kept:
        o = kept[cid]
        item["gemini"] = {"kept": True, "pairs": o["pairs"], "outlook": o["outlook"], "reason": o["reason"]}
    elif author in skipped:
        item["gemini"] = {"kept": False, "reason": skipped[author][0] if len(skipped[author]) == 1 else " / ".join(dict.fromkeys(skipped[author]))}
    thread.append(item)
thread.sort(key=lambda c: c["at"])

seen = {}
for page, g in (("story page", g_story), ("news page", g_news)):
    for o in g["opinions"]:
        seen.setdefault(o.get("comment_id") or o["quote"], []).append({"page": page, "author": o["author"], "quote": o["quote"]})

title = md[: md.find("\n")].replace(" | Forex Factory", "").strip()
excerpt = f"# {title}\n\n…\n\n" + md[md.find("*   **Comments"): md.find("[Manmeetkaur]")].strip() + "\n\n… (trimmed for display)"

live = {
    "title": title,
    "nimble_story": {
        "request": {"method": "POST", "endpoint": "https://sdk.nimbleway.com/v2/extract",
                    "body": {"url": story["url"], "driver": "vx10", "formats": ["markdown"], "browser_actions": [{"wait": 3000}]}},
        "response": {"url": story["url"], "task_id": story["task_id"], "status": story["status"],
                     "data": {"markdown": excerpt}, "metadata": story["metadata"], "status_code": story["status_code"]},
        "full_markdown_chars": len(md),
    },
    "nimble_news": {"url": news["url"], "task_id": news["task_id"], "metadata": news["metadata"], "markdown_chars": len(news["data"]["markdown"])},
    "thread": thread,
    "gemini_story": g_story,
    "gemini_news": {"model": g_news["model"], "opinions": len(g_news["opinions"]), "skipped": len(g_news["skipped"])},
    "dedupe": {"key": "ForexFactory comment ID (from the permalink)", "readings": sum(len(v) for v in seen.values()),
               "unique_comments": len(seen), "by_comment_id": seen,
               "result": "Same author, same thread, same view: 2 comments merged into 1 dish."},
}


def data_uri(name: str, recolor: bool = False) -> str:
    svg = open(f"{ROOT}/assets/logos/{name}.svg").read()
    if recolor:
        svg = svg.replace("#0B0B0B", "#000")
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


logo_css = (
    f'.lg-nimble{{display:inline-block;height:var(--lg-h,12px);aspect-ratio:199/28;background:currentColor;vertical-align:-1px;'
    f'-webkit-mask:url("{data_uri("nimble", True)}") center/contain no-repeat;mask:url("{data_uri("nimble", True)}") center/contain no-repeat}}'
    f'.lg-gemini{{display:inline-block;height:calc(var(--lg-h,12px)*1.7);aspect-ratio:344/127;vertical-align:-5px;'
    f'background:url("{data_uri("gemini_word")}") center/contain no-repeat}}'
)

page = f"{ROOT}/mockup/index.html"
html = open(page).read()
s = json.dumps(live, ensure_ascii=False).replace("</", "<\\/")
html = re.sub(r'(<script type="application/json" id="live">).*?(</script>)', lambda m: m.group(1) + s + m.group(2), html, count=1, flags=re.S)
html = re.sub(r'(<style id="logos">).*?(</style>)', lambda m: m.group(1) + logo_css + m.group(2), html, count=1, flags=re.S)
open(page, "w").write(html)

skeleton = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>:root{color-scheme:light}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
</head>
<body>
"""
os.makedirs(f"{ROOT}/docs", exist_ok=True)
open(f"{ROOT}/docs/index.html", "w").write(skeleton + html + "\n</body>\n</html>\n")
print(f"thread: {len(thread)} comments, kept {sum(1 for c in thread if c.get('gemini', {}).get('kept'))}; live block {len(s)} chars")
