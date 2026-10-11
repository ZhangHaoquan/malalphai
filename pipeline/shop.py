"""Go shopping: Nimble fetches the ForexFactory news page and every story thread with comments,
then Gemini reads each thread. Saves raw pages to data/raw/ and opinions to data/extracted/.

Usage: python3 pipeline/shop.py [max_stories]
"""
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
import gemini_extract  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NEWS = "https://www.forexfactory.com/news"


def nimble_extract(url: str) -> dict:
    body = {"url": url, "driver": "vx10", "formats": ["markdown"], "browser_actions": [{"wait": 3000}]}
    req = urllib.request.Request("https://sdk.nimbleway.com/v2/extract", data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Bearer {os.environ['NIMBLE_API_KEY']}", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                out = json.load(r)
            if out.get("data", {}).get("markdown"):
                return out
        except Exception as e:  # retry transient failures
            print(f"nimble {url}: {e}", file=sys.stderr)
        time.sleep(3)
    raise RuntimeError(f"Nimble failed for {url}")


def story_urls(news_md: str) -> list:
    """Stories that show at least one comment on the news page, newest first."""
    seen, out = set(), []
    for m in re.finditer(r"https://www\.forexfactory\.com/news/(\d+)-[a-z0-9-]+/comment/", news_md):
        sid = m.group(1)
        if sid not in seen:
            seen.add(sid)
            url = re.search(rf"https://www\.forexfactory\.com/news/{sid}-[a-z0-9-]+", news_md).group(0)
            out.append((sid, url))
    return out


FX = re.compile(r"usd|dollar|yen|jpy|eur|euro|pound|gbp|sterling|cable|cad|loonie|canad|fed\b|boj|ecb|boe|boc|cpi|inflation|rate|yield|treasur|oil|fx", re.I)


def currency_stories(news_md: str) -> list:
    """FX-related stories by headline, whether or not comments show on the listing."""
    seen, out = set(), []
    for m in re.finditer(r"\[([^\]]{12,})\]\((https://www\.forexfactory\.com/news/(\d+)-[a-z0-9-]+)\)", news_md):
        title, url, sid = m.groups()
        if sid not in seen and FX.search(title):
            seen.add(sid)
            out.append((sid, url))
    return out


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    t0 = time.time()
    news = nimble_extract(NEWS)
    json.dump(news, open(f"{ROOT}/data/raw/ff_news_latest.json", "w"))
    md = news["data"]["markdown"]
    stories = story_urls(md)
    stories += [s for s in currency_stories(md) if s[0] not in {x[0] for x in stories}]
    stories = stories[:limit]
    print(f"news page: {len(news['data']['markdown'])} chars, {len(stories)} stories with comments")

    def fetch(sid_url):
        sid, url = sid_url
        path = f"{ROOT}/data/raw/ff_story_{sid}.json"
        if not os.path.exists(path):
            json.dump(nimble_extract(url), open(path, "w"))
        return sid, path

    paths = []
    with ThreadPoolExecutor(6) as ex:
        for f in as_completed([ex.submit(fetch, s) for s in stories]):
            try:
                paths.append(f.result())
            except Exception as e:
                print("skip:", e, file=sys.stderr)
    print(f"nimble: {len(paths)} threads in {time.time() - t0:.0f}s")

    def taste(sid_path):
        sid, path = sid_path
        out = f"{ROOT}/data/extracted/ff_story_{sid}.json"
        if os.path.exists(out):
            return sid, "cached"
        res = gemini_extract.extract(json.load(open(path)))
        json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
        return sid, f"{len(res['opinions'])} opinions"

    with ThreadPoolExecutor(5) as ex:
        for f in as_completed([ex.submit(taste, p) for p in paths]):
            try:
                print("gemini:", *f.result())
            except BaseException as e:
                print("gemini skip:", e, file=sys.stderr)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
