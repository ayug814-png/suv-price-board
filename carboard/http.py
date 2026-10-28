"""Polite HTTP client used by every source: browser headers, gzip, spacing between requests, retries."""
import gzip
import random
import time
import urllib.error
import urllib.request

BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
HTML_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
RETRYABLE = {403, 408, 429, 500, 502, 503, 504}


class FetchError(Exception):
    pass


class Fetcher:
    """One per site, so each site gets its own pacing (min_gap seconds plus random jitter between requests)."""

    def __init__(self, min_gap=2.0, jitter=1.5, timeout=45, retries=2, user_agent=BROWSER_UA):
        self.min_gap = min_gap
        self.jitter = jitter
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent
        self.requests = 0
        self._last = 0.0

    def _pace(self):
        wait = self._last + self.min_gap + random.uniform(0, self.jitter) - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def get(self, url, accept=HTML_ACCEPT):
        error = None
        for attempt in range(self.retries + 1):
            if attempt:
                time.sleep(8 * attempt)
            self._pace()
            request = urllib.request.Request(url, headers={
                "User-Agent": self.user_agent,
                "Accept": accept,
                "Accept-Language": "en-CA,en;q=0.9",
                "Accept-Encoding": "gzip",
            })
            self.requests += 1
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read()
                    if response.headers.get("Content-Encoding") == "gzip":
                        body = gzip.decompress(body)
                return body.decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                error = f"HTTP {e.code}"
                if e.code not in RETRYABLE:
                    break
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                error = str(getattr(e, "reason", e))
        raise FetchError(f"{error} for {url}")
