#!/usr/bin/env python3
"""Localize article images; run after convert_source.py.

The source domain is defunct, so images are read from the Wayback Machine.
Because the WordPress uploads were not preserved by the archive, every image
currently resolves to a 404. Successful images are rewritten to local assets/;
unavailable ones become a visible placeholder so nothing is silently dropped.
Records successes and failures in originals/images.json.
"""
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / 'assets'
ASSETS.mkdir(exist_ok=True)
IMAGE = re.compile(r'^image (https?://\S+)$')
CAPTION = re.compile(r'^ caption (.*)$')


def download(url):
    for ts in ('20100123101519', '2'):
        target = f'https://web.archive.org/web/{ts}id_/{url}'
        result = subprocess.run(
            ['curl', '-fLsS', '--connect-timeout', '8', '--max-time', '25', target],
            capture_output=True)
        if result.returncode == 0 and result.stdout:
            return result.stdout
        time.sleep(1)
    return None


saved, missing = {}, []
for path in sorted((ROOT / 'originals').glob('*.scroll')):
    lines = path.read_text().split('\n')
    output = []
    index = 0
    while index < len(lines):
        match = IMAGE.match(lines[index])
        if not match:
            output.append(lines[index])
            index += 1
            continue
        url = match.group(1)
        caption = ''
        if index + 1 < len(lines) and CAPTION.match(lines[index + 1]):
            caption = CAPTION.match(lines[index + 1]).group(1).strip()
        if url not in saved and url not in missing:
            suffix = Path(urlsplit(url).path).suffix or '.jpg'
            asset = 'assets/' + hashlib.sha256(url.encode()).hexdigest()[:16] + suffix
            target = ROOT / asset
            if target.exists():
                saved[url] = asset
            else:
                body = download(url)
                if body is None:
                    missing.append(url)
                    print('MISSING', url, flush=True)
                else:
                    target.write_bytes(body)
                    saved[url] = asset
        if url in saved:
            output.append('image ' + saved[url])
            if caption:
                output.append(' caption ' + caption)
        else:
            note = f'[Image not archived: {caption}]' if caption else '[Image not archived]'
            output.append(note)
        index += 2 if caption else 1
    path.write_text('\n'.join(output))

(ROOT / 'originals' / 'images.json').write_text(
    json.dumps(dict(saved=saved, missing=missing), indent=2) + '\n')
print(f'Saved {len(saved)} local images; {len(missing)} unavailable.')
