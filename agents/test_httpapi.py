#!/usr/bin/env python3
import asyncio
from zendriver.core.browser import HTTPApi

async def main():
    api = HTTPApi(('172.22.80.1', 9223))
    try:
        data = await api.get('version')
        print('OK', data)
    except Exception as e:
        print('FAIL', type(e).__name__, repr(e))

if __name__ == '__main__':
    asyncio.run(main())
