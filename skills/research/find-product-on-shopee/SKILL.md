---
name: find-product-on-shopee
description: Find a video's product on Shopee MY via frames + BigGo.
---

# Finding a product on Shopee MY from a video/image

## 1. Identify the product from the frames (never from the video)

Affiliate video folders (MyRezeki style) look like `<Name>/<Name>.mp4` + `<Name>/IMG/frame_N.jpg`.
The IMG frames were sampled every 3 s by the folder's own `images.py`, so they already cover the
video. Read them with `vision_analyze` (`frame_0`, `frame_1`, `frame_2`, ...) — do not extract new
frames, do not play the video.

Ask per frame for: product type, material, colour, end fittings, adjustable range, installed use
and any on-screen text. A product is usually only fully clear on the frame where it is installed,
not the one where a person holds it.

Also read `<Name>.txt` — but treat its CTA + `s.shopee.com.my/...` short link as marketing copy:
the link is a single constant reused across every folder (`images.py` only randomises the CTA
line), so it usually does NOT point at the product shown in that video. Report this if relevant.

## 2. shopee.com.my is blocked from this machine — go through BigGo

Direct access always fails. Observed on every route: browser (desktop and iPhone UA), plain curl,
and the `/api/v4/...` endpoints all land on `shopee.com.my/verify/traffic/error` or return
`{"error":90309999, "redirect_to_error_page":true}`. The interstitial's language buttons do not
clear it; the fallback page reads "Page Unavailable. Please log in and try again."
Do not burn many calls retrying, and do not ask the user for Shopee credentials for this.

Working routes, in order:

1. **BigGo Malaysia** — `https://my.biggo.com/s/<url-encoded keyword>`
   **Use `scripts/biggo_search.py`** — it does everything below in one call:

   ```
   python3 scripts/biggo_search.py --limit 10 --json out.json --images /tmp/img "kw1" "kw2"
   ```

   Pass several keyword phrasings in one run (results are deduped across them), and `--images DIR`
   to download each listing's own product image from the Shopee CDN for visual confirmation.

   Manual route, if you need it: the page fetches fine with ordinary curl/python. The HTML embeds
   an SSR JSON blob containing the whole result list. Parse it:
   - normalise the JS-escaped payload: `raw.replace('\\"','"').replace('\\u0026','&')`
   - locate `"list":[` and bracket-match to the closing `]`
   - `json.loads` that slice; keep entries whose `nindex` contains `shopee`
   - useful fields per item: `title`, `purl` (real shopee.com.my/product/<shop>/<item> URL),
     `price`, `symbol`, `shop.name`, `shop.location`, `origin_image`, `is_ad`, `multiple`
   Run 3-4 different keyword phrasings (English + Malay) — BigGo result sets differ per query.
   Localise the keyword: for Malaysian home goods, `ampaian baju`, `boleh laras`, `tanpa tebuk`,
   `batang langsir` reach products that English keywords miss.

2. **Image confirmation** — Shopee's CDN is not blocked: fetch the `cf.shopee.com.my/file/...` URL
   from `origin_image` (send `Referer: https://shopee.com.my/`) and inspect it with `vision_analyze`
   to confirm the listing really is the product in the frame before recommending it.

### When BigGo walls you (`verifylogin`)

BigGo rate-limits by IP. After a few hundred requests in an hour every `/s/` URL 307-redirects to
`my.biggo.com/verifylogin` (or answers `{"message":"Access denied"}` in a browser), and the same
wall then hits any proxy that shares the reputation — `r.jina.ai` returns a Cloudflare 403, the free
CORS proxies (`allorigins`, `codetabs`) 520/522, `search.brave.com` 429. Google serves its
"unusual traffic" CAPTCHA, Bing/DDG/searx return no `shopee.com.my/product/...` URLs at all, and
`web_extract` on a Shopee URL answers "page was reached but content could not be extracted".

So: **do not thrash.** The identification half of the job still works while the search half is
walled — run that, write the reports with the keyword lists, and fill in the listings later with
`scripts/backfill_listings.py`, which re-reads each report's keywords and rewrites only the listings
section once BigGo answers again (it prints `BLOCKED` and changes nothing while the wall is up).
Space requests out (`BIGGO_MIN_GAP`, default 1.2 s) and keep concurrency at 2-3 — a burst is what
sets the wall off.

`web_search` also returns shopee.com.my `/list/...` and `/product/...` results with names and
prices, which is a good fallback or cross-check, but it is flaky (403/timeout) and gives no
structured price data.

## 3. Where the result goes

**Write the finished product info into the ROOT of the folder you researched** — the same folder
as the video and its `IMG/`, named `shopee-product-match.md`. Not into `~/.hermes/workspace/`,
not into `$HERMES_HOME` — the files belong with the source material so they travel with it.

```
<researched folder>/shopee-product-match.md
```

- One file per researched folder. Re-running the folder overwrites that file.
- Keep it to the finding: product, identifying spec, keywords, listing links + prices, caveats.
- Raw working files (BigGo HTML/JSON, listing images) stay in the scratch dir — do NOT leave them
  inside the researched folder's root. If you must keep them beside the finding, use a subfolder
  like `img/` or `raw/`.
- On a batch run, write one file per folder as you go, and put the index/roll-up at the root of
  the parent folder that holds the batch.
- Report the absolute path you wrote so the user can open it directly.

## 4. Batch runs (a whole folder set)

`scripts/batch_product_match.py ROOT --only-missing --workers 3`

Per folder it sends the sampled frames to the vision model, gets back JSON (English + Malay product
name, category, look, use, 4-6 Shopee keywords, confidence, clearest frame), runs those keywords
through `biggo_search.py`, writes `<folder>/shopee-product-match.md` and appends a row to
`ROOT/_product-match-index.md`. It is resumable: `--only-missing` skips folders that already have a
report. Read `ROOT/_batch-results.json` for the machine-readable roll-up, and check the
low-confidence rows by eye before trusting them.

Make the vision half free: point the auxiliary vision backend at a cheap/free model instead of
paying the main model to look at pixels —
`hermes config set auxiliary.vision.provider nous` +
`hermes config set auxiliary.vision.model meituan/longcat-2.5-preview:free` +
`hermes config set auxiliary.free_only true`. Verify in `state.db` (`session_model_usage`): the
vision rows should read `cost $0.000000`, `billing_provider=nous`. Trade-off: the free VLM is slow
(~25 s per call) and describes frames less sharply than a strong paid model, so keep the paid model
for ambiguous folders.

## 5. Reporting

Give: the product in plain words plus the spec that identifies it (size range, material, mount
type), the Malay + English keywords that find it, and 5-8 concrete listing links with prices and
shop names. Say plainly that prices come from BigGo's index of Shopee and that Shopee itself could
not be opened from this machine, so the user should verify on click.
