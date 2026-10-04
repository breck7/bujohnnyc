#!/usr/bin/env python3
"""Convert saved source HTML to native Scroll bodies and build archive.json.

Inputs (from fetch_source.py) are originals/html/<slug>.html:
  * WordPress fragments: a single div.post holding h2, a date, and div.entry.
  * Svbtle full pages: an article.post holding the article body.

Requires bs4 and html5lib. Article images keep their source URLs here;
run fetch_images.py afterwards to localize them.
"""
import html
import json
import re
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment, NavigableString

ROOT = Path(__file__).resolve().parent.parent
PAGES = json.loads((ROOT / 'originals' / 'pages.json').read_text())


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def esc(text):
    return html.escape(text, quote=False)


def style_of(tag):
    if tag.name in ('b', 'strong'):
        return 'bold'
    if tag.name in ('i', 'em'):
        return 'italics'
    if tag.name == 'span':
        style = (tag.get('style') or '').replace(' ', '').lower()
        if 'font-weight:bold' in style:
            return 'bold'
        if 'font-style:italic' in style:
            return 'italics'
    return None


def inline_lines(node, url, prefix=''):
    """One paragraph/list item as a Scroll line plus its aftertext decorations."""
    text = clean(node.get_text())
    if not text:
        return []
    lines = [prefix + esc(text), ' linkify false']
    for tag in node.find_all(['a', 'b', 'strong', 'i', 'em', 'span']):
        label = clean(tag.get_text())
        if not label:
            continue
        if tag.name == 'a' and tag.get('href'):
            href = html.escape(urljoin(url, tag['href']), quote=True)
            lines.append(' link ' + href + ' ' + esc(label))
            continue
        kind = style_of(tag)
        if kind and not tag.find('a') and not tag.find_parent('a'):
            lines.append(' ' + kind + ' ' + esc(label))
    return lines


def image_lines(img, url):
    if 'wp-smiley' in (img.get('class') or []):
        return [esc(img.get('alt') or '')]
    lines = ['image ' + urljoin(url, img['src'])]
    alt = clean(img.get('alt') or '')
    filename = re.fullmatch(r'\S+\.(?:jpe?g|png|gif|webp|svg)', alt, re.I)
    if alt and not filename and not re.fullmatch(r'[:;][^\w]*', alt):
        lines.append(' caption ' + esc(alt))
    return lines


def audio_link(node):
    match = re.search(r'external_url=([^&"\s]+)', str(node))
    if not match:
        return None
    label = 'Listen to the interview (MP3).'
    return esc(label) + '\n ' + html.escape(html.unescape(match.group(1)), quote=True) + ' ' + esc(label)


def paragraph_blocks(node, url):
    """Split a paragraph-like node at images, breaks, and embedded audio."""
    blocks = []
    segment = []

    def flush():
        if not segment:
            return
        wrapper = BeautifulSoup('<div></div>', 'html5lib').div
        for part in segment:
            wrapper.append(part)
        lines = inline_lines(wrapper, url)
        if lines:
            blocks.append('\n'.join(lines))
        segment.clear()

    for child in list(node.children):
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            segment.append(NavigableString(str(child)))
            continue
        if child.name == 'img':
            flush()
            blocks.extend(image_lines(child, url))
        elif child.name == 'br':
            flush()
        elif child.name in ('object', 'embed'):
            flush()
            link = audio_link(child)
            if link:
                blocks.append(link)
        else:
            segment.append(child)
    flush()
    return blocks


def convert(node, url, depth=0):
    blocks = []
    for child in node.children:
        if isinstance(child, Comment):
            continue
        if isinstance(child, NavigableString):
            text = clean(str(child))
            if text:
                blocks.append(esc(text) + '\n linkify false')
            continue
        tag = child.name
        if tag in ('script', 'style', 'form', 'time', 'h1'):
            continue
        if tag in ('ul', 'ol'):
            items = []
            for item in child.find_all('li', recursive=False):
                lines = inline_lines(item, url, '- ')
                if lines:
                    items.append('\n'.join(lines))
            if items:
                blocks.append('\n'.join(items))
        elif tag == 'img':
            blocks.extend(image_lines(child, url))
        elif tag == 'blockquote':
            text = clean(child.get_text())
            image = child.find('img')
            if image is not None and not text:
                blocks.extend(image_lines(image, url))
            elif text:
                blocks.append('quote\n ' + esc(text))
        elif tag in ('object', 'embed'):
            link = audio_link(child)
            if link:
                blocks.append(link)
        elif tag in ('div', 'section', 'article'):
            blocks.extend(convert(child, url, depth))
        elif tag == 'br':
            continue
        elif re.fullmatch(r'h[2-6]', tag):
            lines = inline_lines(child, url, '#' * max(2, int(tag[1])) + ' ')
            if lines:
                blocks.append('\n'.join(lines))
        else:
            blocks.extend(paragraph_blocks(child, url))
    return blocks


def article_from(page):
    soup = BeautifulSoup((ROOT / 'originals' / 'html' / (page['slug'] + '.html')).read_text(), 'html5lib')
    for img in soup.select('img.wp-smiley'):
        img.replace_with(NavigableString(img.get('alt') or ''))
    if page['kind'] == 'wordpress':
        match = re.search(r'/(\d{4})/(\d{2})/(\d{2})/', page['url'])
        date = '-'.join(match.groups())
        title = clean(soup.select_one('div.post > h2').get_text())
        container = soup.select_one('div.entry')
    else:
        date = soup.select_one('time[datetime]')['datetime']
        heading = soup.select_one('h1.article_title')
        title = clean(heading.find('a').get_text()) if heading.find('a') else clean(heading.get_text())
        container = soup.select_one('article.post')
        for node in container.select('figure, time, h1, script, .head_anchor'):
            node.decompose()
    body = re.sub(r'\n\n(?= )', '\n', '\n\n'.join(convert(container, page['url'])))
    return dict(slug=page['slug'], title=title, date=date, url=page['url']), body


posts = []
for page in PAGES:
    meta, body = article_from(page)
    (ROOT / 'originals' / (meta['slug'] + '.scroll')).write_text(body.strip() + '\n')
    posts.append(meta)

posts.sort(key=lambda post: (post['date'], post['slug']))
(ROOT / 'archive.json').write_text(json.dumps(posts, indent=2, ensure_ascii=False) + '\n')
print(f'Converted {len(posts)} articles.')
