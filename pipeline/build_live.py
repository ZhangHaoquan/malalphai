"""Bundle every saved Nimble thread + Gemini reading (and sponsor logos) into the demo page.

Writes mockup/index.html (artifact source) and docs/index.html (GitHub Pages).
"""
import base64
import glob
import json
import os
import re
from datetime import datetime, timedelta

ROOT = __file__.rsplit("/pipeline/", 1)[0]
FLAGSHIP = "1430919"

COMMENT = re.compile(
    r"(?:\[([^\]\n]+)\]\(https://www\.forexfactory\.com/[^)\s]+\)|^(Trader#\w+))\s*\n\s*\n"
    r"([^\n]*ago)\s*\n\s*\n\[Permalink\]\([^)]+/comment/(\d+)[^)]*\)\s*\n"
    r"(.*?)(?=\n\[!\[\]|\nhttps://www\.forexfactory\.com/[a-z0-9*._-]+\s*\n|\nTrader#\w+\s*\n|\Z)",
    re.S | re.M)
DROP = re.compile(r"^(Reply|\d+|View \d+ (more )?repl.*|Hide repl.*|Collapse Replies|Expand Replies)?$")


def fx_text(t: str) -> str:
    """Gemini reasons use internal pair keys; show market names instead."""
    for k, v in (("USDEUR", "USD vs EUR"), ("USDGBP", "USD vs GBP"), ("USDJPY", "USD/JPY"), ("USDCAD", "USD/CAD")):
        t = t.replace(k, v)
    return t


def absolute(rel: str, fetched: datetime) -> str:
    d = re.search(r"(\d+) day", rel)
    h = re.search(r"(\d+) hr", rel)
    m = re.search(r"(\d+) min", rel)
    delta = timedelta(days=int(d.group(1)) if d else 0, hours=int(h.group(1)) if h else 0, minutes=int(m.group(1)) if m else 0)
    return (fetched - delta).strftime("%Y-%m-%dT%H:%MZ")


def clean(body: str) -> str:
    body = re.sub(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)|!\[[^\]]*\]\([^)]*\)", "[image]", body, flags=re.S)
    body = body.replace("Attached Image (click to enlarge)", "")
    body = re.sub(r">?\s*\[Quoting ([^\]]+)\]\([^)]*\)", r"↪ quoting \1:", body)
    body = re.split(r"\n[*\s]*#+\s*Related|\n[*\s]*Related Stories", body)[0]
    return "\n".join(l for l in (x.strip() for x in body.split("\n")) if not DROP.match(l)).strip()[:600]


FORUM = re.compile(
    r"\[#[\d,]+\]\(https://www\.forexfactory\.com/thread/post/(\d+)#post\d+\)\s*\n\*\s+([^\n]+)\n\s*\n"
    r"\*\s+\[(?:!\[\]\([^)]*\)\s*)?([^\]]+)\]\(https://www\.forexfactory\.com/[^)\s]+\)\s*\n\s*\n"
    r"(?:\*\s+Joined[^\n]*\n\s*\n)?(.*?)(?=\n\*\s+\[#[\d,]+\]|\Z)", re.S)


def forum_time(line: str, fetched: datetime):
    rel = re.search(r"\(([^)]*ago)\)", line)
    if rel:
        return rel.group(1), absolute(rel.group(1), fetched)
    m = re.search(r"([A-Z][a-z]{2} \d{1,2}), (?:(\d{4}) )?(\d{1,2}:\d\d[ap]m)", line)
    if not m:
        return line.strip()[:30], fetched.strftime("%Y-%m-%dT%H:%MZ")
    dt = datetime.strptime(f"{m.group(1)} {m.group(2) or fetched.year} {m.group(3)}", "%b %d %Y %I:%M%p")
    return dt.strftime("%b %-d %-I:%M%p"), dt.strftime("%Y-%m-%dT%H:%MZ")


RSS = re.compile(r"\*\*([^*]+)\*\* · (\d{4}-\d\d-\d\dT\d\d:\d\dZ) · id (\w+)\n\n(.*?)\n\n---", re.S)


def parse_thread(md: str, fetched: datetime) -> list:
    out = []
    for m in RSS.finditer(md):
        at = m.group(2)
        mins = int((fetched - datetime.strptime(at, "%Y-%m-%dT%H:%MZ")).total_seconds() // 60)
        rel = f"{mins // 1440} days ago" if mins >= 1440 else f"{mins // 60} hr ago" if mins >= 60 else f"{max(mins, 1)} min ago"
        out.append({"id": m.group(3), "author": m.group(1), "relative": rel, "at": at, "text": m.group(4).strip()[:600]})
    for m in FORUM.finditer(md):
        rel, at = forum_time(m.group(2), fetched)
        out.append({"id": m.group(1), "author": m.group(3).strip(), "relative": rel, "at": at, "text": clean(m.group(4))})
    for m in COMMENT.finditer(md):
        out.append({"id": m.group(4), "author": m.group(1) or m.group(2), "relative": m.group(3).strip(),
                    "at": absolute(m.group(3), fetched), "text": clean(m.group(5))})
    return sorted(out, key=lambda c: c["at"])


stories, dishes, readings = [], {}, 0
for raw_path in sorted(glob.glob(f"{ROOT}/data/raw/ff_story_*.json")):
    sid = re.search(r"ff_story_(\w+)\.json", raw_path).group(1)
    ext_path = f"{ROOT}/data/extracted/ff_story_{sid}.json"
    if not os.path.exists(ext_path):
        continue
    raw, g = json.load(open(raw_path)), json.load(open(ext_path))
    md = raw["data"]["markdown"]
    fetched = datetime.strptime(raw["metadata"]["query_time"][:19], "%Y-%m-%dT%H:%M:%S")
    thread = parse_thread(md, fetched)
    by_id = {c["id"]: c for c in thread}
    skipped = {}
    for s in g.get("skipped", []):
        skipped.setdefault(s.get("author", ""), []).append(s.get("reason", ""))
    for o in g["opinions"]:
        readings += 1
        c = by_id.get(o.get("comment_id"))
        if c:
            c["g"] = {"kept": True, "pairs": o["pairs"], "outlook": o["outlook"], "reason": fx_text(o["reason"])}
        key = f"{sid}/{o['author']}"  # one dish per author per thread
        d = dishes.setdefault(key, {"key": key, "story": sid, "author": o["author"], "comment_ids": [], "quotes": [], "pairs": set(),
                                    "outlooks": [], "reasons": [], "at": None})
        d["comment_ids"].append(o.get("comment_id"))
        d["quotes"].append(o["quote"])
        d["pairs"].update(o["pairs"])
        d["outlooks"].append(o["outlook"])
        d["reasons"].append(o["reason"])
        at = c["at"] if c else raw["metadata"]["query_time"][:16] + "Z"
        d["at"] = max(d["at"] or at, at)
    for c in thread:
        if "g" not in c and c["author"] in skipped:
            c["g"] = {"kept": False, "reason": fx_text(" / ".join(dict.fromkeys(skipped[c["author"]])))}
    if not thread:  # fall back to Gemini's own record of who said what
        thread = [{"id": o.get("comment_id") or str(i), "author": o["author"], "relative": o.get("relative_time", ""),
                   "at": raw["metadata"]["query_time"][:16] + "Z", "text": o["quote"],
                   "g": {"kept": True, "pairs": o["pairs"], "outlook": o["outlook"], "reason": fx_text(o["reason"])}} for i, o in enumerate(g["opinions"])]
    title = re.sub(r" \| Page (\d+)", r" · p.\1", md[: md.find("\n")].replace(" | Forex Factory", "")).strip().lstrip("# ")
    tr = g.get("trace") or {}
    site = "r/Forex" if sid.startswith("r") else "ForexFactory"
    url = raw["url"].replace("/.rss?limit=50", "/").replace("/.rss", "/")
    stories.append({"id": sid, "site": site, "title": title, "url": url, "task_id": raw["task_id"], "status_code": raw["status_code"],
                    "meta": {k: raw["metadata"].get(k) for k in ("query_time", "query_duration", "driver")}, "chars": len(md),
                    "gemini": {"model": g.get("model"), "trace": tr, "kept": len(g["opinions"]), "skipped": len(g.get("skipped", []))},
                    "thread": thread})

# The news page also lists the newest comments: count those readings toward dedupe.
news_seen = 0
for p in ("data/extracted/ff_news.json",):
    if os.path.exists(f"{ROOT}/{p}"):
        for o in json.load(open(f"{ROOT}/{p}"))["opinions"]:
            readings += 1
            news_seen += 1

KEYS = ("usd_down", "sideways", "usd_up")
dish_list = []
for d in dishes.values():
    q = {h: [sum(o[h][k] for o in d["outlooks"]) / len(d["outlooks"]) for k in KEYS] for h in ("5d", "22d", "66d")}
    dish_list.append({"key": d["key"], "story": d["story"], "author": d["author"], "comment_ids": d["comment_ids"],
                      "quote": " … ".join(dict.fromkeys(d["quotes"])), "pairs": sorted(d["pairs"]), "q": q,
                      "reason": fx_text(d["reasons"][-1]), "at": d["at"]})
dish_list.sort(key=lambda d: d["at"], reverse=True)

news_raw = json.load(open(f"{ROOT}/data/raw/ff_news_vx10.json"))
flag = json.load(open(f"{ROOT}/data/raw/ff_story_{FLAGSHIP}.json"))
fmd = flag["data"]["markdown"]
excerpt = fmd[: fmd.find("\n")] + "\n\n…\n\n" + fmd[fmd.find("*   **Comments"): fmd.find("*   **Comments") + 2500] + "\n\n… (trimmed for display)"

def trading_days_after(iso: str, n: int) -> str:
    d = datetime.strptime(iso[:10], "%Y-%m-%d")
    while n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d.strftime("%b %-d")


last_fetch = max(s["meta"]["query_time"] for s in stories)
searches = []
for f in sorted(glob.glob(f"{ROOT}/data/search/search_*.json")):
    r = json.load(open(f))
    searches.append({"query": os.path.basename(f)[7:-5].replace("_", " "), "request_id": r.get("request_id"),
                     "results": [x.get("url") for x in r.get("results", [])][:8]})

live = {
    "searches": searches,
    "grade5d": trading_days_after(last_fetch, 5),
    "grade22d": trading_days_after(last_fetch, 22),
    "news": {"url": news_raw["url"], "task_id": news_raw["task_id"], "meta": news_raw["metadata"], "chars": len(news_raw["data"]["markdown"])},
    "stories": stories,
    "dishes": dish_list,
    "funnel": {"pages": len(glob.glob(f"{ROOT}/data/raw/ff_story_*.json")) + 2 + len(glob.glob(f"{ROOT}/data/raw/ff_forums.json")), "pages_read": len(stories), "markdown_chars": sum(s["chars"] for s in stories) + len(news_raw["data"]["markdown"]),
               "comments": sum(len(s["thread"]) for s in stories), "opinions": sum(s["gemini"]["kept"] for s in stories),
               "readings": readings, "news_page_readings": news_seen, "dishes": len(dish_list),
               "prompt_tokens": sum((s["gemini"]["trace"].get("prompt_tokens") or 0) for s in stories),
               "output_tokens": sum((s["gemini"]["trace"].get("output_tokens") or 0) for s in stories)},
    "flagship": {"id": FLAGSHIP,
                 "request": {"method": "POST", "endpoint": "https://sdk.nimbleway.com/v2/extract",
                             "body": {"url": flag["url"], "driver": "vx10", "formats": ["markdown"], "browser_actions": [{"wait": 3000}]}},
                 "response": {"url": flag["url"], "task_id": flag["task_id"], "status": flag["status"], "data": {"markdown": excerpt},
                              "metadata": flag["metadata"], "status_code": flag["status_code"]}},
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
s = json.dumps(live, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = re.sub(r'(<script type="application/json" id="live">).*?(</script>)', lambda m: m.group(1) + s + m.group(2), html, count=1, flags=re.S)
html = re.sub(r'(<style id="logos">).*?(</style>)', lambda m: m.group(1) + logo_css + m.group(2), html, count=1, flags=re.S)
open(page, "w").write(html)

skeleton = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta property="og:title" content="MalalphAI: Turning talk into direction">
<meta property="og:description" content="FX forum chatter, extracted by Nimble and interpreted by Gemini, cooked into odds on the US dollar.">
<style>:root{color-scheme:light}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
</head>
<body>
"""
os.makedirs(f"{ROOT}/docs", exist_ok=True)
open(f"{ROOT}/docs/index.html", "w").write(skeleton + html + "\n</body>\n</html>\n")
f = live["funnel"]
print(f"{len(stories)} threads, {f['comments']} comments, {f['opinions']} opinions, {len(dish_list)} dishes, live block {len(s) // 1024}KB")
