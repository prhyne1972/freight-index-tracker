#!/usr/bin/env python3
"""
Monthly updater for freight-index-tracker/index.html
Fetches BLS data via FRED mirrors, rebases to a 60-month rolling window,
and patches the EMBEDDED constant in index.html in-place.

Run:  python update_index.py
Deps: pip install requests
"""

import re
import json
import csv
import io
from datetime import date
import requests

# ── Series mapping ────────────────────────────────────────────────────────────
# artifact key (BLS ID)  →  FRED series ID
SERIES = {
    'WPUFD49207':           'WPUFD49207',
    'CUUR000SA0':           'CUUR000SA0',
    'PCU49211492110P':      'PCU492110492110',   # FRED uses different ID
    'PCU484122484122':      'PCU484122484122',
    'PCU484121484121':      'PCU484121484121',
    'PCU483111PCU483111':   'PCU483111483111',   # FRED uses different ID
    'PCU481112481112':      'PCU481112481112',
    'PCU482111482111':      'PCU482111482111',
}

FRED_CSV = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'
HEADERS  = {'User-Agent': 'freight-index-tracker-updater/1.0'}


def build_window() -> list[str]:
    """Return 60 YYYY-MM strings ending at last complete month."""
    today = date.today()
    # Last complete month
    if today.month == 1:
        ey, em = today.year - 1, 12
    else:
        ey, em = today.year, today.month - 1
    # Walk back 35 more months to get 36 total
    sy, sm = ey, em - 35
    while sm <= 0:
        sm += 12
        sy -= 1
    months = []
    y, m = sy, sm
    for _ in range(36):
        months.append(f'{y:04d}-{m:02d}')
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months


def fetch_fred(fred_id: str) -> dict[str, float]:
    """Return {YYYY-MM: float} for the given FRED series (drops missing '.')."""
    url = FRED_CSV.format(fred_id)
    print(f'  fetching {url}')
    r = requests.get(url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    data = {}
    reader = csv.DictReader(io.StringIO(r.text))
    for row in reader:
        ym = row['DATE'][:7]        # "2024-05-01" → "2024-05"
        v  = row['VALUE']
        if v and v != '.':
            data[ym] = float(v)
    return data


def rebase(raw: dict[str, float], window: list[str]) -> list[float | None]:
    """Rebase series to first available value in window; null for missing months."""
    base = None
    for ym in window:
        if ym in raw:
            base = raw[ym]
            break
    if base is None or base == 0:
        return [None] * len(window)
    return [
        round(raw[ym] / base, 6) if ym in raw else None
        for ym in window
    ]


def main():
    window = build_window()
    print(f'Window: {window[0]} → {window[-1]}  ({len(window)} months)')

    series_out: dict[str, list] = {}
    for bls_id, fred_id in SERIES.items():
        print(f'\n[{bls_id}]')
        try:
            raw = fetch_fred(fred_id)
        except Exception as e:
            print(f'  ERROR: {e}')
            series_out[bls_id] = [None] * len(window)
            continue
        vals = rebase(raw, window)
        non_null = [v for v in vals if v is not None]
        last = non_null[-1] if non_null else None
        print(f'  base=1.0  last={last}  non-null={len(non_null)}/{len(window)}')
        series_out[bls_id] = vals

    now_utc = date.today().strftime('%Y-%m-%dT12:00:00.000Z')
    embedded = {
        'updatedAt': now_utc,
        'dates':     window,
        'series':    series_out,
    }

    js      = json.dumps(embedded, separators=(',', ':'))
    new_line = f'const EMBEDDED = {js};'

    with open('index.html', 'r', encoding='utf-8') as f:
        html = f.read()

    html_new = re.sub(
        r'const EMBEDDED = .*?;',
        new_line,
        html,
        count=1,
        flags=re.DOTALL,
    )

    if html_new == html:
        print('\nWARNING: no replacement made — check that index.html contains "const EMBEDDED = ...;"')
    else:
        with open('index.html', 'w', encoding='utf-8') as f:
            f.write(html_new)
        print(f'\nindex.html updated  ({len(js)} chars of data embedded)')


if __name__ == '__main__':
    main()
