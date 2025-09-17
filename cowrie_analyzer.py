#!/usr/bin/env python3
"""
cowrie_analyzer_geo_fallback.py
- Parses cowrie docker logs and generates CSVs + plots.
- Uses local GeoLite2 DB if available; otherwise falls back to ip-api.com (batched).
- Caches API responses in ~/.cowrie_geo_cache.json
"""
import re, csv, subprocess, os, json, hashlib, time
from collections import Counter, defaultdict
from datetime import datetime

# try imports
try:
    import geoip2.database
except Exception:
    geoip2 = None
try:
    import requests
except Exception:
    requests = None
try:
    import matplotlib.pyplot as plt
except Exception:
    plt = None

# -------------
# CONFIG
# -------------
LOG_DURATION = "24h"   # change as needed
GEO_DB = "/usr/share/GeoIP/GeoLite2-Country.mmdb"
OUTPUT_DIR = "analysis_output"
CACHE_FILE = os.path.expanduser("~/.cowrie_geo_cache.json")
TOP_N = 50
ANON_HASH = True

# -------------
# HELPERS
# -------------
ip_re = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")
login_re = re.compile(r"login attempt \[([^\]/]+)\/?([^\]]*)\]")
cmd_re = re.compile(r"CMD: (.+)", re.IGNORECASE)
ts_re = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})")

def sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    try:
        with open(CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except Exception as e:
        print("[!] Failed to write cache:", e)

# -------------
# LOG COLLECTION
# -------------
print("[*] Fetching logs from Cowrie (this may take a moment)...")
try:
    cmd = ["sudo", "docker", "logs", "--since", LOG_DURATION, "cowrie"]
    logs_raw = subprocess.check_output(cmd, text=True, errors="ignore")
except Exception as e:
    print("[!] Failed to fetch docker logs. Make sure you can run 'sudo docker logs cowrie'.")
    raise

logs = logs_raw.splitlines()

# -------------
# PARSE
# -------------
ips = []
creds = []
cmds = []
timeline = defaultdict(int)

for line in logs:
    m = ip_re.search(line)
    if m:
        ips.append(m.group())

    lm = login_re.search(line)
    if lm:
        user = lm.group(1).strip()
        pw = lm.group(2).strip() if lm.group(2) is not None else ""
        creds.append((user, pw))

    cm = cmd_re.search(line)
    if cm:
        cmds.append(cm.group(1).strip())

    tm = ts_re.search(line)
    if tm:
        try:
            dt = datetime.fromisoformat(tm.group(1))
            timeline[dt.hour] += 1
        except:
            pass

ip_counts = Counter(ips)
cred_counts = Counter(creds)

# -------------
# GEO RESOLUTION (DB first, then API with cache)
# -------------
print("[*] Resolving IP -> Country (DB fallback -> ip-api.com)...")
country_map = {}
cache = load_cache()

# try GeoLite2 DB if available
use_db = False
if geoip2 is not None and os.path.exists(GEO_DB):
    try:
        reader = geoip2.database.Reader(GEO_DB)
        use_db = True
    except Exception as e:
        use_db = False

if use_db:
    for ip in ip_counts:
        try:
            resp = reader.country(ip)
            country = resp.country.name or resp.country.iso_code or "Unknown"
        except Exception:
            country = "Unknown"
        country_map[ip] = country
    reader.close()
else:
    # fallback to cache / ip-api.com
    # build list of IPs needing lookup
    to_lookup = [ip for ip in ip_counts if ip not in cache]
    # batch up to 100 per request (ip-api supports batch)
    if to_lookup and requests is None:
        print("[!] requests not installed. Cannot call ip-api.com. Countries will be 'Unknown' unless you install requests.")
        # mark remaining as Unknown or cached if present
        for ip in ip_counts:
            country_map[ip] = cache.get(ip, "Unknown")
    else:
        BATCH = 100
        for i in range(0, len(to_lookup), BATCH):
            batch = to_lookup[i:i+BATCH]
            try:
                resp = requests.post("http://ip-api.com/batch", json=batch, timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data:
                        qip = item.get("query")
                        country = item.get("country") or item.get("countryCode") or "Unknown"
                        cache[qip] = country
                    # respect courtesy limit: small pause
                    time.sleep(1.2)
                else:
                    print("[!] ip-api batch returned", resp.status_code)
                    # fallback mark Unknown for this batch
                    for qip in batch:
                        cache[qip] = "Unknown"
            except Exception as e:
                print("[!] ip-api request failed:", e)
                for qip in batch:
                    cache[qip] = "Unknown"
        # now fill country_map from cache
        for ip in ip_counts:
            country_map[ip] = cache.get(ip, "Unknown")

# save cache for future runs
save_cache(cache)

# -------------
# OUTPUT DIR
# -------------
os.makedirs(OUTPUT_DIR, exist_ok=True)

# attackers CSV and hashed CSV
attackers = []
for ip, cnt in ip_counts.most_common(TOP_N):
    attackers.append((ip, cnt, country_map.get(ip, "Unknown")))

plain_csv = os.path.join(OUTPUT_DIR, "cowrie_attackers.csv")
hashed_csv = os.path.join(OUTPUT_DIR, "cowrie_attackers_hashed.csv")

with open(plain_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["IP", "Count", "Country"])
    for row in attackers:
        w.writerow(row)
print(f"[+] Wrote {plain_csv}")

if ANON_HASH:
    with open(hashed_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Hash", "Count", "Country"])
        for ip, cnt, country in attackers:
            h = sha256_hex(ip)
            w.writerow([h, cnt, country])
    print(f"[+] Wrote {hashed_csv} (SHA-256)")

# creds
creds_csv = os.path.join(OUTPUT_DIR, "cowrie_creds.csv")
with open(creds_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Username", "Password", "Count"])
    for (u, p), c in cred_counts.most_common(TOP_N):
        w.writerow([u, p, c])
print(f"[+] Wrote {creds_csv}")

# commands
cmds_file = os.path.join(OUTPUT_DIR, "cowrie_cmds.txt")
with open(cmds_file, "w") as f:
    for c in sorted(set(cmds)):
        f.write(c + "\n")
print(f"[+] Wrote {cmds_file}")

# timeline
timeline_csv = os.path.join(OUTPUT_DIR, "cowrie_timeline.csv")
with open(timeline_csv, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["Hour", "Attempts"])
    for hour in range(24):
        w.writerow([hour, timeline.get(hour, 0)])
print(f"[+] Wrote {timeline_csv}")

# -------------
# PLOTTING
# -------------
if plt is not None:
    try:
        top = attackers[:10]
        labels = [f"{ip}\n({cnt})" for ip, cnt, _ in top]
        counts = [cnt for _, cnt, _ in top]
        plt.figure(figsize=(10,6))
        plt.barh(labels[::-1], counts[::-1])
        plt.title("Top Attacker IPs (last {})".format(LOG_DURATION))
        plt.xlabel("Attempts")
        plt.tight_layout()
        out_top = os.path.join(OUTPUT_DIR, "top_ips.png")
        plt.savefig(out_top)
        plt.close()
        print(f"[+] Wrote {out_top}")

        topcreds = cred_counts.most_common(10)
        if topcreds:
            labels = [f"{u}/{p}" for (u,p), _ in topcreds]
            counts = [c for _, c in topcreds]
            plt.figure(figsize=(10,6))
            plt.barh(labels[::-1], counts[::-1])
            plt.title("Top Credential Attempts")
            plt.xlabel("Attempts")
            plt.tight_layout()
            out_creds = os.path.join(OUTPUT_DIR, "top_creds.png")
            plt.savefig(out_creds)
            plt.close()
            print(f"[+] Wrote {out_creds}")

        hours = list(range(24))
        vals = [timeline.get(h,0) for h in hours]
        plt.figure(figsize=(10,4))
        plt.plot(hours, vals, marker="o")
        plt.xticks(hours)
        plt.title("Hourly Attempts")
        plt.xlabel("Hour (0-23)")
        plt.ylabel("Attempts")
        plt.grid(True)
        plt.tight_layout()
        out_time = os.path.join(OUTPUT_DIR, "timeline.png")
        plt.savefig(out_time)
        plt.close()
        print(f"[+] Wrote {out_time}")
    except Exception as e:
        print("[!] Plotting failed:", e)
else:
    print("[*] matplotlib not installed; skipping plots.")

print("[+] Done. Check the '{}' directory.".format(OUTPUT_DIR))
