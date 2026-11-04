"""Footage helpers for an agent that can't watch video: probe, normalize, look at, check, share.

usage: uv run --no-project --with pillow python -I footage.py COMMAND ...

  probe FILE...                       one line per file plus WARN lines: HDR, rotation, variable frame
                                      rate, odd dimensions, no audio. Run it on anything you're handed.
  proxy IN OUT [--fps 30] [--max 1920]
                                      a clean working copy: SDR (HDR tone-mapped), rotation baked in,
                                      constant frame rate, even dimensions, H.264 yuv420p, AAC 48 kHz,
                                      faststart. Look at and cut from the proxy; keep the original.
  frames IN OUT [--scene 0.3] [--every 4] [--max 60] [--cols 5] [--rows 6] [--tile 380]
                                      contact sheets of the moments that matter: a frame at every scene
                                      change, and at least one every N seconds. Tiles are labeled
                                      "id · m:ss.s"; OUT/manifest.json maps id -> time and sheet
                                      (check_verdicts.py reads it).
  check FILE [--duration S] [--target -16]
                                      delivery check: codec, yuv420p, even size, constant frame rate,
                                      faststart, duration, loudness (EBU R128) and true peak. Exit 1 on FAIL.
  gif IN OUT.gif [--fps 12] [--width 640] [--start 0] [--duration 6]
                                      a GIF with a generated palette (no banding, small files)
  share IN OUT.mp4 [--width 1280] [--crf 28]
                                      a small copy for showing someone (a web page, a chat), never the master

Needs ffmpeg/ffprobe on PATH. HDR tone-mapping uses macOS's avconvert, else ffmpeg's zscale.
"""
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HDR_TRANSFERS = {"arib-std-b67": "HLG", "smpte2084": "PQ"}


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def opt(args, name, default, cast=float):
    if name in args:
        i = args.index(name)
        val = args[i + 1]
        del args[i:i + 2]
        return cast(val)
    return default


def ffprobe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    if r.returncode:
        sys.exit(f"ffprobe failed on {path}: {r.stderr.strip()}")
    return json.loads(r.stdout)


def rate(s):
    try:
        n, d = s.split("/")
        return float(n) / float(d) if float(d) else 0.0
    except Exception:
        return 0.0


def info(path):
    p = ffprobe(path)
    v = next((s for s in p["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in p["streams"] if s["codec_type"] == "audio"), None)
    rot = 0
    if v:
        for sd in v.get("side_data_list", []):
            if "rotation" in sd:
                rot = int(sd["rotation"])
        rot = rot or int(v.get("tags", {}).get("rotate", 0) or 0)
    return {
        "path": str(path), "duration": float(p["format"].get("duration", 0) or 0), "video": v, "audio": a,
        "w": v and v["width"], "h": v and v["height"], "rotation": rot,
        "r_fps": v and rate(v.get("r_frame_rate", "0/1")), "avg_fps": v and rate(v.get("avg_frame_rate", "0/1")),
        "hdr": v and HDR_TRANSFERS.get(v.get("color_transfer", "")),
    }


def warnings(i):
    w = []
    if not i["video"]:
        return ["no video stream"]
    if i["hdr"]:
        w.append(f"HDR ({i['hdr']}, {i['video'].get('color_primaries')}): frames look washed out and miscolored "
                 f"unless tone-mapped; run proxy before looking")
    if i["rotation"]:
        w.append(f"rotation {i['rotation']}: stored sideways; players and ffmpeg rotate it, some tools don't")
    if i["r_fps"] and i["avg_fps"] and abs(i["r_fps"] - i["avg_fps"]) > 0.001:
        w.append(f"variable frame rate (nominal {i['r_fps']:.3f}, average {i['avg_fps']:.3f}): timestamps drift; proxy fixes it")
    if i["w"] % 2 or i["h"] % 2:
        w.append("odd width or height: H.264 yuv420p needs even dimensions")
    if not i["audio"]:
        w.append("no audio stream")
    return w


def cmd_probe(args):
    for f in args:
        i = info(f)
        v = i["video"] or {}
        a = i["audio"]
        print(f"{f}\t{i['duration']:.2f}s\t{i['w']}x{i['h']}\t{v.get('codec_name')}\t{v.get('pix_fmt')}\t"
              f"{i['avg_fps']:.3f} fps\t{v.get('color_transfer', '?')}\t"
              f"{'audio ' + a['codec_name'] + ' ' + a.get('sample_rate', '') + ' Hz' if a else 'no audio'}")
        for w in warnings(i):
            print(f"  WARN {w}")


def has_filter(name):
    return re.search(rf"\b{name}\b", run(["ffmpeg", "-hide_banner", "-filters"]).stdout) is not None


def cmd_proxy(args):
    fps, mx = opt(args, "--fps", 30), int(opt(args, "--max", 1920))
    src, out = Path(args[0]), Path(args[1])
    i = info(src)
    tmp = None
    vf = []
    if i["hdr"]:
        if shutil.which("avconvert"):  # macOS: tone-maps to SDR BT.709 and bakes the rotation in
            tmp = Path(tempfile.mkdtemp()) / "sdr.mov"
            preset = "Preset1920x1080" if mx <= 1920 else "Preset3840x2160"
            r = run(["avconvert", "--preset", preset, "--source", str(src), "--output", str(tmp), "--replace"])
            if r.returncode or not tmp.exists():
                sys.exit(f"avconvert failed: {r.stderr.strip() or r.stdout.strip()}")
            src = tmp
        elif has_filter("zscale"):
            vf.append("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,"
                      "zscale=t=bt709:m=bt709:r=tv")
        else:
            print("WARN HDR source but neither avconvert nor ffmpeg zscale is available: colors will be off",
                  file=sys.stderr)
    vf += [f"scale={mx}:{mx}:force_original_aspect_ratio=decrease", "scale=trunc(iw/2)*2:trunc(ih/2)*2:out_range=limited",
           "format=yuv420p"]
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-vf", ",".join(vf),
           "-fps_mode", "cfr", "-r", f"{fps:g}", "-c:v", "libx264", "-crf", "20", "-preset", "medium",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
           "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-map_metadata", "-1", "-movflags", "+faststart", str(out)]
    r = run(cmd)
    if tmp:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    if r.returncode:
        sys.exit(f"ffmpeg failed: {r.stderr.strip()}")
    cmd_probe([str(out)])


def fmt_t(t):
    return f"{int(t // 60)}:{t % 60:04.1f}"


def cmd_frames(args):
    scene, every, mx = opt(args, "--scene", 0.3), opt(args, "--every", 4), int(opt(args, "--max", 60))
    cols, rows, tile = int(opt(args, "--cols", 5)), int(opt(args, "--rows", 6)), int(opt(args, "--tile", 380))
    src, out = Path(args[0]), Path(args[1])
    i = info(src)
    if i["hdr"]:
        print(f"WARN {src} is HDR: these frames will look washed out. Make a proxy first.", file=sys.stderr)
    fdir = out / "frames"
    fdir.mkdir(parents=True, exist_ok=True)
    for old in fdir.glob("f_*.jpg"):
        old.unlink()
    sel = f"gt(scene\\,{scene})+isnan(prev_selected_t)+gte(t-prev_selected_t\\,{every})"
    r = run(["ffmpeg", "-hide_banner", "-i", str(src), "-vf", f"select='{sel}',showinfo,scale={tile * 2}:-2",
             "-fps_mode", "vfr", "-q:v", "3", str(fdir / "f_%05d.jpg")])
    times = [float(t) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    files = sorted(fdir.glob("f_*.jpg"))
    if not files:
        sys.exit(f"no frames extracted: {r.stderr.strip()[-400:]}")
    picked = list(range(len(files)))
    if len(picked) > mx:  # keep the first and last, spread the rest evenly
        picked = sorted({round(k * (len(files) - 1) / (mx - 1)) for k in range(mx)})

    from PIL import Image, ImageDraw, ImageFont
    font = ImageFont.load_default(size=max(14, tile // 15))
    label_h = font.size + 10
    per = cols * rows
    with Image.open(files[0]) as first:  # cells take the video's shape: tile is the long side
        fw, fh = first.size
    cw, ch = (tile, round(tile * fh / fw)) if fw >= fh else (round(tile * fw / fh), tile)
    tiles, sheet = [], None
    for n, k in enumerate(picked):
        s, cell = n // per + 1, n % per
        if cell == 0:
            if sheet:
                sheet.save(out / f"sheet_{s - 1:03d}.jpg", quality=85)
            used = min(rows, math.ceil((len(picked) - n) / cols))  # the last sheet only as tall as it needs
            sheet = Image.new("RGB", (min(cols, len(picked) - n) * (cw + 4) if used == 1 else cols * (cw + 4),
                                      used * (ch + label_h + 4)), "white")
            draw = ImageDraw.Draw(sheet)
        im = Image.open(files[k]).convert("RGB")
        im.thumbnail((cw, ch))
        t = times[k] if k < len(times) else float("nan")
        tid = f"{n + 1:04d}"
        x, y = (cell % cols) * (cw + 4), (cell // cols) * (ch + label_h + 4)
        draw.rectangle([x, y, x + cw + 2, y + ch + label_h + 2], outline="#bbb")
        draw.text((x + 4, y + 3), f"{tid} · {fmt_t(t) if not math.isnan(t) else '?'}", fill="red", font=font)
        sheet.paste(im, (x + 1 + (cw - im.width) // 2, y + label_h + (ch - im.height) // 2))
        tiles.append({"id": tid, "sheet": s, "time": round(t, 3), "file": str(files[k])})
    sheet.save(out / f"sheet_{tiles[-1]['sheet']:03d}.jpg", quality=85)
    (out / "manifest.json").write_text(json.dumps({"source": str(src), "duration": i["duration"], "tiles": tiles}, indent=1))
    print(f"{len(files)} frames ({'scene > %g or every %gs' % (scene, every)}), {len(tiles)} on "
          f"{tiles[-1]['sheet']} sheets in {out}")


def moov_first(path):
    """True when the moov atom comes before mdat (faststart: plays before it has fully downloaded)."""
    with open(path, "rb") as f:
        while True:
            head = f.read(8)
            if len(head) < 8:
                return False
            size, kind = int.from_bytes(head[:4], "big"), head[4:8]
            if kind == b"moov":
                return True
            if kind == b"mdat":
                return False
            if size == 1:
                size = int.from_bytes(f.read(8), "big") - 8
            f.seek(size - 8, 1)


def loudness(path):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-map", "0:a:0", "-af", "ebur128=peak=true",
             "-f", "null", "-"])
    tail = r.stderr[r.stderr.rfind("Summary:"):]
    i = re.search(r"I:\s+(-?[\d.]+) LUFS", tail)
    tp = re.search(r"Peak:\s+(-?[\d.]+) dBFS", tail)
    return (float(i.group(1)) if i else None), (float(tp.group(1)) if tp else None)


def cmd_check(args):
    want_dur, target = opt(args, "--duration", None), opt(args, "--target", -16)
    path = args[0]
    i = info(path)
    v = i["video"] or {}
    fails = 0

    def line(ok, msg):
        nonlocal fails
        fails += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'}  {msg}")

    line(v.get("codec_name") == "h264", f"codec {v.get('codec_name')} (h264 plays everywhere)")
    line(v.get("pix_fmt") == "yuv420p", f"pixel format {v.get('pix_fmt')} (yuv420p for browsers, phones, Slack)")
    line(not (i["w"] % 2 or i["h"] % 2), f"size {i['w']}x{i['h']}")
    line(abs(i["r_fps"] - i["avg_fps"]) <= 0.001, f"frame rate {i['avg_fps']:.3f} (constant)")
    line(moov_first(path), "faststart (moov before mdat)")
    if want_dur is not None:
        line(abs(i["duration"] - want_dur) < 0.1, f"duration {i['duration']:.2f}s (expected {want_dur:g}s)")
    else:
        print(f"      duration {i['duration']:.2f}s")
    if i["audio"]:
        lu, tp = loudness(path)
        line(lu is not None and abs(lu - target) <= 1.5, f"loudness {lu} LUFS integrated (target {target:g} ±1.5)")
        line(tp is not None and tp <= -1.0, f"true peak {tp} dBFS (keep at or under -1)")
    else:
        print("      no audio")
    for w in warnings(i):
        if not w.startswith("no audio"):
            print(f"WARN  {w}")
    sys.exit(1 if fails else 0)


def cmd_gif(args):
    fps, width = opt(args, "--fps", 12), int(opt(args, "--width", 640))
    start, dur = opt(args, "--start", 0), opt(args, "--duration", 6)
    src, out = args[0], args[1]
    if out.endswith(".webp"):  # animated WebP: far smaller for motion; many ffmpeg builds lack its encoder
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{start:g}", "-t", f"{dur:g}", "-i", src,
                     "-vf", f"fps={fps:g},scale={width}:-2:flags=lanczos", "-q:v", "2", f"{tmp}/f_%05d.png"])
            if r.returncode:
                sys.exit(r.stderr.strip())
            frames = [Image.open(p).convert("RGB") for p in sorted(Path(tmp).glob("f_*.png"))]
            frames[0].save(out, save_all=True, append_images=frames[1:], duration=round(1000 / fps), loop=0,
                           quality=72, method=6)
        print(f"{out}: {Path(out).stat().st_size / 1e6:.1f} MB")
        return
    base = f"fps={fps:g},scale={width}:-2:flags=lanczos"
    graph = f"{base},split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle"
    r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{start:g}", "-t", f"{dur:g}", "-i", src,
             "-filter_complex", graph, "-loop", "0", out])
    if r.returncode:
        sys.exit(r.stderr.strip())
    print(f"{out}: {Path(out).stat().st_size / 1e6:.1f} MB")


def cmd_share(args):
    width, crf = int(opt(args, "--width", 1280)), int(opt(args, "--crf", 28))
    src, out = args[0], args[1]
    r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src, "-c:v", "libx264", "-crf", str(crf),
             "-preset", "slow", "-vf", f"scale={width}:-2", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k",
             "-map_metadata", "-1", "-movflags", "+faststart", out])
    if r.returncode:
        sys.exit(r.stderr.strip())
    print(f"{out}: {Path(out).stat().st_size / 1e6:.1f} MB")


COMMANDS = {"probe": cmd_probe, "proxy": cmd_proxy, "frames": cmd_frames, "check": cmd_check,
            "gif": cmd_gif, "share": cmd_share}

if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]](sys.argv[2:])
