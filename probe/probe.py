"""Temporary probe: find where each brand's dealer locator gets its dealer list."""
import gzip
import re
import urllib.error
import urllib.parse
import urllib.request
import zlib

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"


def get(url, accept="text/html,application/xhtml+xml,*/*;q=0.8", timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept, "Accept-Language": "en-CA,en;q=0.9",
                                               "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            enc = r.headers.get("Content-Encoding", "")
            if enc == "gzip":
                body = gzip.decompress(body)
            elif enc == "deflate":
                body = zlib.decompress(body)
            return r.status, r.geturl(), r.headers.get("Content-Type", ""), body.decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, url, e.headers.get("Content-Type", "") if e.headers else "", ""
    except Exception as e:
        return 0, url, type(e).__name__ + ": " + str(e)[:120], ""


def title(html):
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:90] if m else ""


DEALERISH = re.compile(r"""["'`]((?:https?:)?//[^"'`\s]{3,200}|/[^"'`\s]{2,200})["'`]""")


def endpoints(text):
    found = set()
    for m in DEALERISH.finditer(text):
        s = m.group(1)
        low = s.lower()
        if ("dealer" in low or "retailer" in low or "locator" in low) and not low.endswith((".png", ".jpg", ".svg", ".css", ".webp", ".woff2")):
            found.add(s)
    return found


def discover(name, pages):
    print(f"\n===== {name} =====")
    for url in pages:
        status, final, ctype, html = get(url)
        print(f"{status} {url} -> {final} [{ctype[:40]}] {len(html)}b title={title(html)!r}")
        if not html:
            continue
        hrefs = sorted({h for h in re.findall(r'href="([^"]+)"', html) if "dealer" in h.lower()})[:15]
        if hrefs:
            print("  dealer hrefs:", hrefs)
        eps = endpoints(html)
        if eps:
            print("  in page:", sorted(eps)[:25])
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
        print(f"  {len(scripts)} scripts")
        seen = set()
        for src in scripts:
            full = urllib.parse.urljoin(final, src)
            if full in seen:
                continue
            seen.add(full)
            s2, _, _, js = get(full, accept="*/*")
            eps = endpoints(js)
            if eps:
                print(f"  in {full[:110]} ({len(js)}b):", sorted(eps)[:20])
        # inline JSON blobs that mention dealers
        for m in re.finditer(r'(.{0,80}(?:dealerList|dealers"|"dealerCode|dealerId).{0,200})', html):
            print("  inline:", m.group(1)[:280].replace("\n", " "))
            break
        break_after = status == 200
        if break_after:
            break


discover("KIA", ["https://www.kia.ca/en/find-a-dealer", "https://www.kia.ca/en/dealer-locator", "https://www.kia.ca/en"])
discover("HYUNDAI", ["https://www.hyundaicanada.com/en/find-a-dealer", "https://www.hyundaicanada.com/en/dealer-locator", "https://www.hyundaicanada.com/en"])
discover("HONDA", ["https://www.honda.ca/en/find-a-dealer", "https://www.honda.ca/en/dealerlocator", "https://www.honda.ca/en/dealer-locator", "https://www.honda.ca/en"])

print("\n===== AUTO123 directories =====")
for brand in ("kia", "hyundai", "honda"):
    url = f"https://www.auto123.com/en/new-cars/dealers/{brand}/ontario/"
    status, final, ctype, html = get(url)
    links = re.findall(r'href="([^"]*/dealers/[^"]+)"', html)
    ext = sorted({h for h in re.findall(r'href="(https?://[^"]+)"', html) if "auto123" not in h})[:12]
    print(f"{status} {url} {len(html)}b title={title(html)!r} dealer-links={len(set(links))} sample={sorted(set(links))[:5]}")
    print("  external:", ext)
    m = re.search(r"(\d+)\s+results", html)
    print("  results:", m.group(1) if m else None)
