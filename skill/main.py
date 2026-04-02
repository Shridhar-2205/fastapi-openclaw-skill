"""OpenShell skill — calls a FastAPI app running on the host machine.

Runs inside an OpenShell sandbox container. Reaches the host via
host.docker.internal (Docker Desktop) or the Docker bridge gateway.

Usage (from inside the sandbox):
    python3 -c "from main import run; print(run(action='health'))"
    python3 -c "from main import run; print(run(action='list_endpoints'))"
    python3 -c "from main import run; print(run(action='call', method='GET', path='/hi'))"
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request

# --- Configuration (overridable via environment variables) ---
TIMEOUT_S = int(os.environ.get("FASTAPI_SKILL_TIMEOUT", "15"))  # HTTP request timeout in seconds
FASTAPI_PORT = os.environ.get("FASTAPI_SKILL_PORT", "8000")      # Port the FastAPI app listens on


def _resolve_host_url() -> str:
    """Determine the base URL of the FastAPI app on the host.

    Tries three strategies in order:
    1. Explicit FASTAPI_SKILL_URL env var (user override)
    2. host.docker.internal (Docker Desktop on macOS/Windows)
    3. Docker bridge gateway IP (Linux fallback)
    4. localhost (last resort)
    """
    # Strategy 1: explicit override — trust the user
    explicit = os.environ.get("FASTAPI_SKILL_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    # Strategy 2: Docker Desktop provides host.docker.internal
    # which resolves to the host's private IP (e.g. 192.168.65.254)
    try:
        socket.getaddrinfo("host.docker.internal", None, socket.AF_INET, socket.SOCK_STREAM)
        return f"http://host.docker.internal:{FASTAPI_PORT}"
    except socket.gaierror:
        pass  # hostname doesn't resolve — not on Docker Desktop

    # Strategy 3: on Linux, Docker bridge gateway is typically 172.17.0.1
    # Try a quick TCP connect to verify the host is reachable there
    bridge_gw = os.environ.get("FASTAPI_SKILL_HOST_IP", "172.17.0.1")
    try:
        s = socket.create_connection((bridge_gw, int(FASTAPI_PORT)), timeout=2)
        s.close()
        return f"http://{bridge_gw}:{FASTAPI_PORT}"
    except (OSError, ValueError):
        pass  # bridge gateway unreachable or port not open

    # Strategy 4: last resort — assumes app is on localhost (unlikely in sandbox)
    return f"http://127.0.0.1:{FASTAPI_PORT}"


# Resolve once at import time — cached for all subsequent run() calls
FASTAPI_URL = _resolve_host_url()


def run(
    action: str = "health",
    method: str = "GET",
    path: str = "/",
    body: str | None = None,
) -> str:
    """Main entry point — the OpenClaw agent (or user) calls this function.

    Args:
        action:  "health" | "list_endpoints" | "call"
        method:  HTTP method (GET, POST, etc.) — only used when action="call"
        path:    API path (e.g. "/hi") — only used when action="call"
        body:    JSON string for POST/PUT/PATCH body — only used when action="call"

    Returns:
        JSON string with the result (always parseable, never raises).
    """
    action = action.strip().lower()

    if action == "health":
        # Quick connectivity check — hits GET /hi on the FastAPI app
        return _health(f"{FASTAPI_URL}/hi")
    elif action == "list_endpoints":
        # Fetches /openapi.json and parses available routes
        return _list_endpoints()
    elif action == "call":
        # Generic HTTP call to any endpoint on the FastAPI app
        return _call(method.upper(), path, body)
    else:
        return json.dumps({"error": f"Unknown action: {action}"})


def _health(url: str) -> str:
    """Check if the FastAPI app is reachable. Returns status: ok or unreachable."""
    try:
        req = urllib.request.Request(url, method="GET")
        # urllib respects http_proxy env var — traffic goes through OpenShell proxy
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
            return json.dumps({"status": "ok", "base_url": FASTAPI_URL, "response": data})
    except (urllib.error.URLError, OSError) as exc:
        # Connection refused, proxy denied, timeout, etc.
        return json.dumps({"status": "unreachable", "base_url": FASTAPI_URL, "error": str(exc)})


def _list_endpoints() -> str:
    """Discover all available API endpoints via FastAPI's auto-generated OpenAPI spec."""
    try:
        # FastAPI automatically serves its OpenAPI schema at /openapi.json
        req = urllib.request.Request(f"{FASTAPI_URL}/openapi.json", method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            spec = json.loads(resp.read().decode())
        # Parse the OpenAPI paths into a flat list of {method, path, summary}
        endpoints = []
        for p, methods in spec.get("paths", {}).items():
            for m, detail in methods.items():
                if m.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    endpoints.append({"method": m.upper(), "path": p, "summary": detail.get("summary", "")})
        return json.dumps({"base_url": FASTAPI_URL, "endpoints": endpoints})
    except (urllib.error.URLError, OSError) as exc:
        return json.dumps({"error": str(exc)})


def _call(method: str, path: str, body: str | None) -> str:
    """Make an arbitrary HTTP request to the FastAPI app.

    Handles three outcomes:
    - 2xx success  → {status_code, response}
    - HTTP error   → {status_code, error, detail}
    - Network error → {error, url}
    """
    url = f"{FASTAPI_URL}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}

    # Only encode body for methods that support a request body
    data_bytes = None
    if body and method in ("POST", "PUT", "PATCH"):
        data_bytes = body.encode()

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            parsed = json.loads(resp.read().decode())
            return json.dumps({"status_code": resp.status, "response": parsed})
    except urllib.error.HTTPError as exc:
        # Server returned 4xx/5xx — capture the error body for debugging
        detail = ""
        try:
            detail = exc.read().decode()
        except Exception:
            pass
        return json.dumps({"status_code": exc.code, "error": exc.reason, "detail": detail})
    except (urllib.error.URLError, OSError) as exc:
        # Network-level failure: proxy denied, connection refused, DNS error, timeout
        return json.dumps({"error": str(exc), "url": url})
