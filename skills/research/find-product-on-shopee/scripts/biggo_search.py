#!/usr/bin/env python3
"""Search Shopee MY listings through BigGo (shopee.com.my itself blocks this machine).

BigGo (my.biggo.com) indexes Shopee MY listings with price + link. As of 2026-10 it serves a
"Verify to Continue" wall to this machine's IP for direct HTTP requests, so by default we fetch
each search page through the Jina Reader proxy (r.jina.ai) — Jina's servers get the page and
return it as markdown, which this script parses. Set BIGGO_FETCH=direct to go back to raw HTTP
(works again if the wall lifts, and it is also the fallback used automatically when the proxy
fails).

Output per query: price | title | product URL | [shop]

Usage:
    python3 biggo_search.py "sticker skirting dinding" "wall border sticker"
    python3 biggo_search.py --json out.json --images /tmp/img "wall border sticker"
    python3 biggo_search.py --limit 8 "skirting sticker 3d"

Options:
    --json PATH    also write the parsed results (all queries) as JSON
    --images DIR   download each listing's own product image from cf.shopee.com.my
                   into DIR/<shopid>_<itemid>.jpg — inspect these with vision to
                   confirm the listing really is the product before recommending it
    --limit N      max rows printed per query (default 15; 0 = all)
    --direct       bypass the Jina proxy and fetch BigGo with plain HTTP

Run several keyword phrasings, Malay and English — BigGo's result sets differ per query,
and localised terms (ampaian baju, boleh laras, tanpa tebuk, sticker dinding, skirting)
reach listings that English keywords miss.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
ITEM_RE = re.compile(r"/product/(\d+)/(\d+)")
SHOPEE_IMG_RE = re.compile(r"(https://cf\.shopee\.com\.my/file/[^\"'\s]+)")
JINA = "https://r.jina.ai/"
JINA_UA = os.environ.get("JINA_UA", "curl/8.5.0")   # Jina 403s spoofed browser UAs
JINA_KEY = os.environ.get("JINA_API_KEY", "")       # optional: lifts the per-IP rate ceiling
MIN_GAP = float(os.environ.get("BIGGO_MIN_GAP", "1.2"))   # seconds between fetches
CACHE_DIR = os.environ.get("BIGGO_CACHE", str(Path.home() / ".hermes/cache/scratch/biggo-cache"))
_last = [0.0]
_gate = threading.Lock()          # serialises the global gap across worker threads

# one markdown link row, as rendered by Jina: [![Image 5: title](img)](https://my.biggo.com/r/?… "title")
ROW_RE = re.compile(
    r'\[!\[Image \d+:\s*(?P<alt>.*?)\]\((?P<img>[^)]*)\)\]'
    r'\((?P<href>https://my\.biggo\.com/r/\?[^)]*)\)'
    r'(?:\s*"(?P<title>[^"]*)")?', re.S)


def _clean_title(s: str | None) -> str:
    """Jina alt text sometimes swallows image URLs / nested markdown links; strip them."""
    t = s or ""
    t = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", t)     # [text](url) -> text
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\s*\|\s*", " | ", t)
    return re.sub(r"\s+", " ", t).strip(" |,-")

PRICE_RE = re.compile(r'(?:[\d.]+\s*(?:pcs|set|unit|pack)s?\s+)?(?:RM|MYR)\s*[\d.,]+(?:\s*~\s*RM?\s*[\d.,]+)?')


def _throttle() -> None:
    """Enforce MIN_GAP between fetches GLOBALLY.

    The gap must hold across worker threads, otherwise N threads fire at once and Jina answers
    429 for the whole burst — which read as "0 Shopee results" and quietly wrote empty reports.
    """
    with _gate:
        gap = time.time() - _last[0]
        if gap < MIN_GAP:
            time.sleep(MIN_GAP - gap)
        _last[0] = time.time()


def _get(url: str, headers: dict | None = None, timeout: int = 90,
         tries: int = 4) -> bytes:
    """GET with retry/backoff. 429 and 5xx are transient here and must not be swallowed."""
    hdrs = dict(headers or {})
    delay = 5.0
    last = ""
    for attempt in range(tries):
        _throttle()
        try:
            req = urllib.request.Request(url, headers=hdrs)
            return urllib.request.urlopen(req, timeout=timeout).read()
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code not in (429, 500, 502, 503, 504):
                raise
            ra = e.headers.get("Retry-After")
            try:
                delay = max(delay, float(ra)) if ra else delay
            except ValueError:
                pass
        except Exception as e:                                   # noqa: BLE001
            last = f"{type(e).__name__}: {e}"
        if attempt < tries - 1:
            time.sleep(delay)
            delay *= 2
    raise RuntimeError(f"fetch failed after {tries} tries ({last}): {url}")


def fetch(url: str, referer: str | None = None, timeout: int = 60) -> bytes:
    """Plain HTTP fetch (used for images and as the direct fallback)."""
    headers = {"User-Agent": UA, "Accept-Language": "en-MY,en;q=0.9"}
    if referer:
        headers["Referer"] = referer
    return _get(url, headers, timeout)


def fetch_page(url: str) -> str:
    """Fetch a BigGo search page. Jina proxy first, direct HTTP as fallback.

    Jina rejects spoofed browser User-Agents with 403, so the proxy request must send a
    neutral client UA. The direct BigGo request keeps the browser UA.
    """
    if os.environ.get("BIGGO_FETCH", "jina") != "direct":
        for ua in (JINA_UA, None):
            try:
                hdrs = {"User-Agent": ua} if ua else {}
                if JINA_KEY:
                    hdrs["Authorization"] = "Bearer " + JINA_KEY
                body = _get(JINA + url, hdrs, timeout=90).decode("utf-8", "ignore")
                if "purl=" in body:
                    return body
            except Exception:                                    # noqa: BLE001
                continue
    return fetch(url).decode("utf-8", "ignore")


def _price_after(text: str, pos: int, window: int = 400) -> str | None:
    m = PRICE_RE.search(text[pos:pos + window])
    return m.group(0) if m else None


def _price_num(price: str | None) -> float | None:
    if not price:
        return None
    m = re.search(r"RM?\s*([\d.,]+)", price.replace(",", ""))
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


def parse_markdown(md: str) -> list[dict]:
    """Parse Jina's markdown rendering of a BigGo search page."""
    out, seen = [], set()
    for m in ROW_RE.finditer(md):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(m.group("href")).query)
        purl = urllib.parse.unquote((q.get("purl") or [""])[0])
        if "shopee.com.my/product/" not in purl or purl in seen:
            continue
        seen.add(purl)
        title = _clean_title(m.group("title")) or _clean_title(m.group("alt")) or "(title not captured)"
        price = _price_after(md, m.end())
        if not price:                                            # price can precede the row
            price = _price_after(md, max(0, m.start() - 400), 420)
        shop = "Shopee"
        simg = SHOPEE_IMG_RE.search(m.group("img") or "")
        out.append({
            "title": title,
            "purl": purl,
            "price": _price_num(price),
            "price_text": price,
            "symbol": "RM",
            "shop": {"name": shop},
            "image": simg.group(1) if simg else None,
            "variants": None,
            "ad": False,
        })
    return out


def parse_ssr(html: str) -> list[dict]:
    """Legacy path: pull the SSR JSON result list out of a BigGo page."""
    norm = html.replace('\\"', '"').replace('\\u0026', '&')
    i = norm.find('"list":[')
    if i < 0:
        return []
    s = norm[i + len('"list":'):]
    depth = 0
    for k, ch in enumerate(s):
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                try:
                    items = json.loads(s[:k + 1])
                except json.JSONDecodeError:
                    return []
                rows = []
                for it in items:
                    if 'shopee' not in (it.get('nindex') or ''):
                        continue
                    rows.append({
                        'title': it.get('title'), 'purl': it.get('purl'),
                        'price': it.get('price'), 'price_text': f"{it.get('symbol','')}{it.get('price')}",
                        'symbol': it.get('symbol'), 'shop': it.get('shop') or {},
                        'image': it.get('origin_image') or it.get('image'),
                        'variants': (it.get('multiple') or {}).get('title'),
                        'ad': it.get('is_ad'),
                    })
                return rows
    return []


def _cache_path(keyword: str) -> Path:
    h = hashlib.sha1(keyword.strip().lower().encode()).hexdigest()[:16]
    return Path(CACHE_DIR) / f"{h}.json"


def search(keyword: str, use_cache: bool = True) -> list[dict]:
    """Search BigGo for one keyword, caching hits on disk (same keyword recurs across folders)."""
    cp = _cache_path(keyword)
    if use_cache:
        try:
            cached = json.loads(cp.read_text(encoding="utf-8"))
            rows = cached.get("rows") if isinstance(cached, dict) else cached
            if isinstance(rows, list):
                return rows
        except Exception:                                        # noqa: BLE001
            pass
    url = "https://my.biggo.com/s/" + urllib.parse.quote(keyword)
    page = fetch_page(url)
    rows = parse_markdown(page) if "purl=" in page else []
    if not rows:
        rows = parse_ssr(page)
    if rows and use_cache:
        try:
            cp.parent.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps({"keyword": keyword, "rows": rows}, ensure_ascii=False),
                          encoding="utf-8")
        except Exception:                                        # noqa: BLE001
            pass
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--json")
    ap.add_argument("--images")
    ap.add_argument("--limit", type=int, default=15)
    ap.add_argument("--direct", action="store_true")
    args = ap.parse_args()
    if args.direct:
        os.environ["BIGGO_FETCH"] = "direct"

    all_results: dict[str, list[dict]] = {}
    seen: dict[str, dict] = {}

    for kw in args.keywords:
        try:
            items = search(kw)
        except Exception as exc:                                  # noqa: BLE001
            print(f"!! {kw}: {exc}", file=sys.stderr)
            continue
        all_results[kw] = items
        print(f"\n=== {kw}  ({len(items)} Shopee results) ===")
        shown = 0
        for row in items:
            url = row.get('purl') or ''
            if not url:
                continue
            seen.setdefault(url, row)
            if args.limit and shown >= args.limit:
                continue
            shown += 1
            var = f"  ({row['variants'].strip()})" if row.get('variants') else ''
            print(f"  {row.get('symbol','')}{row.get('price_text') or row.get('price')}   {(row.get('title') or '')[:100]}{var}")
            print(f"           {url}   [{(row.get('shop') or {}).get('name')}]")
            if args.images:
                m = ITEM_RE.search(url)
                if m and row.get('image'):
                    im = SHOPEE_IMG_RE.search(row['image'])
                    if im:
                        dst = os.path.join(args.images, f"{m.group(1)}_{m.group(2)}.jpg")
                        if not os.path.exists(dst):
                            try:
                                os.makedirs(args.images, exist_ok=True)
                                with open(dst, 'wb') as fh:
                                    fh.write(fetch(im.group(1), referer="https://shopee.com.my/"))
                                print(f"           image -> {dst}")
                            except Exception as exc:              # noqa: BLE001
                                print(f"           image failed: {exc}", file=sys.stderr)

    if args.json:
        with open(args.json, 'w', encoding='utf-8') as fh:
            json.dump(all_results, fh, ensure_ascii=False, indent=1)
        print(f"\nwrote {args.json}")

    print(f"\n{len(seen)} unique Shopee listings across {len(all_results)} queries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
