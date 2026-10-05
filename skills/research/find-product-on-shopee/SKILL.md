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
   Fetches fine with ordinary curl/python. The HTML embeds an SSR JSON blob containing the
   whole result list. Parse it:
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

`web_search` also returns shopee.com.my `/list/...` and `/product/...` results with names and
prices, which is a good fallback or cross-check, but it is flaky (403/timeout) and gives no
structured price data.

## 3. Reporting

Give: the product in plain words plus the spec that identifies it (size range, material, mount
type), the Malay + English keywords that find it, and 5-8 concrete listing links with prices and
shop names. Say plainly that prices come from BigGo's index of Shopee and that Shopee itself could
not be opened from this machine, so the user should verify on click.
