#!/usr/bin/env python3
import asyncio
import json
import urllib.request
import subprocess
import sys

import zendriver as zd

async def main():
    candidate_urls = ["http://localhost:9222/json/version"]
    try:
        host_ip = subprocess.check_output(["sh", "-lc", "ip route | awk '/default/ {print $3}' | head -n1"], text=True).strip()
        if host_ip:
            candidate_urls += [
                f"http://{host_ip}:9222/json/version",
                f"http://{host_ip}:9223/json/version",
            ]
    except Exception:
        host_ip = None

    last = None
    for version_url in candidate_urls:
        try:
            print('TRY_VERSION', version_url)
            data = json.loads(urllib.request.urlopen(version_url, timeout=5).read())
            ws_url = data['webSocketDebuggerUrl']
            print('WS_URL', ws_url)
            browser = await zd.start(browser_websocket_url=ws_url)
            print('ATTACHED_OK')
            pages = getattr(browser, 'tabs', None) or getattr(browser, 'targets', None)
            print('PAGES_OBJ', type(pages).__name__)
            await browser.stop()
            return 0
        except Exception as e:
            last = e
            print('ATTACH_FAIL', type(e).__name__, str(e))
    print('FINAL_FAIL', repr(last))
    return 1

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
