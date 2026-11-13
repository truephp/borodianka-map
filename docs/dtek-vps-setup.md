# DTEK on existing Ubuntu 24.04 VPS

This is a **new, independent service**. It does not alter the existing
Tactical Kitchen, Nextcloud AIO, or their Nginx virtual hosts.

- Public hostname: `dtek.theredcat.top`
- Collector: existing `scripts/fetch_dtek_shared_houses.py` (one Playwright session for `DisconSchedule.fact` + all house AJAX calls)
- Publisher: `scripts/run_dtek_vps.py`
- Timing: every 15 minutes, `systemd` timer
- No database, Node, R2 credentials, Visicom or encrypted cross-source geometry
- **Do not disable GitHub Actions or switch the map until the VPS URLs work.**

## 1. DNS

Create DNS A record `dtek.theredcat.top` pointing to this VPS public IPv4.
If an AAAA record exists, it must point to a working IPv6 on the same VPS.
Use DNS-only mode initially if Cloudflare proxy interferes with certificate
issuance. Allow inbound ports 80 and 443 (reuse existing Nginx).

## 2. Install on VPS

Run as a sudo-capable SSH user. These commands use the existing Nginx installation.

```bash
sudo apt-get update
sudo apt-get install -y git python3-venv python3-pip nginx certbot python3-certbot-nginx util-linux
sudo useradd --system --create-home --home-dir /var/lib/dtek-collector --shell /usr/sbin/nologin dtek 2>/dev/null || true
sudo install -d -o dtek -g dtek -m 0755 /var/lib/dtek-collector
sudo install -d -o dtek -g dtek -m 0755 /var/www/dtek/v1/borodianka
sudo git clone https://github.com/truephp/borodianka-map.git /opt/dtek-collector
sudo python3 -m venv /opt/dtek-collector/.venv
sudo /opt/dtek-collector/.venv/bin/python -m pip install 'playwright>=1.50,<2'
sudo /opt/dtek-collector/.venv/bin/python -m playwright install-deps chromium
sudo -u dtek env HOME=/var/lib/dtek-collector /opt/dtek-collector/.venv/bin/python -m playwright install chromium
```

For later updates: `sudo git -C /opt/dtek-collector pull --ff-only`.
The source checkout may be root-owned; do not make Nginx or other services
writeable there.

## 3. Configure service + test a single run

```bash
sudo install -m 0644 /opt/dtek-collector/deploy/vps/dtek-collector.service /etc/systemd/system/dtek-collector.service
sudo install -m 0644 /opt/dtek-collector/deploy/vps/dtek-collector.timer /etc/systemd/system/dtek-collector.timer
sudo systemctl daemon-reload
sudo systemctl start dtek-collector.service
sudo journalctl -u dtek-collector.service --no-pager -n 80
sudo ls -l /var/www/dtek/v1/borodianka/
python3 -m json.tool /var/www/dtek/v1/borodianka/status.json
```

Expected: `schedule.json`, `houses.json`, `status.json`.
A service failure can still publish the valid schedule independently.
Known `getHomeNum` errors for up to two streets appear explicitly in
`houses.json.errors`. No stale house values are filled in for them.

Only after a successful test, enable periodic runs:

```bash
sudo systemctl enable --now dtek-collector.timer
systemctl list-timers dtek-collector.timer --all
```

The service uses `flock -n` to avoid simultaneous runs. A missed busy
interval will be skipped instead of overlapping. `Persistent=true` catches up
after server downtime. If the service fails, the next timer event retries.

## 4. Add Nginx virtual host without touching existing hosts

```bash
sudo install -m 0644 /opt/dtek-collector/deploy/vps/dtek.theredcat.top.nginx /etc/nginx/sites-available/dtek.theredcat.top
sudo ln -s /etc/nginx/sites-available/dtek.theredcat.top /etc/nginx/sites-enabled/dtek.theredcat.top
sudo nginx -t
sudo systemctl reload nginx
curl -i -H 'Host: dtek.theredcat.top' http://127.0.0.1/v1/borodianka/status.json
```

Once DNS resolves to the VPS and HTTP succeeds, obtain HTTPS for **only**
the new name (existing certificates/hosts remain):

```bash
sudo certbot --nginx -d dtek.theredcat.top
sudo nginx -t && sudo systemctl reload nginx
curl -i https://dtek.theredcat.top/v1/borodianka/status.json
curl -i https://dtek.theredcat.top/v1/borodianka/schedule.json
curl -i https://dtek.theredcat.top/v1/borodianka/houses.json
```

Files are public JSON and serve `Access-Control-Allow-Origin: *`,
allowing the Borodianka map to fetch them cross-origin.

## 5. Cut over safely (separate change)

After observing several timer cycles and checking that JSON timestamps advance:

1. Update the Borodianka frontend to load `schedule.json` and `houses.json`
   from the VPS endpoint. The current frontend still expects the encrypted
   **pre-matched Visicom** report; keep its last valid static report until the
   map implements joining the live DTEK address updates to previously reviewed
   address-to-building IDs.
2. Stop scheduled GitHub polling by deleting the `schedule` and watchdog
   dispatch triggers in the repository; leave manual dispatch for diagnostics.
3. Check that no GitHub workflow publishes an older snapshot over the new VPS
   data. The new VPS endpoint does not share a destination with existing R2
   publishing, so there is no overwrite until frontend cutover.
4. Monitor `journalctl -u dtek-collector.service` and `status.json`
   (`lastAttemptAt`, `schedule.ok`, `houses.ok`) or set up external alerting.

## API shapes

`/v1/borodianka/schedule.json`: same normalized GPV format as the existing
`dtek-gpv-schedule.json` (dates, groups and hourly slots).

`/v1/borodianka/houses.json`: `schemaVersion`, `source`, `fetchedAt`,
`processedAt`, `complete`, `streetPairs`, `successfulPairs`, `errors`,
`counts` and `addresses`. Each entry carries `city`, `street`, `house`,
`raw` (seven original DTEK fields) and `signal`. An empty DTEK response
does NOT prove that electricity is available.

`/v1/borodianka/status.json`: timestamp and success/error summaries of
the **most recent attempt**. A failed attempt must not overwrite previous
valid dataset files: consumers must use each dataset's `fetchedAt` to check
actual freshness.

## Troubleshooting

```bash
sudo systemctl status dtek-collector.service --no-pager
sudo journalctl -u dtek-collector.service --since '2 hours ago' --no-pager
sudo systemctl list-timers --all | grep dtek
sudo -u dtek test -w /var/www/dtek/v1/borodianka && echo writable
sudo nginx -t
```
