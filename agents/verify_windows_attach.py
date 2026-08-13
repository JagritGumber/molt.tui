#!/usr/bin/env python3
import asyncio
import sys

from x_browser import launch_browser

async def main():
    browser = await launch_browser(headless=False)
    try:
        print('ATTACHED')
        page = await browser.get('https://x.com/home')
        print('GOT_HOME', page)
        await asyncio.sleep(5)
        page2 = await browser.get('https://x.com/rauchg')
        print('GOT_RAUCHG', page2)
        await asyncio.sleep(10)
    finally:
        await browser.stop()

if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
