"""Citation link audit - does every source we cite still resolve?

TIER A of the citation audit. This checks ONE thing: that the URL
is reachable. It does NOT check that the document says what we claim - that is
Tier B, and it has to be done by reading, one source at a time.

Worth being precise about the difference, because it is the whole lesson of
this audit: the LBNL room-AC citation RESOLVES PERFECTLY and says the opposite
of what was attributed to it. A green link is not a verified claim.

What a green link does buy: no examiner opens a footnote and gets a 404.

Status interpretation, which matters on Indian government sites:
  200        fine
  403        very often a bot block, NOT a dead page - flag for manual check
  404 / 410  genuinely dead, must be replaced
  timeout    slow gov server or dead; flag for manual check
"""
from __future__ import annotations

import os
import re
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import urllib.request
import urllib.error
import ssl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)

# Directories whose citations drive MODEL NUMBERS. _spec is documentation and
# is checked separately at write-up time.
SCAN = ["config", "energy", "core", "layout"]
# BUG FIX the first version of this regex omitted "$" and "!",
# which silently TRUNCATED the Bain EV URL at "...create-a-" and then
# reported the truncated string as a dead link. A link checker that
# mangles the link before checking it manufactures its own findings.
URL_RE = re.compile(r"https?://[A-Za-z0-9./_%?=&#~+,:$!*'()@;-]+")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def collect():
    """url -> list of 'file:line' where it is cited."""
    found = defaultdict(list)
    for d in SCAN:
        for dirpath, _dirs, files in os.walk(d):
            if "__pycache__" in dirpath:
                continue
            for fn in files:
                if not fn.endswith((".yaml", ".yml", ".py")):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        for i, line in enumerate(fh, 1):
                            for m in URL_RE.findall(line):
                                # keep a trailing "/" - it is significant on some servers
                                if "w3.org/2000/svg" in m:
                                    continue   # XML namespace, not a citation
                                u = m.rstrip(".,);:'\"")
                                found[u].append("%s:%d" % (path, i))
                except OSError:
                    continue
    return found


def check(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA},
                                 method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ctx) as r:
            return r.status, ""
    except urllib.error.HTTPError as e:
        # Many servers reject HEAD but serve GET. BUG FIX 404 is
        # in this list too - prana.cpcb.gov.in and www.pspcl.in both answer
        # 404 to HEAD and 200 to GET, and were wrongly reported dead.
        if e.code in (403, 404, 405, 501):
            try:
                req2 = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req2, timeout=timeout,
                                            context=_ctx) as r2:
                    return r2.status, "(GET)"
            except urllib.error.HTTPError as e2:
                return e2.code, ""
            except Exception as e2:
                return -1, type(e2).__name__
        return e.code, ""
    except Exception as e:
        return -1, type(e).__name__


def main():
    urls = collect()
    print("citation link audit - %d unique URLs across %s"
          % (len(urls), ", ".join(SCAN)))
    print("checking (green link != verified claim; see the module docstring)")
    print()
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=12) as ex:
        results = list(ex.map(lambda u: (u,) + check(u), sorted(urls)))

    buckets = defaultdict(list)
    for url, code, note in results:
        if code == 200:
            buckets["ok"].append((url, code, note))
        elif code in (404, 410):
            buckets["dead"].append((url, code, note))
        elif code == 403:
            buckets["blocked"].append((url, code, note))
        else:
            buckets["other"].append((url, code, note))

    def show(key, title):
        rows = buckets.get(key) or []
        print("=" * 74)
        print("%s  (%d)" % (title, len(rows)))
        print("=" * 74)
        for url, code, note in sorted(rows):
            print("  [%s] %s %s" % (code, url, note))
            if key in ("dead", "other"):
                for site in urls[url][:3]:
                    print("        cited at %s" % site)
        print()

    show("dead", "DEAD - must be replaced before submission")
    show("other", "UNREACHABLE - timeout or error; check manually")
    show("blocked", "403 - usually a bot block, not a dead page; spot-check")
    print("=" * 74)
    print("OK (200): %d" % len(buckets.get("ok") or []))
    print("elapsed %.0f s" % (time.time() - t0))
    print()
    print("REMINDER: this is Tier A. It proves the page exists, not that it")
    print("says what we claim. Tier B is reading the source - and the LBNL")
    print("room-AC citation would pass Tier A while saying the opposite of")
    print("what was attributed to it.")


if __name__ == "__main__":
    main()
