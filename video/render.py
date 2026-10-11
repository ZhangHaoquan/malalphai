"""Render the MalalphAI comic demo video: panels (headless Chrome) + voice (macOS say) -> MP4 (ffmpeg).

Usage: python3 video/render.py   ->  video/out/malalphai_demo.mp4
"""
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = f"{HERE}/out"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
FFPROBE = "/opt/homebrew/bin/ffprobe"
SITE = "https://zhanghaoquan.github.io/malalphai/"

NARR, MAX, CLAUDE = "Daniel", "Eddy (English (US))", "Flo (English (US))"
NAME = "Mahlalf A.I."

DOCS = os.path.join(os.path.dirname(HERE), "docs", "index.html")
LIVE = json.loads(re.search(r'<script type="application/json" id="live">(.*?)</script>', open(DOCS).read(), re.S).group(1).replace("<\\/", "</"))
F = LIVE["funnel"]


def beats():
    return [
        (1, 99, NARR, f"{NAME}. Turning talk into direction."),
        (2, 99, NARR, "Monday morning, New York. Max trades the dollar. And like every trader, Max starts the day on the forums."),
        (3, 2, MAX, "Sell U.S.D.? Gold up? I see orange?? And who do I even trust?"),
        (3, 3, NARR, "Eighteen comments. Two real calls. Zero track records. Sound familiar?"),
        (4, 1, NARR, "So Max sends Nimble shopping. The forum hides behind a bot wall."),
        (4, 2, NARR, "Nimble's stealth browser goes straight through it, and brings back the whole thread as clean markdown. Five point six seconds."),
        (5, 1, NARR, "Then Gemini tastes every comment. I see orange? A joke. Skip."),
        (5, 2, NARR, "Politics? Skip."),
        (5, 3, NARR, "Sell U.S.D., oil down, no rate hike? Now that's a call. Dollar down, with odds for five, twenty two, and sixty six days."),
        (6, 99, NARR, "And Gemini keeps the reasoning. Oil down, inflation down, no hike, dollar down. So Max can argue with the logic, not just the vibe."),
        (7, 99, NARR, f"Today's shop: {F['pages']} pages from Forex Factory and Reddit. {F['comments']} comments. {F['opinions']} real currency calls. A Bayesian update turns them into odds, for four pairs and three horizons."),
        (8, 99, NARR, "The pulse shows Gemini's judgment at scale. When the chatter happened, why comments were skipped, and how much the crowd agrees."),
        (9, 1, NARR, "Click any dish for its receipt. The thread, exactly as Nimble extracted it, with Gemini's verdict on every comment."),
        (9, 2, NARR, "A trace, with real latencies and tokens."),
        (9, 3, NARR, "And lineage, all the way back to the source. Nerds welcome."),
        (10, 1, NARR, "Then you season it. This is the default pot."),
        (10, 2, NARR, "Trust one chef more, mute another, and My pot shows exactly how the odds move."),
        (11, 1, CLAUDE, "Hi, I'm Claude. I helped cook this. Score every author against real outcomes, and you get a public leaderboard of who actually knows the dollar."),
        (11, 2, CLAUDE, "Read every forum, in every language, with Nimble's geo targeting. Run the same recipe on oil, gold and rates. And you have a sentiment desk that shows its work."),
        (12, 99, NARR, f"{NAME}. Extracted by Nimble. Interpreted by Gemini. Turning talk into direction."),
    ]


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def chrome_shot(url, path, w, h, budget=6000):
    run(CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
        f"--window-size={w},{h}", f"--virtual-time-budget={budget}", f"--screenshot={path}", url)


def duration(path):
    out = subprocess.run([FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def main():
    os.makedirs(OUT, exist_ok=True)
    # Real screenshots of the built page (docs/index.html) for the product scenes.
    url = "file://" + DOCS
    def page_shot(name, suffix, w, h, crop):
        chrome_shot(url + suffix, f"{OUT}/{name}_full.png", w, h + 200)
        run(FFMPEG, "-y", "-i", f"{OUT}/{name}_full.png", "-vf", f"crop={crop}", f"{OUT}/{name}.png")
    page_shot("shot_pot", "?only=pot-section", 1100, 820, "1100:560:0:0")
    page_shot("shot_pulse", "?only=pulse-section", 980, 820, "980:400:0:0")
    for tab in ("thread", "trace", "lineage"):
        page_shot(f"shot_{tab}", "#" + tab, 1000, 700, "976:668:12:16")
    chefs = {}
    for d in LIVE["dishes"]:
        chefs[d["author"]] = chefs.get(d["author"], 0) + 1
    top = sorted(chefs, key=chefs.get, reverse=True)
    boost = next((a for a in top if a != "eqshack"), top[0])
    season = f"eqshack:0:1:1,{boost}:1.5:2:2"  # mute the all-pairs dollar bear, back the busiest chef
    page_shot("shot_default", "?only=pot-section", 900, 620, "900:330:0:0")
    page_shot("shot_mine", f"?only=pot-section&season={season}", 900, 620, "900:330:0:0")

    for f in os.listdir(OUT):
        if re.match(r"[psv]\d\d\.", f):
            os.remove(f"{OUT}/{f}")
    segs = []
    for i, (scene, step, voice, line) in enumerate(beats()):
        png, aiff, mp4 = f"{OUT}/p{i:02d}.png", f"{OUT}/v{i:02d}.aiff", f"{OUT}/s{i:02d}.mp4"
        # Headless Chrome's viewport is shorter than the window, so render tall and crop to 1080p.
        chrome_shot(f"file://{HERE}/comic.html?scene={scene}&step={step}", png + ".tall.png", 1920, 1300)
        run(FFMPEG, "-y", "-i", png + ".tall.png", "-vf", "crop=1920:1080:0:0", png)
        run("say", "-v", voice, "-r", {NARR: "186", MAX: "195"}.get(voice, "182"), "-o", aiff, line)
        d = duration(aiff) + 0.45
        frames = int(d * 30)
        # Slow push-in on each panel; audio padded so lines don't clip.
        run(FFMPEG, "-y", "-loop", "1", "-i", png, "-i", aiff,
            "-filter_complex",
            f"[0:v]scale=2304:1296,zoompan=z='min(1+0.0006*on,1.06)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps=30,format=yuv420p[v];"
            f"[1:a]apad=pad_dur=0.45,aresample=48000[a]",
            "-map", "[v]", "-map", "[a]", "-t", f"{d:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", mp4)
        segs.append(mp4)
        print(f"beat {i:02d} scene {scene}.{step} {d:.1f}s")

    with open(f"{OUT}/concat.txt", "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    final = f"{OUT}/malalphai_demo.mp4"
    run(FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", f"{OUT}/concat.txt", "-c", "copy", "-movflags", "+faststart", final)
    print("wrote", final, f"{duration(final):.1f}s")


if __name__ == "__main__":
    main()
