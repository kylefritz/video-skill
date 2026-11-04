---
name: video-skill
description: Make, edit, check and understand videos from a terminal, for an agent that can't watch them. Use when someone wants a video made, edited, checked or rendered - a launch or demo video, explainer, title card, motion graphics, slideshow of photos, trip or event montage, GIF, social clip, or a cut of existing footage and sound - or wants to know what's in a video ("what happens in this clip", "find the moment when", "transcribe this"), or has phone footage that looks washed out, sideways or out of sync. Also for OpenFilm, its Studio editor, film.html or pages with window.film, and for loudness, H.264 compatibility, HDR to SDR, GIF and WebP export.
---

# video-skill

Scripts live in `scripts/` next to this file; write it as `$S` below, but spell the absolute path
out in each command, because shell variables don't carry between Bash calls.

You can't watch video, so every step turns it into something you can read: **frames you look at
and numbers you check.** Making a film is write → render frames → read the contact sheet → fix.
Understanding footage is probe → proxy → timestamped sheets + transcript → judge. Delivering is a
script that checks codec, frame rate, faststart and loudness, so "it plays everywhere" is a fact.

## First time on a Mac

Run `sh $S/setup.sh` yourself. It checks mise and ffmpeg (installing ffmpeg with Homebrew when it
can), installs the pinned OpenFilm on first use and runs `openfilm doctor`. Fix each `TODO` it
prints, or explain it plainly to the person. Safe to re-run.

## Making a film: OpenFilm

[OpenFilm](https://github.com/openfilm/openfilm) (MIT) is the authoring format: a film is a folder
with a `film.html` that cuts HTML pages, footage, pictures and sound together, each page drawing
any moment `t` it's asked for. Studio is its local browser editor.

1. **Print the manual and read it whole** (it's short and it changes between releases):
   `$S/openfilm`. Follow it, with this file taking precedence where they differ.
2. `$S/openfilm` is the only way to run OpenFilm here: it pins the version, installs it through
   mise on first use, and keeps Studio from popping a browser window. Don't use `npx openfilm`
   (bypasses the pin) or `npx skills add openfilm/openfilm` (an upstream skill that competes with
   this one).
3. `FILM` is always an absolute path, `$HOME/Movies/OpenFilm/Projects/<film-name>`. A relative
   name lands in the current folder, such as somebody's git repo. Films never go in a repo.

| Step | Command |
| --- | --- |
| Create or open | `$S/openfilm open FILM` |
| Check the whole film | `$S/openfilm -C FILM look` |
| Check a moment, a stretch, a file | `… look 4.5`, `look 3-6`, `look assets/bed.wav` |
| Check a fast entrance | `… look 0-2 --count 24` |
| Render the MP4 | `$S/openfilm -C FILM render` |
| What media services are connected | `$S/openfilm get` |
| Diagnose the install | `$S/openfilm doctor` |

`look` and `render` run without Studio open and print paths relative to FILM. Studio's address
contains an access key: give it only to the person you're working with (it's `127.0.0.1`, Chrome or
Edge, not from a phone).

**Read every `look` sheet before you show anything**, and fix what you see. Its checks (same `t`
draws the same picture, fonts loaded, text clipped, loudness) say nothing about taste or layout. A
`!` about text cut off during an entrance is fine; cut off at rest is a bug. Then look at a few
moments at full size (`look 12.5`): a 300 px tile hides small things, people included.

How a film is built, learned from making one:

- One page per shot; what pages share (a Ken Burns move, fonts, colors) goes in a module they
  import. Every value is a function of `t` only: no timers, no animation loop, no state.
- Pages fade themselves (opacity from `t`); a fade through black between shots on one track is the
  simplest transition. A cross-dissolve needs the incoming shot on a track *above* the outgoing one.
- Text over photos needs a shade behind it (a bottom gradient), or it disappears into busy scenes.
- Fonts go in `FILM/fonts/` with `@font-face`, awaited through `window.film.ready`
  (`document.fonts.ready`). For photos, `ready: img.decode()`.
- Trim with `#t=in,out`, never by cutting new files; a sound longer than the film extends the film.

## Sound

`$S/openfilm get` shows what's connected; generated voice, music and effects need the person's own
provider keys (Studio: OpenFilm logo → Settings → Providers). Without them, make sound with ffmpeg,
save it under `FILM/assets/`, keep the command in `FILM/sound-notes.txt` so it can be rebuilt, and
say which service would do it better. You can't hear it, so judge by numbers:

- **-16 LUFS integrated** for a finished mix (podcasts, most web video); streaming platforms
  normalize near -14. Keep true peak at or under **-1 dBTP**. A bed under a voice sits ~-22.
- Measure: `ffmpeg -i X -af ebur128=peak=true -f null -`. Normalize a generated bed with
  `loudnorm=I=-16:TP=-1.5:LRA=7`; for a final master, run `loudnorm` twice (measure, then feed the
  `measured_*` values back) so the gain is linear.
- `look` prints the mix's loudness, and `footage.py check` fails a render that misses the target.

## Footage you were handed: intake

Phone video is rarely what it looks like. Run this on anything before you look at it or cut it:

```bash
uv run --no-project --with pillow python -I $S/footage.py probe CLIP.mov ...
uv run --no-project --with pillow python -I $S/footage.py proxy CLIP.mov <scratch>/clip.mp4
```

`probe` warns about each of these, and `proxy` fixes all of them in one pass (SDR BT.709, rotation
baked in, constant 30 fps, even size, H.264 yuv420p, AAC 48 kHz, faststart):

- **HDR** (iPhones record HLG by default: `color_transfer=arib-std-b67`, BT.2020). Read as SDR, it
  looks washed out and shifts colors: vermilion turns orange. `proxy` tone-maps with macOS's
  built-in `avconvert`, else ffmpeg `zscale` (missing from many Homebrew builds), else warns.
- **Rotation**: phones store portrait video sideways with a rotation flag; some tools ignore it.
- **Variable frame rate**: nominal 24, average 23.997. Frame times drift and audio slides out of
  sync after cuts. `probe` flags any difference over 0.001 fps.
- **Odd dimensions**: H.264 yuv420p needs even width and height.

Look at and cut from the proxy; keep the original for anything that must stay full quality.

## Understanding footage

```bash
uv run --no-project --with pillow python -I $S/footage.py frames <scratch>/clip.mp4 <scratch>/sheets --every 4
```

That takes a frame at every scene change (`--scene 0.3`) and at least one every `--every` seconds,
capped at `--max 60`, onto sheets of 5×6 tiles labeled `0007 · 1:23.4`, with `manifest.json`
mapping each id to its time. Read the sheets and answer with ids and times. Practice, not doctrine:

- Authored films: uniform sampling at the shot length. Found footage: scene changes plus a floor of
  one frame every 2-5 s. Fast action: a short stretch at `--every 0.5`.
- Keep a sheet under ~2,500 px on its long side and read a handful at a time; for long footage,
  fan out to subagents over sheets, each writing one JSONL verdict per tile id, then
  `python3 -I $S/check_verdicts.py manifest.json out/*.jsonl` (missing, duplicate or invented ids
  fail; a sheet where every tile got the same answer was probably skimmed).
- **Most of a talking video is in its audio.** Transcribe on-device with word times:
  `uvx parakeet-mlx AUDIO.wav --output-format json --output-dir <scratch>` (extract audio first:
  `ffmpeg -i clip.mp4 -ar 16000 -ac 1 audio.wav`). Join words to frames by time. Proper nouns come
  out wrong ("torii" → "Torrey"), so check names against what you see before quoting it.

## Delivering

```bash
uv run --no-project --with pillow python -I $S/footage.py check FILM/<name>.mp4 --duration 30
uv run --no-project --with pillow python -I $S/footage.py share FILM/<name>.mp4 <scratch>/<name>-share.mp4
uv run --no-project --with pillow python -I $S/footage.py gif FILM/<name>.mp4 <scratch>/loop.webp --start 2.5 --duration 6 --width 480
```

- `check` must pass before you hand over a file: H.264, yuv420p, even size, constant frame rate,
  `moov` before `mdat` (faststart: plays while downloading), duration, loudness ±1.5 LU, true peak.
- Render when the person asks for the file or can't be at this Mac; run `look` on the MP4 itself
  as the last check. `share` makes a small copy (1280 wide, CRF 28: a 30 s 1080p render went from
  34 MB to 3.8 MB) for a web page or chat; the film's own MP4 stays untouched.
- Loops: **animated WebP over GIF.** A 5.6 s photo loop with a slow zoom was 6.7 MB as GIF and
  1.6 MB as WebP: GIF can't reuse pixels when every pixel moves. GIF only when the target can't
  show WebP; then `footage.py gif X.gif` uses a generated palette (`palettegen`/`paletteuse`).
- Strip what shouldn't travel: iPhone video carries GPS, the phone model and the time in its
  metadata. `proxy` and `share` drop all of it (`-map_metadata -1`). The original file, or a copy
  made by AirDrop or a Photos export, keeps it. Check with `exiftool -GPSCoordinates FILE`.

## Photos in a film

Use the `photo-skill` skill ([github.com/kylefritz/photo-skill](https://github.com/kylefritz/photo-skill);
if it isn't installed, offer to clone it into `~/.claude/skills/photo-skill`) to find them (search
the library by description, then judge contact sheets) and to download full-resolution originals:
previews are too small for 1080p. Copy what the
film uses into `FILM/assets/`, re-saved without EXIF. Before a film with someone's photos goes
anywhere, look at each shot at full size: face detection misses crowds, and a 300 px tile hides
people that a 1080p frame shows.

## Other tools

OpenFilm fits an agent best because a film is plain HTML and `look` hands back exactly what you
need to see. Alternatives, as of late 2026:

| Tool | Authoring | Notes |
| --- | --- | --- |
| [HyperFrames](https://github.com/heygen-com/hyperframes) (HeyGen, Apache-2.0) | HTML/CSS + GSAP, rendered by headless Chrome | the closest analogue; `check --json` lint/layout/contrast gate, snapshots, a Claude Code plugin |
| [Remotion](https://www.remotion.dev) | React components | mature, official agent skills; source-available license, companies above a small size need one |
| [Manim](https://www.manim.community) (MIT) | Python scenes | math and diagram explainers |
| MoviePy (MIT) / raw ffmpeg | Python / filtergraphs | simple cuts and overlays; ffmpeg is best kept as the I/O layer |

## Upgrading OpenFilm

Upstream ships often. Read the release notes and run `npm view openfilm scripts` first (a
`preinstall` or `postinstall` entry deserves a look), then change `OPENFILM_VERSION` in
`scripts/openfilm` and re-run `setup.sh`. Afterwards `ls ~/Library/Caches/ms-playwright`: OpenFilm's
first run deletes Playwright browsers that have no link marker; `setup.sh` reports any it removed,
and `npx playwright install chromium` in the project that needs one puts it back.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| `npx openfilm …` | `$S/openfilm …`: npx bypasses the pin |
| `look` or `render` in the wrong folder | `$S/openfilm -C FILM …` |
| Trusting `look`'s checks without opening its PNG | Read the sheet; a passing check says nothing about layout |
| Cutting or looking at iPhone footage directly | `probe`, then `proxy`: HDR, rotation and VFR all bite |
| Sending the master MP4 to a chat | `share` it, then `check` the copy |
| A GIF for a README or a page | WebP, ~4× smaller |
| Stale Studio after an upgrade | Stop the old `studio/server/main.mjs` processes (`pgrep -fl openfilm`); one Studio is two processes |
