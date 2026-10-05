---
name: batch-folder-processing
description: Use when processing many similar numbered folders.
---

# Working a large set of similar folders

The shape: hundreds or thousands of sibling folders built to one contract (`... 5/`, `... 15/`,
`... 3220/`), each holding the same kinds of file, and the user wants the same analysis or content
out of every one. The work is cheap per folder and ruinous to do wrong across the set, so the
procedure is about the *batch*, not the per-folder cleverness.

## 1. Read the folder contract before the first folder

Look for the script that created the layout and read it — it tells you how files were produced, and
sometimes which parts are generated noise rather than content:

    search_files pattern="*.py" target="files" path=<root>     # the builder script usually sits at the root

In the affiliate video layout this is decisive: a root `images.py` samples frames every 3 s into
`<name>/IMG/frame_N.jpg`, moves the video into `<name>/`, and writes `<name>/<name>.txt` with a
**randomised** CTA line plus a **fixed** affiliate short link. Consequences worth remembering: the
frames already cover the video (prefer them over re-deriving), and the `.txt` link is one constant
reused across every folder, so it rarely identifies that folder's product — treat it as marketing
copy, never as ground truth.

Also get the count: `find . -maxdepth 1 -type d | wc -l`. Report it and keep it for the final audit.

## 2. One folder end-to-end, then report and stop

Do a single folder completely — the real deliverable, in the real output format — and report it.
The user asks for exactly this ("try one folder first"): the first folder is a check on the method
before the method is applied thousands of times, and a wrong interpretation caught here costs one
folder instead of all of them. Do not open with a sweep, and do not present a bulk plan as progress.

Pick the folder deliberately: an early numbered one with the full set of files present, not a
partially-built or already-processed one. When the user names a folder or path, use it as given.

## 3. Batch hygiene once the method is approved

- **Write results out as you go**, one file per batch, to a durable workspace path under the
  project (`~/.hermes/workspace/<project>/`). The scratch directory is pruned; a run that only
  exists in context is lost to a timeout.
- **Append a record per folder** to JSON/CSV with the folder path and the extracted fields, then
  dedupe, count and sort with Python against that file rather than reasoning over results in
  context. Sample a few lines back from disk to confirm the format before scaling up.
- **Audit the count before answering**: collected records vs folders processed, both printed. A
  declared total is a hard claim; re-read the file if the numbers disagree instead of going with
  what you have.
- **Keep reference data across folders**: products, listings and lookups repeat between folders, so
  one shared candidate/cache file saves re-deriving the same answer per folder.
- **Two outputs, not one**: a short curated report per batch for reading, plus the raw record file
  for machine use. Keep the raw file append-only so nothing is lost between batches.

## 4. Reporting convention

State the absolute path of every file you produce in the reply — in a plain CLI session a `MEDIA:`
tag prints as literal text and delivers nothing, so the path is the delivery mechanism. Lead with
what the batch produced and how many folders it covered, then the file paths, then anything you
could not resolve. Keep per-folder detail out of the reply; it belongs in the files.

Per-folder sub-tasks that have their own hard-won route (e.g. finding a product on Shopee) belong in
their own skill — this one governs the batch mechanics and hands off to them.
