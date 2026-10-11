"""60-second cut: Gemini TTS narration, punch-in zooms, flash cuts, burned-in captions and a ducked beat.

Run video/render.py once first (it captures the product screenshots this cut reuses).
Usage: python3 video/render60.py  ->  video/out/malalphai_60s.mp4
"""
import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = f"{HERE}/out"
TTS = f"{OUT}/tts"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
FFMPEG, FFPROBE = "/opt/homebrew/bin/ffmpeg", "/opt/homebrew/bin/ffprobe"

STYLE = "Say quickly and excitedly, like a hype YouTube narrator, with no pauses: "
NARR, MAX, CLAUDE = "Puck", "Fenrir", "Kore"
F = json.loads(re.search(r'id="live">(.*?)</script>', open(os.path.join(os.path.dirname(HERE), "docs", "index.html")).read(), re.S).group(1).replace("<\\/", "</"))["funnel"]

# (scene, step, voice, spoken line, caption; *word* = highlighted, shake=True for impact panels)
BEATS = [
    (1, 99, NARR, "Ma La Alpha AI: turning talk into direction!", "Turning talk into *direction*", False),
    (3, 2, MAX, "Sell USD? Gold up? I see orange?! Who do I even trust?!", "Forums: all chatter, no *track record*", True),
    (4, 2, NARR, "Nimble goes shopping: stealth browser, straight through the bot wall, clean markdown in seconds.", "*Nimble* gets past the bot wall", True),
    (5, 3, NARR, "Gemini tastes every comment. Joke? Skip. Politics? Skip. Sell USD, no rate hike? That's a call, with odds.", "*Gemini* keeps the calls, skips the noise", True),
    (6, 99, NARR, "And it keeps the why.", "Not just what. *Why.*", False),
    (7, 99, NARR, f"Today: {F['pages']} pages, {F['comments']} comments, {F['opinions']} real calls, one Bayesian pot.", f"{F['pages']} pages → {F['comments']} comments → *{F['opinions']} calls*", True),
    (9, 3, NARR, "Every number has a receipt: thread, trace, lineage.", "Every number has a *receipt*", False),
    (10, 2, NARR, "Then you season it. Back the chefs who've been right, and watch the odds move.", "You *season* the pot", False),
    (11, 1, CLAUDE, "I'm Claude, I helped cook this. Next: a leaderboard of who really knows the dollar.", "Next: who *really* knows the dollar", False),
    (12, 99, NARR, "Ma La Alpha AI. Extracted by Nimble. Interpreted by Gemini.", "", False),
]


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def duration(path):
    out = subprocess.run([FFPROBE, "-v", "quiet", "-print_format", "json", "-show_format", path], capture_output=True, text=True).stdout
    return float(json.loads(out)["format"]["duration"])


def tts(text, voice, path):
    if os.path.exists(path):
        return
    style = STYLE if voice != CLAUDE else "Say warmly and briskly, like a friendly, confident engineer: "
    body = {"contents": [{"parts": [{"text": style + text}]}],
            "generationConfig": {"responseModalities": ["AUDIO"], "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    for attempt in range(12):
        model = ["gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"][attempt % 3]
        req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                     data=json.dumps(body).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": os.environ["GEMINI_API_KEY"]})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                part = json.load(r)["candidates"][0]["content"]["parts"][0]["inlineData"]
            data = base64.b64decode(part["data"])
            if not data.startswith(b"RIFF"):  # raw 24 kHz PCM from some models: wrap it as WAV
                raw = path + ".pcm"
                open(raw, "wb").write(data)
                run(FFMPEG, "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", raw, path)
                return
            open(path, "wb").write(data)
            return
        except urllib.error.HTTPError as e:
            print(f"tts {model}: HTTP {e.code}, retrying", flush=True)
            time.sleep(8 if e.code == 429 else 2)
    raise SystemExit("TTS unavailable")


def main():
    os.makedirs(TTS, exist_ok=True)
    segs = []
    for i, (scene, step, voice, line, cap, shake) in enumerate(BEATS):
        wav, png, mp4 = f"{TTS}/b{i:02d}.wav", f"{OUT}/q{i:02d}.png", f"{OUT}/q{i:02d}.mp4"
        tts(line, voice, wav)
        url = f"file://{HERE}/comic.html?scene={scene}&step={step}" + (f"&cap={urllib.parse.quote(cap)}" if cap else "")
        run(CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--allow-file-access-from-files",
            "--window-size=1920,1300", "--virtual-time-budget=5000", f"--screenshot={png}.tall.png", url)
        run(FFMPEG, "-y", "-i", f"{png}.tall.png", "-vf", "crop=1920:1080:0:0", png)
        # Trim the TTS lead-in/out silence and nudge the pace up a touch.
        clean = f"{TTS}/c{i:02d}.wav"
        run(FFMPEG, "-y", "-i", wav, "-af",
            "silenceremove=start_periods=1:start_threshold=-45dB:stop_periods=-1:stop_duration=0.3:stop_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse,atempo=1.1",
            "-ar", "48000", "-ac", "2", clean)
        d = max(duration(clean) + 0.6, 2.8)
        frames = int(d * 30)
        jitter = "+if(lt(on,9),14*sin(on*2.3),0)" if shake else ""
        vf = (f"[0:v]scale=2304:1296,zoompan=z='1+0.07*(1-exp(-on/7))+0.0004*on':"
              f"x='iw/2-(iw/zoom/2){jitter}':y='ih/2-(ih/zoom/2){jitter}':d={frames}:s=1920x1080:fps=30,"
              f"fade=t=in:st=0:d=0.12:color=white,format=yuv420p[v];[1:a]apad=pad_dur=3[a]")
        run(FFMPEG, "-y", "-loop", "1", "-i", png, "-i", clean, "-filter_complex", vf, "-map", "[v]", "-map", "[a]",
            "-t", f"{d:.2f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", mp4.replace(".mp4", ".mkv"))
        segs.append(mp4.replace(".mp4", ".mkv"))
        print(f"beat {i} {d:.1f}s")

    with open(f"{OUT}/concat60.txt", "w") as f:
        f.writelines(f"file '{s}'\n" for s in segs)
    base = f"{OUT}/base60.mkv"
    run(FFMPEG, "-y", "-f", "concat", "-safe", "0", "-i", f"{OUT}/concat60.txt", "-c", "copy", base)
    total = duration(base)

    # 120 bpm beat: kick on every beat, hat on the off-beat, a pulsing bass line.
    music = f"{OUT}/beat.wav"
    expr = ("0.55*sin(2*PI*(50+120*exp(-30*mod(t,0.5)))*t)*exp(-9*mod(t,0.5))"
            "+0.10*(random(0)*2-1)*exp(-70*mod(t+0.25,0.5))"
            "+0.16*sin(2*PI*if(lt(mod(t,4),2),55,73.4)*t)*(0.6+0.4*sin(2*PI*2*t))")
    run(FFMPEG, "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=48000:d={total:.2f}", "-af", "lowpass=f=5000,afade=t=out:st=" + f"{total - 1.5:.2f}" + ":d=1.5", "-ac", "2", music)

    final = f"{OUT}/malalphai_60s.mp4"
    run(FFMPEG, "-y", "-i", base, "-i", music, "-filter_complex",
        "[1:a]volume=0.32[m];[0:a]asplit=2[v1][v2];[m][v1]sidechaincompress=threshold=0.03:ratio=6:attack=10:release=300[md];"
        "[v2][md]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-15:TP=-1.5[a]",
        "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", final)
    print("wrote", final, f"{duration(final):.1f}s")


if __name__ == "__main__":
    main()
