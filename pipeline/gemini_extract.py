"""Read a Nimble markdown page and pull out author-dated FX opinions with Gemini.

Usage: python3 pipeline/gemini_extract.py data/raw/ff_story_1430919.json > data/extracted/ff_story_1430919.json
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

MODELS = ["gemini-3.8-flash", "gemini-3.5-flash"]
PAIRS = ["USDEUR", "USDJPY", "USDGBP", "USDCAD"]

PROMPT = """You read forum pages about currencies. The page below was fetched by Nimble at {fetched_at} (UTC).
Find every comment or post that gives a view on where one of these pairs is heading: {pairs}.
Pair convention: USDJPY = yen per 1 US dollar. "up" means the US dollar strengthens against the other currency.
A view on "the dollar" in general applies to all four pairs. A view on EUR/USD going up means USDEUR going down.

For each opinion return:
- author: the username exactly as shown
- comment_id: the number in the comment permalink, if any
- relative_time: the time text shown (e.g. "1 hr 46 min ago")
- quote: the opinion text, short
- pairs: which of {pairs} it applies to
- outlook for horizons 5d, 22d, 66d: probabilities usd_down, sideways, usd_up that sum to 1.
  Sideways means the move stays within 1 standard deviation of normal moves for that horizon.
  With no information the baseline is usd_down 0.16, sideways 0.68, usd_up 0.16. Move away from it only as far as the text justifies.
- reason: one short sentence
Skip jokes, politics without a currency view, and pure questions; list them in skipped with a reason.

PAGE MARKDOWN:
{markdown}
"""

PROB = {"type": "OBJECT", "properties": {k: {"type": "NUMBER"} for k in ["usd_down", "sideways", "usd_up"]},
        "required": ["usd_down", "sideways", "usd_up"]}
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "opinions": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "author": {"type": "STRING"}, "comment_id": {"type": "STRING"}, "relative_time": {"type": "STRING"},
            "quote": {"type": "STRING"}, "pairs": {"type": "ARRAY", "items": {"type": "STRING", "enum": PAIRS}},
            "outlook": {"type": "OBJECT", "properties": {"5d": PROB, "22d": PROB, "66d": PROB}, "required": ["5d", "22d", "66d"]},
            "reason": {"type": "STRING"},
        }, "required": ["author", "quote", "pairs", "outlook", "reason"]}},
        "skipped": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "author": {"type": "STRING"}, "reason": {"type": "STRING"}}}},
    },
    "required": ["opinions", "skipped"],
}


def comments_only(markdown: str) -> str:
    """Drop the site menu; keep the story headline and the comment thread."""
    i = markdown.find("**Comments")
    return markdown[:300] + "\n…\n" + markdown[i:] if i > 0 else markdown


def extract(nimble_result: dict) -> dict:
    md = comments_only(nimble_result["data"]["markdown"])
    prompt = PROMPT.format(fetched_at=nimble_result["metadata"]["query_time"], pairs=", ".join(PAIRS), markdown=md[:60000])
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "responseSchema": SCHEMA, "temperature": 0.2}}
    out, used = None, None
    for attempt in range(6):
        model = MODELS[attempt % len(MODELS)]
        req = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                out, used = json.load(r), model
                break
        except urllib.error.HTTPError as e:
            print(f"{model}: HTTP {e.code}, retrying", file=sys.stderr)
            time.sleep(2 + attempt * 2)
    if out is None:
        raise SystemExit("Gemini unavailable after retries")
    result = json.loads(out["candidates"][0]["content"]["parts"][0]["text"])
    result.update(model=used, source_url=nimble_result["url"], source_task_id=nimble_result["task_id"],
                  fetched_at=nimble_result["metadata"]["query_time"])
    return result


if __name__ == "__main__":
    print(json.dumps(extract(json.load(open(sys.argv[1]))), indent=2, ensure_ascii=False))
