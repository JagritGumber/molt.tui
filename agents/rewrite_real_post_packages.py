#!/usr/bin/env python3
import json
from pathlib import Path
from x_browser import get_zai_config

INP = Path.home()/'.moltui'/'x-real-post-packages.json'
OUT = Path.home()/'.moltui'/'x-real-post-packages-rewritten.json'


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

packages = json.loads(INP.read_text()).get('packages', [])
prompt = f"""Rewrite these real-media X post packages for @wyvernotwts.

Rules:
- keep the same real media_url and source_url
- rewrite the text to sound more native to X
- no em dashes
- no hashtags
- no emojis
- no fake first-person claims
- no devrel/blog-summary tone
- no 'this blog post breaks down'
- no 'this template lets'
- no Vercel-marketing voice
- sharper, more builder-native, more taste
- easier to parse in one scroll
- text should work WITH the media, not describe it blandly
- user has AI + low-level + systems + gamedev creator energy

Return strict JSON:
{{
  "packages": [
    {{
      "text": "...",
      "source_title": "...",
      "source_url": "...",
      "media_url": "...",
      "media_type": "image",
      "why_better": "...",
      "postable_score": 0-10
    }}
  ]
}}

Current packages:
{json.dumps(packages, indent=2)}
"""

out = llm_json(prompt) or {'packages': []}
OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False))
print(json.dumps(out, indent=2, ensure_ascii=False))
