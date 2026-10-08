#!/usr/bin/env python3
"""Batch: identify the product in each MyRezeki video folder and find it on Shopee MY.

Pipeline per folder:
  1. send the folder's IMG/frame_*.jpg (sampled) to the FREE vision model on the Nous Portal
  2. it returns JSON: product (English + Malay), category, colours/material, how it is used,
     Shopee search keywords, confidence
  3. run those keywords through BigGo's index of Shopee MY (shopee.com.my itself is blocked)
  4. write <folder>/shopee-product-match.md in the shape of the manual reports
  5. append a row to _product-match-index.md at the batch root

Costs: the vision+keyword model is free (cost_details.source == free_path). Only the BigGo
HTTP fetches are local. Nothing here touches the paid model.

Usage:
  python3 batch_product_match.py ROOT [--folders N N ...] [--limit N] [--workers 3]
                                         [--only-missing] [--dry-run]
  python3 batch_product_match.py "/media/masso/System/Affiliates/Deco Rumah" --only-missing

Resumable: a folder that already has shopee-product-match.md is skipped with --only-missing.
Never prints credentials.
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as futures
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERMES = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
AUTH = HERMES / "auth.json"
BIGGO = HERMES / "skills" / "research" / "find-product-on-shopee" / "scripts" / "biggo_search.py"
VISION_MODEL = os.environ.get("BATCH_VISION_MODEL", "meituan/longcat-2.5-preview:free")
MAX_FRAMES = 5
OUT_NAME = "shopee-product-match.md"
INDEX_NAME = "_product-match-index.md"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

PROMPT = """These are frames from ONE short affiliate video selling ONE product.
Identify the single product being advertised (not the background, not the person, not the end-card text).

Reply with ONLY a JSON object, no prose:
{
  "product_en": "common English product name, as a buyer would search it",
  "product_ms": "Malay name if one exists, else empty string",
  "category": "one of: kitchen, home_organiser, laundry, decor, beauty, tech, fashion, toy, tool, other",
  "look": "material, colour(s), size/shape in one short phrase",
  "used_for": "how it is used in the frames, one short phrase",
  "shopee_keywords": ["4 to 6 search phrases, mix Malay and English, that would find this exact product on Shopee Malaysia"],
  "evidence_frame": "which frame number shows the product most clearly",
  "confidence": 0.0
}
confidence is 0.0-1.0 for how sure you are of the product identity. Use a low number if the frames show
several different products or the product is unclear. Output nothing except the JSON."""


def portal() -> tuple[str, str]:
    d = json.load(open(AUTH))
    n = d["providers"]["nous"]
    return n["inference_base_url"].rstrip("/"), n["agent_key"]


def frames(folder: Path, limit: int = MAX_FRAMES) -> list[Path]:
    fs = sorted(folder.glob("IMG/*.jpg"), key=lambda p: int(re.search(r"(\d+)", p.stem).group(1)))
    if len(fs) > limit:                       # keep first, last and an even spread
        step = (len(fs) - 1) / (limit - 1)
        fs = [fs[round(i * step)] for i in range(limit)]
    return fs


def post(url: str, payload: dict, key: str, timeout: int = 180) -> dict:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def identify(paths: list[Path], base: str, key: str, tries: int = 4) -> tuple[dict, str]:
    """Returns (parsed json, raw text). Retries 429/capacity stalls."""
    content = [{"type": "text", "text": PROMPT}]
    for p in paths:
        b64 = base64.b64encode(p.read_bytes()).decode()
        content.append({"type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    payload = {"model": VISION_MODEL, "max_tokens": 900, "temperature": 0.2,
               "messages": [{"role": "user", "content": content}]}
    delay = 8
    for attempt in range(tries):
        try:
            d = post(base + "/chat/completions", payload, key)
            txt = ((d.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            cost = (d.get("usage") or {}).get("cost")
            m = re.search(r"\{.*\}", txt, re.S)
            if m:
                return json.loads(m.group(0)), txt
            return {}, txt
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:200]
            if e.code in (429, 500, 502, 503) and attempt < tries - 1:
                time.sleep(delay); delay *= 2; continue
            return {}, f"HTTP {e.code}: {body}"
        except Exception as e:                                  # noqa: BLE001
            if attempt < tries - 1:
                time.sleep(delay); delay *= 2; continue
            return {}, f"{type(e).__name__}: {e}"
    return {}, "exhausted retries"


def biggo(keywords: list[str], base: str, key: str) -> dict:
    """Search BigGo for each keyword via the skill script's parser, in-process."""
    sys.path.insert(0, str(BIGGO.parent))
    import importlib.util
    spec = importlib.util.spec_from_file_location("biggo_search", BIGGO)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)                                # type: ignore[union-attr]
    out: dict[str, list[dict]] = {}
    failed = 0
    for kw in keywords[:3]:
        try:
            items = mod.search(kw)
        except Exception as e:                                  # noqa: BLE001
            failed += 1
            print(f"      !! biggo {kw!r}: {type(e).__name__}: {e}", flush=True)
            continue
        rows = []
        for it in items:
            url = it.get("purl") or ""
            if not url:
                continue
            rows.append({"title": it.get("title"), "url": url, "price": it.get("price"),
                         "symbol": it.get("symbol"), "shop": (it.get("shop") or {}).get("name")})
        out[kw] = rows
    if failed and failed == min(3, len(keywords)) and not any(out.values()):
        # every fetch errored — a rate-limited/blocked search, not "this product has no listing".
        # Raise so process() leaves the folder without a report and a later pass retries it.
        raise RuntimeError(f"all {failed} keyword fetches failed")
    return out


def best_listings(results: dict, want: int = 8) -> list[dict]:
    seen, rows = set(), []
    for kw, items in results.items():
        for it in items:
            if it["url"] in seen:
                continue
            seen.add(it["url"]); rows.append(it)
    def key(r):
        return float(r["price"]) if isinstance(r["price"], (int, float)) else 9e9
    return sorted(rows, key=key)[:want]


def write_report(folder: Path, ident: dict, results: dict, raw: str) -> Path:
    p = folder / OUT_NAME
    listings = best_listings(results)
    rows = "\n".join(
        f"| {l['symbol']}{l['price']} | {(l['title'] or '')[:95]} | {l['url']} |"
        for l in listings) or "| - | no Shopee listings returned | - |"
    kw = ident.get("shopee_keywords") or list(results.keys())
    kw_block = "\n".join(f"- `{k}`" for k in kw)
    by_kw = []
    for k, items in results.items():
        by_kw.append(f"\n**`{k}`** — {len(items)} results")
        for it in items[:6]:
            by_kw.append(f"    {it['symbol']}{it['price']}  {(it['title'] or '')[:90]}")
            by_kw.append(f"           {it['url']}")
    conf = ident.get("confidence")
    flag = "" if (isinstance(conf, (int, float)) and conf >= 0.6) else \
        "\n> **NEEDS REVIEW** — the vision model was not confident about this product. Check the\n> frames and correct the product line before using this file.\n"
    body = f"""# Product ID from video folder → Shopee match

Folder checked: {folder.name} (frames in IMG/, sampled every 3s from the video)

Auto-generated by `batch_product_match.py` (free vision model + BigGo Shopee MY index).
Confidence reported by the vision model: **{conf}**
{flag}
## Product identified from frames

| field | value |
|---|---|
| English | {ident.get('product_en', '(none)')} |
| Malay | {ident.get('product_ms', '') or '(none)'} |
| Category | {ident.get('category', '')} |
| Look | {ident.get('look', '')} |
| Used for | {ident.get('used_for', '')} |
| Clearest frame | {ident.get('evidence_frame', '')} |

## Shopee search keywords

{kw_block}

## Matching Shopee MY listings

| Price | Listing | Link |
|---|---|---|
{rows}

### Raw results per keyword
{chr(10).join(by_kw)}

## Notes

- The .txt in this folder carries the same constant affiliate link as every other folder
  (`https://s.shopee.com.my/2g4kzNQAUT`); it is not a link to this product.
- shopee.com.my cannot be opened from this machine (traffic-verification wall). Listings come from
  BigGo Malaysia's index of Shopee MY — prices are index-time values, verify on click.
- Generated {time.strftime('%Y-%m-%d %H:%M')} by batch_product_match.py.
"""
    p.write_text(body, encoding="utf-8")
    return p


def process(folder: Path, base: str, key: str, dry: bool) -> dict:
    t0 = time.time()
    fs = frames(folder)
    if not fs:
        return {"folder": folder.name, "status": "no-frames"}
    ident, raw = identify(fs, base, key)
    if not ident:
        return {"folder": folder.name, "status": "identify-failed", "detail": raw[:200],
                "secs": round(time.time() - t0, 1)}
    kws = [k for k in (ident.get("shopee_keywords") or []) if isinstance(k, str) and k.strip()]
    if not kws:
        kws = [ident.get("product_en") or "", ident.get("product_ms") or ""]
        kws = [k for k in kws if k]
    try:
        results = {} if dry else biggo(kws, base, key)
    except Exception as e:                                       # noqa: BLE001
        return {"folder": folder.name, "status": "search-failed", "detail": str(e)[:200],
                "product_en": ident.get("product_en"), "confidence": ident.get("confidence"),
                "secs": round(time.time() - t0, 1)}
    if not dry:
        write_report(folder, ident, results, raw)
    return {"folder": folder.name, "status": "ok", "product_en": ident.get("product_en"),
            "product_ms": ident.get("product_ms"), "confidence": ident.get("confidence"),
            "keywords": kws, "listings": len(best_listings(results)) if results else 0,
            "written": str(folder / OUT_NAME) if not dry else "", "secs": round(time.time() - t0, 1)}

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--folders", nargs="*", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--only-missing", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    dirs = sorted([d for d in root.iterdir()
                   if d.is_dir() and (d / "IMG").is_dir() and d.name.startswith("MyRezeki")],
                  key=lambda d: int(re.search(r"(\d+)$", d.name).group(1))
                  if re.search(r"(\d+)$", d.name) else 0)
    if args.folders:
        want = set(args.folders)
        dirs = [d for d in dirs if d.name in want or d.name.split()[-1] in want]
    if args.only_missing:
        dirs = [d for d in dirs if not (d / OUT_NAME).exists()]
    if args.limit:
        dirs = dirs[:args.limit]
    print(f"folders to process: {len(dirs)}")
    if not dirs:
        return 0

    base, key = portal()
    print(f"vision model: {VISION_MODEL} via {base}")
    results = []
    with futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(process, d, base, key, args.dry_run): d for d in dirs}
        for f in futures.as_completed(futs):
            r = f.result()
            results.append(r)
            flag = "OK " if r["status"] == "ok" else "!! "
            print(f"{flag}{r['folder']:32s} {str(r.get('product_en'))[:52]:54s} "
                  f"conf={r.get('confidence')} listings={r.get('listings')} {r.get('secs')}s", flush=True)

    (root / "_batch-results.json").write_text(json.dumps(results, indent=1, ensure_ascii=False))
    index = root / INDEX_NAME
    with index.open("w", encoding="utf-8") as fh:
        fh.write(f"# Product match index — {root.name}\n\n")
        fh.write(f"Generated {time.strftime('%Y-%m-%d %H:%M')} · {len(results)} folders · "
                 f"free vision model `{VISION_MODEL}`\n\n")
        fh.write("| folder | product | confidence | listings | status |\n|---|---|---|---|---|\n")
        for r in sorted(results, key=lambda r: r["folder"]):
            fh.write(f"| {r['folder']} | {r.get('product_en', '')} {r.get('product_ms', '') or ''} | "
                     f"{r.get('confidence', '')} | {r.get('listings', '')} | {r['status']} |\n")
    ok = [r for r in results if r["status"] == "ok"]
    low = [r for r in ok if not isinstance(r.get("confidence"), (int, float)) or r["confidence"] < 0.6]
    print(f"\ndone: {len(ok)}/{len(results)} ok, {len(low)} low-confidence, "
          f"{len(results) - len(ok)} failed")
    print(f"index: {index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
