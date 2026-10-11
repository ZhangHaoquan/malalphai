"""Shop r/Forex through Reddit's official RSS feeds (fetched by Nimble), then read them with Gemini.

Each feed is saved as a Nimble result with an extra data.markdown built from the feed entries,
so the same Gemini step and page builder work on it.
Usage: python3 pipeline/reddit.py
"""
import html
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
import gemini_extract  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FX = re.compile(r"eur|usd|jpy|gbp|cad|cable|yen|dollar|loonie", re.I)


def nimble_rss(url: str) -> dict:
    body = {"url": url, "driver": "vx6", "formats": ["html"]}
    req = urllib.request.Request("https://sdk.nimbleway.com/v2/extract", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {os.environ['NIMBLE_API_KEY']}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)


def entries(feed_html: str) -> list:
    out = []
    for e in re.findall(r"<entry>(.*?)</entry>", feed_html, re.S):
        get = lambda p: (re.search(p, e, re.S) or [None, ""])[1]
        content = html.unescape(get(r"<content[^>]*>(.*?)</content>"))
        text = re.sub(r"<[^>]+>", " ", html.unescape(content))
        text = re.sub(r"\s+", " ", text.replace("submitted by", "\nsubmitted by")).split("\nsubmitted by")[0].strip()
        out.append({"id": get(r"<id>(.*?)</id>").split("_")[-1], "author": get(r"<name>/u/(.*?)</name>"),
                    "at": get(r"<updated>(.*?)</updated>")[:16] + "Z", "title": html.unescape(get(r"<title>(.*?)</title>")),
                    "link": get(r'<link href="([^"]+)"'), "text": text[:1500]})
    return out


def to_markdown(title: str, items: list) -> str:
    parts = [f"# {title}\n"]
    for it in items:
        parts.append(f"**{it['author']}** · {it['at']} · id {it['id']}\n\n{it['title']}\n\n{it['text']}\n\n---\n")
    return "\n".join(parts)


def save(name: str, url: str, title: str) -> tuple:
    res = nimble_rss(url)
    items = entries(res["data"]["html"])
    res["data"] = {"markdown": to_markdown(title, items), "html_chars": len(res["data"]["html"])}
    path = f"{ROOT}/data/raw/ff_story_{name}.json"  # same naming so the builder picks it up
    json.dump(res, open(path, "w"))
    print(name, len(items), "entries")
    return path, items


def taste(path: str) -> str:
    out = path.replace("/raw/", "/extracted/")
    try:
        json.dump(gemini_extract.extract(json.load(open(path))), open(out, "w"), indent=1, ensure_ascii=False)
        return os.path.basename(out)
    except BaseException as e:
        return f"skip {os.path.basename(path)}: {e}"


def main():
    path, feed = save("rforex", "https://www.reddit.com/r/Forex/new/.rss?limit=50", "r/Forex · newest posts")
    paths = [path]
    for e in [e for e in feed if FX.search(e["title"])][:4]:
        pid = e["link"].split("/comments/")[1].split("/")[0]
        paths.append(save(f"r{pid}", e["link"].rstrip("/") + "/.rss", f"r/Forex · {e['title']}")[0])
    with ThreadPoolExecutor(3) as ex:
        for f in ex.map(taste, paths):
            print("gemini:", f)


if __name__ == "__main__":
    main()
