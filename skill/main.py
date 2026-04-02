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

TIMEOUT_S = int(os.environ.get("FASTAPI_SKILL_TIMEOUT", "15"))
FASTAPI_PORT = os.environ.get("FASTAPI_SKILL_PORT", "8000")


def _resolve_host_url() -> str:
    explicit = os.environ.get("FASTAPI_SKILL_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")

    try:
        socket.getaddrinfo("host.docker.internal", None, socket.AF_INET, socket.SOCK_STREAM)
        return f"http://host.docker.internal:{FASTAPI_PORT}"
    except socket.gaierror:
        pass

    bridge_gw = os.environ.get("FASTAPI_SKILL_HOST_IP", "172.17.0.1")
    try:
        s = socket.create_connection((bridge_gw, int(FASTAPI_PORT)), timeout=2)
        s.close()
        return f"http://{bridge_gw}:{FASTAPI_PORT}"
    except (OSError, ValueError):
        pass

    return f"http://127.0.0.1:{FASTAPI_PORT}"


FASTAPI_URL = _resolve_host_url()


def run(
    action: str = "health",
    method: str = "GET",
    path: str = "/",
    body: str | None = None,
) -> str:
    action = action.strip().lower()

    if action == "health":
        return _health(f"{FASTAPI_URL}/hi")
    elif action == "list_endpoints":
        return _list_endpoints()
    elif action == "call":
        return _call(method.upper(), path, body)
    else:
        return json.dumps({"error": f"Unknown action: {action}"})


def _health(url: str) -> str:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode())
            return json.dumps({"status": "ok", "base_url": FASTAPI_URL, "response": data})
    except (urllib.error.URLError, OSError) as exc:
        return json.dumps({"status": "unreachable", "base_url": FASTAPI_URL, "error": str(exc)})


def _list_endpoints() -> str:
    try:
        req = urllib.request.Request(f"{FASTAPI_URL}/openapi.json", method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            spec = json.loads(resp.read().decode())
        endpoints = []
        for p, methods in spec.get("paths", {}).items():
            for m, detail in methods.items():
                if m.upper() in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                    endpoints.append({"method": m.upper(), "path": p, "summary": detail.get("summary", "")})
        return json.dumps({"base_url": FASTAPI_URL, "endpoints": endpoints})
    except (urllib.error.URLError, OSError) as exc:
        return json.dumps({"error": str(exc)})


def _call(method: str, path: str, body: str | None) -> str:
    url = f"{FASTAPI_URL}{path}"
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    data_bytes = None
    if body and method in ("POST", "PUT", "PATCH"):
        data_bytes = body.encode()

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            parsed = json.loads(resp.read().decode())
            return json.dumps({"status_code": resp.status, "response": parsed})
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode()
        except Exception:
            pass
        return json.dumps({"status_code": exc.code, "error": exc.reason, "detail": detail})
    except (urllib.error.URLError, OSError) as exc:
        return json.dumps({"error": str(exc), "url": url})
