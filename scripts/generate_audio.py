#!/usr/bin/env python3
"""daily/*.md から未生成分の読み上げ音声 (docs/audio/*.mp3) を OpenAI TTS で生成する。"""
import glob
import json
import os
import re
import subprocess
import tempfile
import urllib.request

MODEL = os.environ.get("TTS_MODEL", "gpt-4o-mini-tts")
VOICE = os.environ.get("TTS_VOICE", "nova")
INSTRUCTIONS = (
    "落ち着いたラジオパーソナリティとして、明瞭で聞き取りやすい日本語で"
    "ニュースを読み上げてください。テンポはゆったりめ、固有名詞は自然な英語発音で。"
)
CHUNK_LIMIT = 3000  # APIの入力上限4096文字に対する安全マージン


def clean(s):
    s = re.sub(r"https?://[^\s),、]+", "", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[\U0001F300-\U0001FAFF☀-➿⬀-⯿]", "", s)
    s = s.replace("×", "と").replace("✕", "と")
    return re.sub(r"\s+", " ", s).strip()


def build_script(md, date_str):
    y, m, d = (int(x) for x in date_str.split("-"))
    parts = [f"AIニュース、{y}年{m}月{d}日号です。"]
    section = 0
    in_code = False
    for raw in md.split("\n"):
        line = raw.strip()
        if line.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line or line.startswith("# ") or line.startswith(">"):
            continue
        if line.startswith("## "):
            name = clean(line[3:])
            parts.append(("まずは、" if section == 0 else "続いて、") + name + "の話題です。")
            section += 1
        elif line.startswith("### "):
            parts.append(clean(line[4:]) + "。")
        elif line.startswith("- "):
            item = line[2:]
            if re.match(r"^情報源", item):
                continue
            if re.match(r"^\*?\*?活用ポイント", item):
                t = "活用ポイント。" + clean(re.sub(r"^\*\*活用ポイント[:：]?\*\*\s*", "", item))
            else:
                t = clean(re.sub(r"^要約[:：]\s*", "", item))
            if t:
                parts.append(t)
        else:
            t = clean(line)
            if t:
                parts.append(t)
    parts.append("以上、本日のAIニュースでした。")
    return parts


def chunks(parts):
    buf = ""
    for p in parts:
        if buf and len(buf) + len(p) + 1 > CHUNK_LIMIT:
            yield buf
            buf = p
        else:
            buf = f"{buf}\n{p}" if buf else p
    if buf:
        yield buf


def tts(text, out_path):
    body = json.dumps(
        {
            "model": MODEL,
            "voice": VOICE,
            "input": text,
            "instructions": INSTRUCTIONS,
            "response_format": "mp3",
        }
    ).encode()
    req = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=body,
        headers={
            "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as r, open(out_path, "wb") as f:
        f.write(r.read())


def main():
    os.makedirs("docs/audio", exist_ok=True)
    for md_path in sorted(glob.glob("daily/*.md")):
        date_str = os.path.basename(md_path)[:-3]
        out = f"docs/audio/{date_str}.mp3"
        if os.path.exists(out):
            continue
        with open(md_path) as f:
            md = f.read()
        parts = build_script(md, date_str)
        with tempfile.TemporaryDirectory() as tmp:
            segs = []
            for i, ch in enumerate(chunks(parts)):
                seg = os.path.join(tmp, f"{i}.mp3")
                tts(ch, seg)
                segs.append(seg)
            if len(segs) == 1:
                cmd = ["ffmpeg", "-y", "-i", segs[0]]
            else:
                lst = os.path.join(tmp, "list.txt")
                with open(lst, "w") as f:
                    f.writelines(f"file '{p}'\n" for p in segs)
                cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst]
            subprocess.run(
                cmd + ["-c:a", "libmp3lame", "-b:a", "96k", out],
                check=True,
                capture_output=True,
            )
        print("generated", out)


if __name__ == "__main__":
    main()
