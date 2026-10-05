#!/usr/bin/env python3
"""Search Shopee MY listings through BigGo (shopee.com.my itself blocks this machine).

BigGo (my.biggo.com) indexes Shopee MY and embeds the full result set as an SSR JSON
blob inside the page HTML. This script fetches that page, parses the blob and prints
the Shopee entries as: price | title | product URL | [shop].

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

Run several keyword phrasings, Malay and English — BigGo's result sets differ per query,
and localised terms (ampaian baju, boleh laras, tanpa tebuk, sticker dinding, skirting)
reach listings that English keywords miss.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
ITEM_RE = re.compile(r"/product/(\d+)/(\d+)")
SHOPEE_IMG_RE = re.compile(r"(https://cf\.shopee\.com\.my/file/[^\"'\s]+)")


def fetch(url: str, referer: str | None = None) -> bytes:
    headers = {"User-Agent": UA, "Accept-Language": "en-MY,en;q=0.9"}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    return urllib.request.urlopen(req, timeout=45).read()


def parse_biggo(html: str) -> list[dict]:
    """Pull the SSR result list out of a BigGo search page."""
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
                return [it for it in items if 'shopee' in (it.get('nindex') or '')]
    return []


def search(keyword: str) -> list[dict]:
    url = "https://my.biggo.com/s/" + urllib.parse.quote(keyword)
    return parse_biggo(fetch(url).decode('utf-8', 'ignore'))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("keywords", nargs="+")
    ap.add_argument("--json")
    ap.add_argument("--images")
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()

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
        for it in items:
            url = it.get('purl') or ''
            if not url:
                continue
            row = {
                'title': it.get('title'),
                'url': url,
                'price': it.get('price'),
                'symbol': it.get('symbol'),
                'shop': (it.get('shop') or {}).get('name'),
                'location': (it.get('shop') or {}).get('location'),
                'ad': it.get('is_ad'),
                'variants': (it.get('multiple') or {}).get('title'),
                'image': it.get('origin_image') or it.get('image'),
            }
            seen.setdefault(url, row)
            if args.limit and shown >= args.limit:
                continue
            shown += 1
            var = f"  ({row['variants'].strip()})" if row['variants'] else ''
            print(f"  {row['symbol']}{row['price']:<8} {(row['title'] or '')[:100]}{var}")
            print(f"           {url}   [{row['shop']}]")
            if args.images:
                m = ITEM_RE.search(url)
                if m and row['image']:
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
