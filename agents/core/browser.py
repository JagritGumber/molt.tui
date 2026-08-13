"""Browser Manager — zendriver CDP connection to Windows Chrome/Opera."""

import json
import subprocess
import urllib.parse
import urllib.request

import zendriver as zd


def _get_wsl_gateway_ip() -> str | None:
    """Get the WSL2 gateway IP (Windows host) for cross-VM CDP."""
    try:
        return subprocess.check_output(
            ["sh", "-lc", "ip route | awk '/default/ {print $3}' | head -n1"],
            text=True,
        ).strip() or None
    except Exception:
        return None


def _probe_cdp(url: str, timeout: int = 5) -> dict | None:
    """Probe a CDP /json/version endpoint. Returns version data or None."""
    try:
        resp = urllib.request.urlopen(url, timeout=timeout)
        return json.loads(resp.read())
    except Exception:
        return None


class BrowserManager:
    def __init__(self, cdp_port: int = 9222, cdp_host: str = "localhost"):
        self.cdp_port = cdp_port
        self.cdp_host = cdp_host
        self.browser = None
        self._page = None

    async def connect(self):
        """Connect to an existing Chrome/Opera instance via CDP.

        Tries multiple endpoints in order:
          1. localhost:{port}  (direct, works if port-forwarded)
          2. {gateway_ip}:{port}  (WSL2 -> Windows host)
          3. {gateway_ip}:{port+1}  (fallback alt port)
        """
        candidates = [
            (self.cdp_host, self.cdp_port),
        ]

        # In WSL2, also try the gateway IP
        gateway = _get_wsl_gateway_ip()
        if gateway and gateway != self.cdp_host:
            candidates.append((gateway, self.cdp_port))
            candidates.append((gateway, self.cdp_port + 1))

        last_error = None
        for host, port in candidates:
            version_url = f"http://{host}:{port}/json/version"
            print(f"  CDP: trying {host}:{port}...")
            data = _probe_cdp(version_url)
            if data:
                try:
                    self.browser = await zd.start(host=host, port=port)
                    self.cdp_host = host
                    self.cdp_port = port
                    browser_name = data.get("Browser", "Chrome")
                    print(f"  CDP: connected to {browser_name} via {host}:{port}")
                    return self.browser
                except Exception as e:
                    last_error = e
                    continue
            else:
                last_error = Exception(f"No response from {version_url}")

        msg = f"Could not connect to browser CDP on any endpoint. Last error: {last_error}"
        raise ConnectionError(msg)

    async def new_page(self):
        """Get a page from the browser."""
        if not self.browser:
            await self.connect()
        self._page = await self.browser.get("about:blank")
        return self._page

    async def close(self):
        """Close the browser connection."""
        if self.browser:
            try:
                await self.browser.stop()
            except Exception:
                pass
            self.browser = None
            self._page = None
