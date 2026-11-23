#!/bin/sh
# Check (and where it's safe, install) what video-skill needs on this Mac. Re-runnable.
# usage: sh scripts/setup.sh
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
PW="$HOME/Library/Caches/ms-playwright"
problems=0
ok()   { echo "ok    $*"; }
todo() { echo "TODO  $*"; problems=$((problems + 1)); }

if command -v mise >/dev/null 2>&1; then
  ok "mise $(mise --version | cut -d' ' -f1)"
else
  todo "mise is missing: curl https://mise.run | sh, then reopen the shell"
fi

if command -v ffmpeg >/dev/null 2>&1; then
  ok "ffmpeg"
elif command -v brew >/dev/null 2>&1 && brew install ffmpeg >/dev/null 2>&1; then
  ok "ffmpeg installed with Homebrew"
else
  todo "ffmpeg is missing (sound beds and share copies): brew install ffmpeg"
fi

# OpenFilm is pinned in scripts/openfilm (0.4.1, Node >= 22.2). Upgrade by editing that pin
# and re-running this script. `openfilm update` and `npx openfilm` bypass the pin.
# OpenFilm's first run deletes Playwright browsers that have no link marker, which can break
# another project's Playwright install. Note what's there so we can say what to put back.
before=$(ls "$PW" 2>/dev/null)

if command -v mise >/dev/null 2>&1; then
  if v=$("$HERE/openfilm" --version 2>/dev/null); then
    ok "openfilm $v (pinned in scripts/openfilm)"
    "$HERE/openfilm" doctor || todo "openfilm doctor reported a problem (above)"
  else
    todo "openfilm did not start; run $HERE/openfilm --version to see why"
  fi
fi

after=$(ls "$PW" 2>/dev/null)
for b in $before; do
  case " $(echo $after) " in *" $b "*) ;; *)
    todo "OpenFilm removed Playwright's $b; in the project that needs it run: node_modules/.bin/playwright install chromium (or: npx playwright install chromium)";;
  esac
done

[ "$problems" -eq 0 ] && echo "ready" || echo "$problems thing(s) to fix above"
exit "$problems"
