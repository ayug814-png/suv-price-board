# SUV Price Board

A live board of every Canadian listing for six 2025 SUVs, refreshed every 15 minutes:

| Column | What counts |
| --- | --- |
| Tucson Preferred w/ Panoramic Sunroof (gas) | Preferred trim with proof of the sunroof: Trend package, "panoramic"/"sunroof" in the title, Trend/SEL Convenience trim code, or a Preferred-with-Trend VIN (5NMJC…/3KMJC…) |
| Tucson Hybrid N Line | N Line hybrids (the lowest 2025 hybrid trim in Canada; panoramic sunroof is standard). Hybrids labelled "SEL Convenience" by US VIN decoders are shown as likely (?) because that VIN series also covers some Ultimates |
| CR-V EX-L Hybrid | EX-L trim, hybrid (or fuel not stated; EX-L is hybrid-only for 2025 in Canada) |
| CR-V Sport (gas) | Sport trim, gas engine (not Sport Hybrid / Sport Touring) |
| Sportage EX w/ Panoramic Sunroof (gas) | EX trim, gas engine, with proof of the sunroof: roof wording in the title or "panoramic sunroof" in the description (a plain "sunroof" in the description or a ticked sunroof box shows as likely (?)). Not EX Premium, X-Line or the hybrids; an EX whose ad doesn't state the fuel counts as gas unless it mentions a hybrid |
| Sportage EX Hybrid w/ Panoramic Sunroof | EX trim, hybrid (not the plug-in, EX Premium or SX), with the same proof of the sunroof |

Rows are cities, cells are prices, and every price links to the original ad. The same car posted on several sites shows once with
a link per site (AT = AutoTrader.ca, CG = CarGurus.ca, KJ = Kijiji, CP = Carpages.ca).

## Website (password-protected, runs 24/7)

Everything runs in the cloud; no PC needs to be on.

- **Site:** a Cloudflare Worker (`site/worker.js`) serves your domain. Visitors get a password page; the right password
  sets a 30-day sign-in cookie, and changing the password signs everyone out. Search engines are told not to index it.
- **Scans:** GitHub Actions (`.github/workflows/scan.yml`) runs `run.py` every 15 minutes, then `cloud_sync.py` stores the
  new board and its history in the site's Cloudflare KV storage.
- **Deploys:** `.github/workflows/deploy-site.yml` publishes the Worker. It runs when `site/` changes, or by hand.
- **Carpages** is switched off (`config.json`): its bot shield blocks cloud servers. Most of its cars are also on the other sites.

### One-time setup (works from a phone browser)

1. **Cloudflare API token.** dash.cloudflare.com → profile icon → *My Profile* → *API Tokens* → *Create Token* →
   *Edit Cloudflare Workers* template. Set *Account Resources* to your account and *Zone Resources* to your domain,
   then *Continue to summary* → *Create Token*, and copy the token (it's shown once).
2. **Cloudflare account ID.** On dash.cloudflare.com, open your domain; the *Account ID* is in the right-hand column
   (or *Workers & Pages* → right-hand column). Copy it.
3. **GitHub settings.** In this repo: *Settings* → *Secrets and variables* → *Actions*.
   - *Secrets* tab → *New repository secret*: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, and `BOARD_PASSWORD`
     (the password you'll type to see the board).
   - *Variables* tab → *New repository variable*: `BOARD_DOMAIN` (e.g. `mycarboard.com`) and `BOARD_HOME`
     (your city for distances, e.g. `North Bay, ON`).
4. **Deploy.** *Actions* → *Deploy site* → *Run workflow*. Then *Actions* → *Scan listings* → *Run workflow*.
   A few minutes later, open your domain and sign in.

### Later

- Change the password: update the `BOARD_PASSWORD` secret, then run *Deploy site* again.
- Scan right now: *Actions* → *Scan listings* → *Run workflow*.
- GitHub pauses scheduled workflows in public repos after 60 days without activity; the weekly keep-alive job prevents
  that. If GitHub ever emails that the schedule was disabled, re-enable it under *Actions*.
- Your home city lives in the `BOARD_HOME` variable (or `config.local.json` on a PC), not in the public code.

## Use it on a PC

- Open `board.html` in your browser. It reloads itself after each scheduled refresh.
- The refresh runs as the Windows scheduled task **SUV Price Board** (`install_schedule.ps1` creates it, `uninstall_schedule.ps1` removes it).
  It only runs while you're signed in; a run missed while the PC slept happens on wake.
- Run a refresh by hand: `python run.py` (add `--dump` to save every scanned ad and its match decision to `data/last_scan.json`).
- Rebuild the page without scanning, e.g. after changing `home`: `python run.py --render-only`.

## Settings (`config.json`)

- `home`: city used for the distance column and the "Nearest first" sort (set it in `config.local.json` or `BOARD_HOME`).
- `refresh_minutes`: re-run `install_schedule.ps1` after changing it.
- `price_floor` / `price_ceiling`: prices outside this range are treated as "no price" (placeholders like $1, payment-only ads).
- `remove_after_missed_runs`: how many complete scans in a row must miss an ad before it leaves the board.
- `sources`: switch individual sites off.

## Files

- `run.py`: one refresh (scan, match, update history, write `board.html`).
- `carboard/sources/`: one module per site. `carboard/targets.py`: the matching rules.
- `data/state.json`: listing history (first seen, price changes). `data/geocache.json`: city coordinates.
- `logs/run.log`: what each run did, including any site that failed.

Sites not covered: Facebook Marketplace (needs a login), Clutch.ca and dealer websites (their cars are syndicated to the sites above),
Canada Drives (no longer lists its own inventory).
