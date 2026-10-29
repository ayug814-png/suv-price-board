"""Listing history between runs: first/last seen, price changes, and dropping listings that disappear."""
import datetime
import json
from pathlib import Path

KEEP_GONE_FOR = datetime.timedelta(days=7)
KEEP_UNREAD_FOR = datetime.timedelta(days=2)  # a dealer site that keeps failing stops vouching for its cars


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, path):
        self.path = Path(path)
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}
        self.data.setdefault("listings", {})
        self.data.setdefault("sources", {})
        self.data.setdefault("gone", {})  # history of recently removed ads, in case one comes back

    @property
    def listings(self):
        return self.data["listings"]

    @property
    def sources(self):
        return self.data["sources"]

    def merge(self, source, result, matched, now, remove_after, target_keys):
        """Fold one source's scan into the history.

        A listing only counts as gone after `remove_after` complete scans of its site in a row miss it,
        so a scan that failed part-way never wipes listings off the board. For a source made of many sites, a site
        that couldn't be read (result.incomplete) keeps its listings for up to KEEP_UNREAD_FOR.
        """
        status = self.sources.setdefault(source, {})
        # Whatever a site's first scan (or a newly added column's first scan) finds is the starting
        # inventory, not "new".
        scanned_targets = set(status.get("targets", [])) if "first_ok" in status else set()
        complete = not result.errors
        status.update(last_run=now, scanned=len(result.listings), matched=len(matched),
                      requests=result.requests, errors=result.errors[:3], notes=result.notes)
        if complete:
            status.setdefault("first_ok", now)
            status["last_ok"] = now
            status["targets"] = sorted(target_keys)

        gone = self.data["gone"]
        seen = set()
        for listing in matched:
            record = listing.record()
            # An ad that dropped off and came back keeps its history, so it isn't flagged as new.
            previous = self.listings.get(listing.key) or gone.pop(listing.key, None)
            if previous:
                history = previous["price_history"]
                if listing.price != history[-1][1]:
                    history.append([now, listing.price])
                record.update(first_seen=previous["first_seen"], baseline=previous.get("baseline", False),
                              price_history=history[-20:])
            else:
                record.update(first_seen=now, baseline=listing.target not in scanned_targets,
                              price_history=[[now, listing.price]])
            record.update(last_seen=now, missed=0)
            self.listings[listing.key] = record
            seen.add(listing.key)

        if complete:
            unread = tuple(f"{part}:" for part in result.incomplete)
            unread_cutoff = (datetime.datetime.fromisoformat(now.replace("Z", "+00:00"))
                             - KEEP_UNREAD_FOR).isoformat().replace("+00:00", "Z")
            for key, record in list(self.listings.items()):
                if record["source"] == source and key not in seen:
                    if record["source_id"].startswith(unread) and record["last_seen"] >= unread_cutoff:
                        continue
                    record["missed"] = record.get("missed", 0) + 1
                    if record["missed"] >= remove_after:
                        gone[key] = {k: record[k] for k in ("first_seen", "baseline", "price_history")} | {"gone_at": now}
                        del self.listings[key]
        cutoff = (datetime.datetime.fromisoformat(now.replace("Z", "+00:00")) - KEEP_GONE_FOR).isoformat().replace("+00:00", "Z")
        for key in [k for k, record in gone.items() if record["gone_at"] < cutoff]:
            del gone[key]

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        tmp.replace(self.path)
