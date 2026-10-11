"""Read every fetched page that Gemini hasn't read yet, in priority order, gently (rate limits).

Usage: python3 pipeline/taste_queue.py [workers]
"""
import glob
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(__file__))
import gemini_extract  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def priority(path: str) -> int:
    sid = re.search(r"ff_story_(\w+)\.json", path).group(1)
    return 0 if sid.startswith("t") else 1 if sid.startswith("r") else 2  # forums, then reddit, then news


def taste(path: str) -> str:
    out = path.replace("/raw/", "/extracted/")
    try:
        res = gemini_extract.extract(json.load(open(path)))
        json.dump(res, open(out, "w"), indent=1, ensure_ascii=False)
        return f"{os.path.basename(out)}: {len(res['opinions'])} calls ({res['model']})"
    except BaseException as e:
        return f"{os.path.basename(path)}: failed ({e})"


todo = sorted((p for p in glob.glob(f"{ROOT}/data/raw/ff_story_*.json") if not os.path.exists(p.replace("/raw/", "/extracted/"))), key=priority)
print(len(todo), "pages to read", flush=True)
with ThreadPoolExecutor(int(sys.argv[1]) if len(sys.argv) > 1 else 2) as ex:
    for line in ex.map(taste, todo):
        print(line, flush=True)
