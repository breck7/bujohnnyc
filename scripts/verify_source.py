#!/usr/bin/env python3
"""Check rendered source words and original reference links after conversion.

Requires bs4 and html5lib. Run after npm run build. Compares each saved source
page with its generated HTML. Extra output words (image placeholders, missing
image notes) are allowed; missing source words or source links are errors.
"""
import collections
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
PAGES = {page['slug']: page for page in json.loads((ROOT / 'originals' / 'pages.json').read_text())}
errors = []

for post in json.loads((ROOT / 'archive.json').read_text()):
    slug = post['slug']
    page = PAGES[slug]
    source_soup = BeautifulSoup((ROOT / 'originals' / 'html' / (slug + '.html')).read_text(), 'html5lib')
    if page['kind'] == 'wordpress':
        source = source_soup.select_one('div.entry')
    else:
        source = source_soup.select_one('article.post')
        for node in source.select('figure, time, h1, script, .head_anchor'):
            node.decompose()
    output = BeautifulSoup((ROOT / (slug + '.html')).read_text(), 'html5lib').select_one('#main')
    for tree in (source, output):
        for br in tree.select('br'):
            br.replace_with(' ')
        for block in tree.select('p,li,h1,h2,h3,h4,div,blockquote'):
            block.insert_before(' ')
            block.insert_after(' ')

    def words(node):
        return collections.Counter(w for w in re.findall(r'\w+', node.get_text().lower()) if not w.isdigit())

    missing = words(source) - words(output)
    if missing:
        errors.append(f'{slug}: missing source words {dict(missing)}')
    links = {a['href'] for a in output.select('a[href]')}
    for a in source.select('a[href]'):
        url = urljoin(post['url'], a['href'])
        if a.get_text(strip=True) and url not in links and not url.startswith(post['url'] + '#'):
            errors.append(f'{slug}: missing source link {url}')

if errors:
    raise SystemExit('\n'.join(errors))
print(f'{len(PAGES)} pages preserve source words and reference links.')
