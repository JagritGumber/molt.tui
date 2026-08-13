#!/usr/bin/env python3
import json
from pathlib import Path
from x_browser import get_zai_config

HOME = Path.home()/'.moltui'
OUT = HOME/'x-real-post-packages.json'

SOURCES = [
  {
    'title': 'Build knowledge agents without embeddings',
    'url': 'https://vercel.com/blog/build-knowledge-agents-without-embeddings',
    'media_url': 'https://assets.vercel.com/image/upload/contentful/image/e5382hct74si/5ufspQFdShGTwPNUYbdnjX/0dd201598fbc4d38a7cb3a2fd8ad8419/og.png',
    'description': 'Open source file-system and knowledge based agent template. Build AI agents that stay up to date with your knowledge base. Grep, find, and cat across your sources, no embeddings, no vector DB.'
  },
  {
    'title': 'Chat SDK brings agents to your users',
    'url': 'https://vercel.com/blog/chat-sdk-brings-agents-to-your-users',
    'media_url': 'https://assets.vercel.com/image/upload/contentful/image/e5382hct74si/2X1etrEAFzqdP5zOlLJKdU/33aa1150c52d9aaa6e22bfb17b5fd74c/image.png',
    'description': 'Unified TypeScript library for building chat bots across platforms from one codebase.'
  },
  {
    'title': 'Two startups at global scale without DevOps',
    'url': 'https://vercel.com/blog/two-startups-at-global-scale-without-devops',
    'media_url': 'https://assets.vercel.com/image/upload/contentful/image/e5382hct74si/2nwBHcJ0dfqYUzhyVvvPhj/398f481d27196a2299df752d303b0d14/image__1_.png',
    'description': 'How very small teams scaled to millions of users without a traditional platform team.'
  },
]

def llm_json(prompt: str, max_tokens: int = 2200, temperature: float = 0.9):
    zai = get_zai_config()
    if not zai:
        return None
    key, model = zai
    try:
        import urllib.request
        req = urllib.request.Request(
            'https://api.z.ai/api/paas/v4/chat/completions',
            data=json.dumps({
                'model': model,
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': max_tokens,
                'temperature': temperature,
                'stream': False,
                'thinking': {'type': 'disabled'},
                'response_format': {'type': 'json_object'},
            }).encode(),
            headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'},
        )
        resp = urllib.request.urlopen(req, timeout=35)
        data = json.loads(resp.read())
        text = (data['choices'][0]['message']['content'] or '').strip()
        return json.loads(text)
    except Exception:
        return None

prompt = f"""Build 5 actual X post packages for @wyvernotwts using ONLY the real media sources below.

Rules:
- every package must reference one of the provided real media URLs
- no concept-only media
- no fake first-person claims
- no em dashes
- no hashtags
- no emojis
- no 'Show HN'
- no AI-sludge phrasing like 'the next wave is' or 'the real opportunity is'
- creator-centered and X-native
- if text is weak, package is weak even with media
- prefer posts that feel visual-first and easy to understand immediately
- user is broader than AI: also low-level, systems, and gamedev-minded

Return strict JSON:
{{
  "packages": [
    {{
      "text": "...",
      "source_title": "...",
      "source_url": "...",
      "media_url": "...",
      "media_type": "image",
      "text_only_score": 0-10,
      "package_score": 0-10,
      "why_it_might_work": "...",
      "why_it_might_fail": "..."
    }}
  ]
}}

Real sources:
{json.dumps(SOURCES, indent=2)}
"""

data = llm_json(prompt) or {'packages': []}
OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False))
print(json.dumps(data, indent=2, ensure_ascii=False))
