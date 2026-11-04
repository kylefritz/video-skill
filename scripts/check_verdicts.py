"""Check a model pass over contact sheets: every tile answered exactly once, no invented ids.

usage: python3 -I check_verdicts.py MANIFEST.json VERDICTS.jsonl [VERDICTS.jsonl ...]
  Each verdict line is a JSON object with an "id" from the manifest, plus whatever fields the prompt
  asked for. Prints coverage and per-sheet counts of each field's values; exits 1 on any gap.

A sheet where every tile got the same verdict usually means the subagent skimmed: the per-sheet table
makes those easy to spot. Look at that sheet yourself before trusting it.
"""
import collections
import json
import sys


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    manifest = json.load(open(sys.argv[1]))
    sheet_of = {t["id"]: t["sheet"] for t in manifest["tiles"]}
    seen = collections.Counter()
    unknown, rows = [], []
    for path in sys.argv[2:]:
        for n, line in enumerate(open(path), 1):
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                unknown.append(f"{path}:{n} not JSON")
                continue
            tid = str(r.get("id"))
            if tid not in sheet_of:
                unknown.append(f"{path}:{n} id {tid!r} not in manifest")
                continue
            seen[tid] += 1
            rows.append(r)

    missing = [t for t in sheet_of if not seen[t]]
    dupes = [t for t, c in seen.items() if c > 1]
    print(f"{len(seen)}/{len(sheet_of)} tiles answered, {len(missing)} missing, {len(dupes)} answered twice, "
          f"{len(unknown)} bad lines")
    for label, items in (("missing", missing), ("twice", dupes), ("bad", unknown)):
        if items:
            print(f"  {label}: {', '.join(items[:20])}{' ...' if len(items) > 20 else ''}")

    # per sheet, how varied were the answers? (all-identical sheets deserve a look)
    fields = sorted({k for r in rows for k, v in r.items() if k != "id" and isinstance(v, (str, int, bool))})
    for field in fields:
        by_sheet = collections.defaultdict(collections.Counter)
        for r in rows:
            if field in r:
                by_sheet[sheet_of[str(r["id"])]][r[field]] += 1
        if len({v for c in by_sheet.values() for v in c}) > 12:
            continue  # free text, not a verdict
        print(f"{field}:")
        for s in sorted(by_sheet):
            c = by_sheet[s]
            flag = "  <- all the same" if len(c) == 1 and sum(c.values()) > 5 else ""
            print(f"  sheet {s:3d}: {dict(c.most_common())}{flag}")
    sys.exit(1 if missing or dupes or unknown else 0)


if __name__ == "__main__":
    main()
