#!/usr/bin/env python3
"""Fetch John Collison's writing into originals/html.

The live domain is defunct (parked), so every page is read from the Wayback Machine.
Sources:
  * http://johncollison.ie/blog/  - WordPress blog (2007-2008). Its two index
    pages carry the full text of all twenty posts, so each post fragment is
    saved directly from the archive.
  * https://blog.johncollison.ie/ - Svbtle blog (2012), two posts.

Requires bs4 and curl. Writes originals/html/<slug>.html and originals/pages.json.
"""
import json
import subprocess
import time
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
DEST = ROOT / 'originals' / 'html'
DEST.mkdir(parents=True, exist_ok=True)

WAYBACK = 'https://web.archive.org/web/{ts}id_/{url}'
OLD_BLOG = 'http://johncollison.ie/blog/'
OLD_TS = '20100123101519'
SVBTLE = [
    ('aircraft-engines', 'https://blog.johncollison.ie/aircraft-engines', '20210512083834'),
    ('permanent-world-encyclopaedia', 'https://blog.johncollison.ie/permanent-world-encyclopaedia', '20210620131045'),
]


def fetch(url, timestamp):
    """Download url from the Wayback Machine, retrying transient failures."""
    last = ''
    for ts in (timestamp, timestamp[:4], '2'):
        target = WAYBACK.format(ts=ts, url=url)
        for attempt in range(4):
            result = subprocess.run(
                ['curl', '-fLsS', '--max-time', '60', target], capture_output=True)
            if result.returncode == 0 and result.stdout:
                return result.stdout
            last = result.stderr.decode().strip()
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f'Could not fetch {url}: {last}')


pages = []
for page in (1, 2):
    url = OLD_BLOG if page == 1 else f'{OLD_BLOG}page/{page}/'
    body = fetch(url, OLD_TS)
    soup = BeautifulSoup(body, 'html5lib')
    for post in soup.select('div.post'):
        link = post.select_one('h2 a[rel=bookmark]')
        if link is None:
            continue
        permalink = link['href']
        slug = permalink.rstrip('/').split('/')[-1]
        (DEST / (slug + '.html')).write_text(str(post))
        pages.append(dict(slug=slug, url=permalink, kind='wordpress'))
        print('wordpress', slug, flush=True)

for slug, url, ts in SVBTLE:
    (DEST / (slug + '.html')).write_bytes(fetch(url, ts))
    pages.append(dict(slug=slug, url=url, kind='svbtle'))
    print('svbtle', slug, flush=True)

pages.sort(key=lambda p: p['url'])
(ROOT / 'originals' / 'pages.json').write_text(json.dumps(pages, indent=2) + '\n')
print(f'Fetched {len(pages)} pages.')
