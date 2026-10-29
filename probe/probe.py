"""Temporary probe #2: find each brand's dealer list (sitemaps, API strings in page code)."""
import gzip
import re
import urllib.error
import urllib.parse
import urllib.request
import zlib

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"


def get(url, accept="text/html,application/xhtml+xml,*/*;q=0.8", timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en-CA,en;q=0.9",
                                               "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            enc = r.headers.get("Content-Encoding", "")
            if enc == "gzip" or body[:2] == b"\x1f\x8b":
                body = gzip.decompress(body)
            elif enc == "deflate":
                body = zlib.decompress(body)
            return r.status, r.geturl(), r.headers.get("Content-Type", ""), body.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, "", ""
    except Exception as e:
        return 0, url, type(e).__name__ + ": " + str(e)[:100], ""


STR = re.compile(r"""["'`]([^"'`\s<>]{4,220})["'`]""")
INTEREST = re.compile(r"dealer|retailer|/api/|graphql|\.ashx|/services/|locator", re.I)
SKIP = re.compile(r"\.(png|jpe?g|svg|css|webp|woff2?|gif|ico)(\?|$)|^kca\.global|^#", re.I)


def strings_of_interest(text, limit=40):
    out = []
    for m in STR.finditer(text):
        s = m.group(1)
        if INTEREST.search(s) and not SKIP.search(s) and s not in out:
            out.append(s)
            if len(out) >= limit:
                break
    return out


def sitemaps(base):
    status, _, _, robots = get(base + "/robots.txt", accept="text/plain,*/*")
    maps = re.findall(r"(?im)^sitemap:\s*(\S+)", robots) or [base + "/sitemap.xml"]
    print(f"  robots.txt {status}; sitemaps: {maps[:6]}")
    seen, queue, dealer_urls = set(), list(maps), []
    while queue and len(seen) < 25:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        status, _, _, xml = get(url, accept="application/xml,text/xml,*/*")
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        subs = [l for l in locs if l.endswith(".xml") or "sitemap" in l.lower()]
        hits = [l for l in locs if re.search(r"dealer|retailer|concession", l, re.I)]
        print(f"  {status} {url} locs={len(locs)} sub={len(subs)} dealer-ish={len(hits)} {hits[:4]}")
        dealer_urls += hits
        queue += [s for s in subs if re.search(r"dealer|retailer|page|en|default|sitemap", s, re.I)][:15]
    return dealer_urls


def deep(name, base, page):
    print(f"\n===== {name} =====")
    dealer_urls = sitemaps(base)
    print(f"  total dealer-ish sitemap urls: {len(dealer_urls)} sample: {dealer_urls[:8]}")
    status, final, ctype, html = get(page)
    print(f"  page {status} {final} {len(html)}b")
    print("  page strings:", strings_of_interest(html))
    scripts = list(dict.fromkeys(urllib.parse.urljoin(final, s) for s in re.findall(r'<script[^>]+src="([^"]+)"', html)))
    print("  scripts:", [s[:100] for s in scripts][:30])
    for src in scripts:
        s2, _, _, js = get(src, accept="*/*")
        found = strings_of_interest(js, 25)
        if found:
            print(f"  -- {src[:100]} ({len(js)}b): {found}")
        # webpack chunk maps: look for chunk file names mentioning dealer
        for m in re.finditer(r'["\']([^"\']*[Dd]ealer[^"\']*\.js)["\']', js):
            print("     chunk:", m.group(1)[:120])


deep("HONDA", "https://www.honda.ca", "https://www.honda.ca/en/dealerlocator")
deep("KIA", "https://www.kia.ca", "https://www.kia.ca/en")
deep("HYUNDAI", "https://www.hyundaicanada.com", "https://www.hyundaicanada.com/en")
