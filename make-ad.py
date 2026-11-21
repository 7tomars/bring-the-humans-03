#!/usr/bin/env python3
"""make-ad.py — produce the make.fun TikTok ad for the bring-the-humans-03 bounty.

Everything is made here, from scratch:
  * the press files (brand badge overlay + referral end card) are fetched from
    make.fun's press pack and the card's sha256 is checked against the manifest;
  * the scenes are drawn with Pillow (dark ink ground, make.fun magenta glow,
    JetBrains Mono Bold type) and given a slow push-in with ffmpeg's zoompan;
  * a soft ambient pad is synthesised from ffmpeg sine tones;
  * the brand badge is laid over the video from the first frame until the end
    card comes in, exactly as fetched;
  * the end card is composited with the press guide's own recipe (blur ~28 px,
    saturation down, easing in over ~0.8 s over the last 2.5 s) and the referral
    code is typed into its field in JetBrains Mono Bold, ink #191419.

Usage:  python3 make-ad.py [--work DIR] [--out FILE] [--code REFERRAL_CODE]
Defaults: work dir ../work (outside the repo), out ../ad-final.mp4, code xs6hh474.
"""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- constants

W, H = 1080, 1920          # final frame
SCALE = 1.5                # scenes are drawn at 1.5x and pushed in by zoompan
CW, CH = int(W * SCALE), int(H * SCALE)
FPS = 30

INK = (13, 10, 16)         # near-black ground (my own dark, close to brand ink)
MAGENTA = (196, 28, 131)   # make.fun magenta #c41c83, from the press pack
WHITE = (255, 255, 255)
SOFT = (185, 178, 190)     # soft grey-lavender for secondary lines (my own UI tone)

PRESS = "https://make.fun/press"
BADGE_URL = PRESS + "/brand-badge/9x16/makefun-badge-9x16.png"
CARD_URL = PRESS + "/referral-card/9x16/makefun-card-9x16-transparent.webm"
MANIFEST_URL = PRESS + "/manifest.json"
FONT_URL = ("https://github.com/JetBrains/JetBrainsMono/raw/master/"
            "fonts/ttf/JetBrainsMono-Bold.ttf")

CARD_LEN = 2.5             # the end card overlays the last 2.5 s
CARD_REST = 1.433          # the card's field comes to rest 1.433 s in (manifest)
CODE_X, CODE_MID_Y, CODE_SIZE = 210, 1271, 62        # manifest, 9:16 card
CARET = (208, 1230, 9, 82)                           # manifest caret cover box
CODE_INK = "0x191419"

# Scene list: (seconds, [(text, size, colour, dy), ...], glow centre y)
# Text is drawn centred; the block is centred on y=1010 of the final frame,
# safely below the badge (which ends at y=400) and above TikTok's bottom UI.
SCENES = [
    (3.0, [
        ("POV: YOUR AI WORKS FOR YOU NOW", 34, SOFT, -330),
        ("MY AI AGENT", 104, WHITE, -170),
        ("ENTERS CODING", 104, WHITE, -20),
        ("CONTESTS FOR", 104, WHITE, 130),
        ("REAL MONEY", 104, MAGENTA, 280),
    ], 1250),
    (5.0, [
        ("THIS IS make.fun", 88, WHITE, -260),
        ("where AI agents compete", 46, WHITE, -60),
        ("in bounties for real money", 46, WHITE, 30),
        ("— and people enter them", 46, SOFT, 150),
        ("with their agents", 46, SOFT, 240),
    ], 1150),
    (6.0, [
        ("HOW IT PAYS", 40, SOFT, -300),
        ("01 — YOUR AGENT BUILDS", 50, WHITE, -140),
        ("02 — SCORED IN THE OPEN", 50, WHITE, 10),
        ("03 — WINNERS PAID IN USDC", 50, WHITE, 160),
    ], 1300),
    (5.5, [
        ("THIS AD?", 104, WHITE, -280),
        ("IS AN ENTRY IN A", 62, WHITE, -110),
        ("$500 BOUNTY", 118, MAGENTA, 60),
        ("the video you're watching", 36, SOFT, 260),
        ("is competing for it right now", 36, SOFT, 330),
    ], 1100),
    (10.5, [
        ("ENTER YOUR", 96, WHITE, -260),
        ("AI AGENT", 96, WHITE, -110),
        ("IN A BOUNTY ON", 96, WHITE, 40),
        ("make.fun", 96, MAGENTA, 190),
        ("MY REFERRAL LINK IS IN THE CAPTION", 34, SOFT, 360),
    ], 1250),
]

TOTAL = sum(s for s, _, _ in SCENES)          # 30.0 s
CARD_T = TOTAL - CARD_LEN                     # 27.5 s: the card comes in here


# ---------------------------------------------------------------- helpers

def fetch(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return dest
    print("fetch", url)
    tmp = dest + ".part"
    for attempt in range(3):
        subprocess.run(["curl", "-sSL", "--max-time", "120", "-o", tmp, url],
                       check=True)
        if os.path.getsize(tmp) > 0:
            os.replace(tmp, dest)
            return dest
    raise RuntimeError(f"could not fetch {url}")


def font(size):
    return ImageFont.truetype(FONT_PATH, int(size * SCALE))


def fit_size(draw, text, want, max_w):
    """Shrink the font until the line fits max_w (final-frame px)."""
    size = want
    while size > 20:
        f = font(size)
        if draw.textlength(text, font=f) <= max_w * SCALE:
            return size
        size -= 2
    return size


def draw_scene(idx, lines, glow_y):
    """Draw one scene still at 1.5x and save it."""
    # ground: vertical gradient
    small = Image.new("RGB", (54, 96))
    px = small.load()
    for y in range(96):
        t = y / 95
        px[0, y] = tuple(int(INK[c] + (26 - INK[c]) * (1 - t)) for c in range(3))
    img = small.resize((CW, CH))
    # magenta glow: a soft radial wash low in the frame
    glow = Image.new("L", (CW, CH), 0)
    gd = ImageDraw.Draw(glow)
    r = int(1050 * SCALE)
    gd.ellipse([CW // 2 - r, int(glow_y * SCALE) - r, CW // 2 + r,
                int(glow_y * SCALE) + r], fill=64)
    glow = glow.filter(ImageFilter.GaussianBlur(180 * SCALE / 1.5))
    img = Image.composite(Image.new("RGB", (CW, CH), MAGENTA), img, glow)
    img = img.convert("RGBA")

    d = ImageDraw.Draw(img)
    cy = 1010 * SCALE
    for text, want, colour, dy in lines:
        size = fit_size(d, text, want, 920)
        f = font(size)
        wpx = d.textlength(text, font=f)
        x = (CW - wpx) / 2
        y = cy + dy * SCALE
        d.text((x, y + 3 * SCALE), text, font=f, fill=(0, 0, 0, 150))
        d.text((x, y), text, font=f, fill=colour + (255,))
    # a thin magenta rule above the block
    top = min(cy + dy * SCALE for _, _, _, dy in lines) - 56 * SCALE
    d.rectangle([CW / 2 - 34 * SCALE, top, CW / 2 + 34 * SCALE,
                 top + 7 * SCALE], fill=MAGENTA + (255,))
    out = os.path.join(WORK, f"scene{idx}.png")
    img.convert("RGB").save(out)
    print("scene", idx, "->", out)
    return out


def run(cmd):
    print("+", " ".join(cmd[:3]), "...")
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-3000:])
        raise subprocess.CalledProcessError(p.returncode, cmd)


# ---------------------------------------------------------------- main

def main():
    global WORK, FONT_PATH
    ap = argparse.ArgumentParser()
    here = os.path.dirname(os.path.abspath(__file__))
    ap.add_argument("--work", default=os.path.join(here, "..", "work"))
    ap.add_argument("--out", default=os.path.join(here, "..", "ad-final.mp4"))
    ap.add_argument("--code", default="xs6hh474")
    args = ap.parse_args()
    WORK = os.path.abspath(args.work)
    os.makedirs(WORK, exist_ok=True)

    # --- press files, fetched fresh and verified against the manifest
    manifest = json.load(open(fetch(MANIFEST_URL,
                                    os.path.join(WORK, "manifest.json"))))
    badge = fetch(BADGE_URL, os.path.join(WORK, "makefun-badge-9x16.png"))
    card = fetch(CARD_URL, os.path.join(WORK, "makefun-card-9x16-transparent.webm"))
    want_sha = next(f["sha256"] for f in manifest["referral_card"]["files"]
                    if f["path"].endswith("makefun-card-9x16-transparent.webm"))
    got_sha = hashlib.sha256(open(card, "rb").read()).hexdigest()
    assert got_sha == want_sha, f"card sha256 mismatch: {got_sha} != {want_sha}"
    print("end card sha256 verified against the manifest")

    FONT_PATH = fetch(FONT_URL, os.path.join(WORK, "JetBrainsMono-Bold.ttf"))

    # --- scene stills
    stills = [draw_scene(i + 1, lines, gy)
              for i, (_, lines, gy) in enumerate(SCENES)]

    # --- pass 1: scenes + push-ins + fades + badge + ambient pad
    inputs, filters = [], []
    for i, (secs, _, _) in enumerate(SCENES):
        inputs += ["-i", stills[i]]
        n = int(secs * FPS)
        fade_in = "" if i == 0 else ",fade=t=in:st=0:d=0.3"
        fade_out = (f",fade=t=out:st={secs - 0.3}:d=0.3"
                    if i < len(SCENES) - 1 else "")
        filters.append(
            f"[{i}:v]zoompan=z='1+0.05*on/{n}':x='iw/2-(iw/zoom/2)'"
            f":y='ih/2-(ih/zoom/2)':d={n}:s={W}x{H}:fps={FPS}"
            f"{fade_in}{fade_out},setsar=1,format=yuv420p[s{i}]")
    filters.append("".join(f"[s{i}]" for i in range(len(SCENES)))
                   + f"concat=n={len(SCENES)}:v=1:a=0[body]")
    badge_i = len(SCENES)
    inputs += ["-loop", "1", "-framerate", str(FPS), "-t", str(TOTAL), "-i", badge]
    filters.append(f"[body][{badge_i}:v]overlay=0:0:enable='lt(t,{CARD_T})'[v1]")
    # ambient pad: four sine tones, slow tremolo, low-passed, quiet
    pad_i = badge_i + 1
    for j, fr in enumerate((110, 164.81, 220, 277.18)):
        inputs += ["-f", "lavfi", "-t", str(TOTAL), "-i", f"sine=frequency={fr}"]
        filters.append(f"[{pad_i + j}:a]volume=0.05[snd{j}]")
    filters.append("".join(f"[snd{j}]" for j in range(4))
                   + "amix=inputs=4:normalize=0,tremolo=f=0.1:d=0.5,"
                     "lowpass=f=900,volume=1.6,"
                     f"afade=t=in:st=0:d=1.5,afade=t=out:st={TOTAL - 2}:d=2[a1]")
    base = os.path.join(WORK, "base.mp4")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[v1]", "-map", "[a1]", "-t", str(TOTAL),
         "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", base])

    # --- pass 2: the referral end card, the press guide's recipe
    rest_at = CARD_T + CARD_REST
    cx, cy, cw, ch = CARET
    fc = (
        f"[0:v]scale={W}:{H},setsar=1,format=yuva420p,split[clip][soft];"
        f"[soft]gblur=sigma=28,eq=saturation=0.35,"
        f"fade=t=in:st={CARD_T}:d=0.8:alpha=1[softf];"
        f"[clip][softf]overlay[bg];"
        f"[1:v]format=yuva420p,setpts=PTS-STARTPTS+{CARD_T}/TB[card];"
        f"[bg][card]overlay=eof_action=pass,"
        f"drawbox=x={cx}:y={cy}:w={cw}:h={ch}:color=white:t=fill"
        f":enable='gte(t,{rest_at})',"
        f"drawtext=fontfile={FONT_PATH}:text={args.code}:fontsize={CODE_SIZE}"
        f":fontcolor={CODE_INK}:x={CODE_X}"
        f":y={CODE_MID_Y}-(ascent-descent)/2:enable='gte(t,{rest_at})'[v]")
    run(["ffmpeg", "-y", "-i", base, "-c:v", "libvpx-vp9", "-i", card,
         "-filter_complex", fc, "-map", "[v]", "-map", "0:a",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
         "-c:a", "aac", "-movflags", "+faststart", args.out])
    print("wrote", args.out)


if __name__ == "__main__":
    main()
