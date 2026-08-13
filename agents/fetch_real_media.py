#!/usr/bin/env python3
import json
import re
import urllib.request
from html.parser import HTMLParser

URLS = [
    'https://georgelarson.me/writing/2026-03-23-nullclaw-doorman/',
    'https://vercel.com/blog/build-knowledge-agents-without-embeddings',
    'https://vercel.com/blog/chat-sdk-brings-agents-to-your-users',
    'https://vercel.com/blog/two-startups-at-global-scale-without-devops',
]

class ImgParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.imgs = []
        self.meta = {}
        self.title = ''
        self._in_title = False
    def handle_starttag(self, tag, attrs):
        d = dict(attrs)
        if tag == 'img':
            src = d.get('src') or d.get('data-src') or d.get('srcset')
            if src:
                self.imgs.append(src)
        if tag == 'meta':
            k = d.get('property') or d.get('name')
            v = d.get('content')
            if k and v:
                self.meta[k] = v
        if tag == 'title':
            self._in_title = True
    def handle_endtag(self, tag):
        if tag == 'title':
            self._in_title = False
    def handle_data(self, data):
        if self._in_title:
            self.title += data

out = []
for url in URLS:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=25) as r:
            html = r.read().decode('utf-8', errors='replace')
        p = ImgParser()
        p.feed(html)
        imgs = []
        for src in p.imgs:
            if src.startswith('//'):
                src = 'https:' + src
            elif src.startswith('/'):
                m = re.match(r'https?://[^/]+', url)
                if m:
                    src = m.group(0) + src
            imgs.append(src)
        out.append({
            'url': url,
            'title': p.title.strip(),
            'og_image': p.meta.get('og:image') or p.meta.get('twitter:image'),
            'description': p.meta.get('og:description') or p.meta.get('description') or p.meta.get('twitter:description'),
            'images': imgs[:20],
        })
    except Exception as e:
        out.append({'url': url, 'error': str(e)})
print(json.dumps(out, indent=2, ensure_ascii=False))
