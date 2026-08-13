#!/usr/bin/env python3
import asyncio
import zendriver as zd

async def main():
    try:
        browser = await zd.start(host='172.22.80.1', port=9223)
        print('START_OK', browser)
        await browser.stop()
    except Exception as e:
        import traceback
        print('START_FAIL', type(e).__name__, repr(e))
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(main())
