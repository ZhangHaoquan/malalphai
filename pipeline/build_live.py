"""Bundle the saved Nimble + Gemini results into the page's live data block."""
import json
import re

ROOT = __file__.rsplit("/pipeline/", 1)[0]
story = json.load(open(f"{ROOT}/data/raw/ff_story_1430919.json"))
news_raw = json.load(open(f"{ROOT}/data/raw/ff_news_vx10.json"))
g_story = json.load(open(f"{ROOT}/data/extracted/ff_story_1430919.json"))
g_news = json.load(open(f"{ROOT}/data/extracted/ff_news.json"))

md = story["data"]["markdown"]
title = md[: md.find("\n")].strip()
thread = md[md.find("*   **Comments"): md.find("[Manmeetkaur]")].strip()
excerpt = f"# {title}\n\n…\n\n{thread}\n\n… (trimmed for display)"

seen = {}
for page, g in (("story page", g_story), ("news page", g_news)):
    for o in g["opinions"]:
        seen.setdefault(o.get("comment_id") or o["quote"], []).append(
            {"page": page, "author": o["author"], "quote": o["quote"], "model": g["model"]})

live = {
    "nimble_story": {
        "request": {"method": "POST", "endpoint": "https://sdk.nimbleway.com/v2/extract",
                    "body": {"url": story["url"], "driver": "vx10", "formats": ["markdown"], "browser_actions": [{"wait": 3000}]}},
        "response": {"url": story["url"], "task_id": story["task_id"], "status": story["status"],
                     "data": {"markdown": excerpt}, "metadata": story["metadata"], "status_code": story["status_code"]},
        "full_markdown_chars": len(md),
    },
    "nimble_news": {"url": news_raw["url"], "metadata": news_raw["metadata"], "markdown_chars": len(news_raw["data"]["markdown"])},
    "gemini_story": g_story,
    "dedupe": {
        "key": "ForexFactory comment ID (from the permalink)",
        "readings": sum(len(v) for v in seen.values()),
        "unique_comments": len(seen),
        "by_comment_id": seen,
        "result": "Same author, same thread, same view: merged into 1 dish. Probabilities are averaged across the story-page readings.",
    },
}

s = json.dumps(live, ensure_ascii=False).replace("</", "<\\/")
page = f"{ROOT}/mockup/index.html"
html = open(page).read()
html = re.sub(r'(<script type="application/json" id="live">).*?(</script>)', lambda m: m.group(1) + s + m.group(2), html, count=1, flags=re.S)
open(page, "w").write(html)

# GitHub Pages copy: same page wrapped in a full HTML document.
skeleton = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<style>:root{color-scheme:light}body{margin:0;font:14px system-ui,sans-serif}img{max-width:100%}[hidden]{display:none!important}</style>
</head>
<body>
"""
import os
os.makedirs(f"{ROOT}/docs", exist_ok=True)
open(f"{ROOT}/docs/index.html", "w").write(skeleton + html + "\n</body>\n</html>\n")
print("live block:", len(s), "chars;", live["dedupe"]["readings"], "readings ->", live["dedupe"]["unique_comments"], "comments")
