#!/usr/bin/env python3
"""Backfill the Shopee listing tables in existing shopee-product-match.md reports.

The identification pass (batch_product_match.py) can run any time — the vision model is free and
local to the portal. Its listing step needs BigGo (my.biggo.com), our only index of Shopee MY,
and BigGo serves an IP wall ("verifylogin") when it has seen too many requests from this machine.
This script re-reads each report's keyword list, retries BigGo, and rewrites only the listings
section of reports that are still empty. Safe to run repeatedly; exits non-zero-ish (prints
BLOCKED) without touching files when BigGo is still walled.

Usage:
  python3 backfill_listings.py "/media/masso/System/Affiliates/Deco Rumah" [--wait 0]
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
import time
from pathlib import Path

BIGGO = Path.home() / ".hermes/skills/research/find-product-on-shopee/scripts/biggo_search.py"
OUT_NAME = "shopee-product-match.md"
KW_RE = re.compile(r"^- `(.+?)`\s*$", re.M)


def load_biggo():
    spec = importlib.util.spec_from_file_location("biggo_search", BIGGO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                                 # type: ignore[union-attr]
    return mod


def biggo_alive(mod) -> bool:
    try:
        return bool(mod.search("test candle"))
    except Exception:                                            # noqa: BLE001
        return False


def listings_block(results: dict, want: int = 8) -> str:
    seen, rows = set(), []
    for kw, items in results.items():
        for it in items:
            url = it.get("purl") or ""
            if not url or url in seen:
                continue
            seen.add(url)
            rows.append(it)
    def pkey(r):
        p = r.get("price")
        return p if isinstance(p, (int, float)) else 9e9
    rows.sort(key=pkey)
    table = "\n".join(
        f"| RM{r.get('price')} | {(r.get('title') or '')[:95]} | {r.get('purl')} |"
        for r in rows[:want]) or "| - | no Shopee listings returned | - |"
    by_kw = []
    for k, items in results.items():
        by_kw.append(f"\n**`{k}`** — {len(items)} results")
        for it in items[:6]:
            by_kw.append(f"    RM{it.get('price')}  {(it.get('title') or '')[:90]}")
            by_kw.append(f"           {it.get('purl')}")
    return (f"## Matching Shopee MY listings\n\n| Price | Listing | Link |\n|---|---|---|\n{table}\n\n"
            f"### Raw results per keyword\n{chr(10).join(by_kw)}\n\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--wait", type=int, default=0, help="minutes to keep retrying BigGo first")
    args = ap.parse_args()

    mod = load_biggo()
    deadline = time.time() + args.wait * 60
    alive = biggo_alive(mod)
    while not alive and time.time() < deadline:
        time.sleep(60)
        alive = biggo_alive(mod)
    if not alive:
        print("BLOCKED: BigGo still serving its verifylogin wall to this IP — nothing changed.")
        return 0

    root = Path(args.root)
    done = skipped = failed = 0
    for folder in sorted(root.iterdir()):
        if not folder.is_dir() or not folder.name.startswith("MyRezeki"):
            continue
        rep = folder / OUT_NAME
        if not rep.exists():
            continue
        body = rep.read_text(encoding="utf-8")
        if "no Shopee listings returned" not in body:
            skipped += 1
            continue
        head, sep, tail = body.partition("## Matching Shopee MY listings")
        if not sep:
            continue
        notes_at = tail.find("## Notes")
        notes = tail[notes_at:] if notes_at >= 0 else ""
        kws = [k.strip() for k in KW_RE.findall(head)]
        if not kws:
            failed += 1
            continue
        results = {}
        for kw in kws[:6]:
            try:
                results[kw] = mod.search(kw)
            except Exception as exc:                             # noqa: BLE001
                print(f"  !! {folder.name} / {kw}: {exc}")
            time.sleep(0.5)
        got = sum(1 for v in results.values() if v)
        if not got:
            print(f"  -- {folder.name}: still 0 results, left as is")
            failed += 1
            continue
        rep.write_text(head + listings_block(results) + notes, encoding="utf-8")
        n = sum(len(v) for v in results.values())
        print(f"  OK {folder.name}: {n} listings")
        done += 1
    print(f"\nbackfilled {done}, already complete {skipped}, still empty {failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
