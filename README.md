# FastAPI Skill in OpenShell Sandbox

> **EXPERIMENTAL** — This example is a work-in-progress and may not be
> perfect. It has been tested **only with direct `python3` / `curl`
> invocation** (no LLM). The OpenClaw agent + LLM path (gateway →
> bash tool → skill) has **NOT been tested**. If you configure an LLM
> provider via `openclaw onboard`, behavior may differ from what is
> documented here. Use at your own risk and expect rough edges.

## What This Example Does

This example demonstrates how an [OpenClaw](https://github.com/openclaw/openclaw)
agent skill running inside an [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell)
sandbox can securely call a **FastAPI application hosted on your machine**.

- **`app.py`** is a simple FastAPI server that runs on the **host machine**
  (outside Docker) and exposes REST endpoints (`/hi`, `/hello/{name}`,
  `/foo`, `/bar`).
- **`skill/main.py`** is a Python skill that lives **inside the OpenShell
  sandbox** (a locked-down Docker container). It provides a `run()` function
  that makes HTTP requests to the FastAPI app.
- The skill reaches the host through Docker's **`host.docker.internal`**
  hostname, which resolves to the host's private IP (`192.168.65.254` on
  Docker Desktop).

## How the Connection Works

OpenShell sandboxes block **all outbound network traffic by default**. To
allow the skill to talk to the host:

1. A **network policy** (`openshell-policy.yaml`) is applied that permits
   TCP connections to `host.docker.internal:8000`.
2. The policy includes **`allowed_ips`** to whitelist the private IP range
   that `host.docker.internal` resolves to — without this, OpenShell's
   built-in SSRF protection blocks connections to RFC 1918 addresses.
3. All traffic flows through the OpenShell **forward proxy**
   (`10.200.0.1:3128`) which enforces the policy at the network level.

No LLM is required — you test the skill directly with `python3` and `curl`
from inside the sandbox.

```
 HOST MACHINE (macOS / Linux)            OPENSHELL SANDBOX (Docker container: openshell-cluster-openshell)
┌─────────────────────────────┐         ┌───────────────────────────────────────────────────────────────────┐
│                             │         │                                                                   │
│                             │         │   OpenClaw Agent (with LLM)          Direct (no LLM)              │
│                             │         │   ┌─────────────────────┐           ┌──────────────────┐         │
│                             │         │   │  openclaw gateway    │           │  sandbox shell    │         │
│                             │         │   │  ws://127.0.0.1:18789│           │  (ssh session)    │         │
│                             │         │   │                     │           │                  │         │
│                             │         │   │  Agent receives     │           │  python3 -c      │         │
│                             │         │   │  user prompt  ───►  │           │  "from main      │         │
│                             │         │   │  LLM decides to     │           │   import run;    │         │
│                             │         │   │  use bash tool ───► │           │   print(run(..)) │         │
│                             │         │   └────────┬────────────┘           └────────┬─────────┘         │
│                             │         │            │ bash: python3 main.py           │                    │
│                             │         │            └──────────┬──────────────────────┘                    │
│                             │         │                       ▼                                           │
│   FastAPI App               │         │   /sandbox/.agents/skills/fastapi-skill/                          │
│   ┌───────────────────┐    │         │   ┌───────────────────────┐                                      │
│   │  app.py            │    │         │   │  main.py               │                                      │
│   │                    │    │         │   │                        │                                      │
│   │  GET  /hi          │    │  HTTP   │   │  run(action=...)       │                                      │
│   │  GET  /hello/{name}│◄───┼─────────┼───│    _call_endpoint()    │                                      │
│   │  GET  /foo         │    │         │   │    _health_check()     │                                      │
│   │  POST /bar         │    │         │   │    _list_endpoints()   │                                      │
│   │                    │    │         │   └───────────┬────────────┘                                      │
│   │  uvicorn           │    │         │               │                                                   │
│   │  0.0.0.0:8000      │    │         │               │ HTTP via http_proxy env var                       │
│   └───────────────────┘    │         │               ▼                                                   │
│            ▲                │         │   ┌────────────────────────────┐                                   │
│            │                │         │   │  OpenShell Forward Proxy   │                                   │
│            │                │         │   │  10.200.0.1:3128           │                                   │
│            │                │         │   │                            │                                   │
│            │                │         │   │  1. Match endpoint policy  │                                   │
│            │                │         │   │  2. Check allowed_ips      │                                   │
│            │                │         │   │  3. Verify binary path     │                                   │
│            │                │         │   │  4. FORWARD to destination │                                   │
│            │                │         │   └────────────┬───────────────┘                                   │
│            │                │         │                │                                                   │
│            │                │         │   ┌────────────▼───────────────┐                                   │
│            │                │         │   │  DNS: host.docker.internal │                                   │
│            │                │         │   │   → 192.168.65.254         │                                   │
│            │                │         │   │  (Docker Desktop host IP)  │                                   │
│            │                │         │   └────────────┬───────────────┘                                   │
│            │                │         └────────────────┼───────────────────────────────────────────────────┘
│            │                │                          │
│            │  192.168.65.254:8000                      │
│            └──────────────────────────────────────────┘
│                             │
└─────────────────────────────┘

 POLICY ENFORCEMENT (openshell-policy.yaml)
┌──────────────────────────────────────────────────────────┐
│  network_policies:                                       │
│    host_fastapi:                                         │
│      endpoints:                                          │
│        - host: host.docker.internal                      │
│          port: 8000                                      │
│          tls: skip              ← plain HTTP, no TLS     │
│          allowed_ips:                                    │
│            - "192.168.65.0/24"  ← bypasses SSRF block    │
│      binaries:                                           │
│        - { path: /** }          ← any executable allowed │
└──────────────────────────────────────────────────────────┘
```

> **Docs:** [docs.nvidia.com/openshell/latest](https://docs.nvidia.com/openshell/latest/)
> — [Policy Schema](https://docs.nvidia.com/openshell/latest/reference/policy-schema.html)
> — [First Network Policy tutorial](https://docs.nvidia.com/openshell/latest/tutorials/first-network-policy.html)
> — [Private IP Routing](https://github.com/NVIDIA/OpenShell/tree/main/examples/private-ip-routing)

## Project Structure

```
fastapi-openclaw-skill/
├── app.py                  # FastAPI app (runs on HOST)
├── requirements.txt        # pip deps for the host app
├── openshell-policy.yaml   # Network policy — sandbox → host:8000
├── README.md
└── skill/                  # Copy into the sandbox
    ├── skill.yaml
    ├── SKILL.md
    └── main.py             # run() function the agent/user calls
```

---

## Step 1 — Install OpenShell

> **Prerequisite:** Docker Desktop (or a Docker daemon) must be running.

```bash
# Binary install (recommended)
curl -LsSf https://raw.githubusercontent.com/NVIDIA/OpenShell/main/install.sh | sh

# Or via PyPI (requires uv)
uv tool install -U openshell
```

Verify:

```bash
openshell --help
```

---

## Step 2 — Create an OpenClaw Sandbox

Create a sandbox from the [OpenClaw community image](https://github.com/NVIDIA/OpenShell-Community/tree/main/sandboxes/openclaw).
We use `--keep` (stays running after you exit) and `--forward 18789` to
expose the OpenClaw UI on the host.

```bash
openshell sandbox create --name fastapi-demo --keep --from openclaw --forward 18789 -- openclaw-start
```

This:
- Pulls the OpenClaw sandbox image (includes OpenClaw CLI + gateway + Node.js)
- Runs `openclaw-start` which calls `openclaw onboard` and starts the gateway
- Forwards the OpenClaw UI to `http://127.0.0.1:18789/` on the host
- Auto-bootstraps a local OpenShell gateway on first use

You land in an interactive shell:

```
sandbox@fastapi-demo:/sandbox$
```

The sandbox home directory is `/sandbox/`. Type `exit` to return to the
host — the sandbox keeps running.

Useful commands:

```bash
openshell sandbox list                         # list sandboxes
openshell sandbox connect fastapi-demo         # reconnect
openshell logs fastapi-demo --since 5m         # view recent logs
openshell status                               # gateway health
```

> **Note:** The sandbox user's home is `/sandbox/`, not `/home/sandbox/`.
> Skills are discovered from `/sandbox/.agents/skills/`.

---

## Step 3 — Start the FastAPI App on the Host

In a **separate terminal on the host**:

```bash
cd examples/fastapi-openclaw-skill
pip install -r requirements.txt
python app.py
```

Verify from the host:

```bash
curl http://localhost:8000/hi
# {"message":"hi there!"}

curl http://localhost:8000/hello/world
# {"message":"hello world!"}

curl http://localhost:8000/foo
# {"foo":"bar"}

curl -X POST http://localhost:8000/bar \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
# {"you_sent":{"key":"value"},"status":"ok"}
```

> **Important:** `app.py` binds to `0.0.0.0` so the sandbox container can
> reach it via `host.docker.internal`. Binding to `127.0.0.1` would make it
> invisible to the container.

---

## Step 4 — Apply the Network Policy

OpenShell sandboxes start with **default-deny networking** — all outbound
connections are blocked. We need a policy that allows the sandbox to reach
`host.docker.internal:8000`.

The included `openshell-policy.yaml` does exactly this. Apply it:

```bash
openshell policy set fastapi-demo --policy openshell-policy.yaml --wait
```

- `--wait` blocks until the sandbox confirms the policy is loaded.
- **Hot-reloads** — no sandbox restart needed.
- `policy set` **replaces the entire policy**, which is why the file
  includes `filesystem_policy`, `landlock`, and `process` sections too.

Key policy details:
- **`allowed_ips: ["192.168.65.0/24"]`** — required because
  `host.docker.internal` resolves to a private IP (`192.168.65.254` on
  Docker Desktop). The proxy blocks RFC 1918 IPs by default as SSRF
  protection. See [private-ip-routing example](https://github.com/NVIDIA/OpenShell/tree/main/examples/private-ip-routing).
- **`tls: skip`** — disables TLS auto-detection for plain HTTP.
- **No `protocol: rest`** — L7 HTTP inspection requires CONNECT tunneling,
  but the sandbox `http_proxy` uses FORWARD mode. Omitting `protocol` uses
  TCP passthrough which is compatible.

Verify the policy is active:

```bash
openshell policy get fastapi-demo
```

You should see the `host_fastapi` network policy with
`host: host.docker.internal`, `port: 8000`, `allowed_ips: 192.168.65.0/24`.

---

## Step 5 — Verify Connectivity from the Sandbox

```bash
openshell sandbox connect fastapi-demo
```

Inside the sandbox:

```bash
curl -s http://host.docker.internal:8000/hi
# {"message":"hi there!"}

curl -s http://host.docker.internal:8000/foo
# {"foo":"bar"}

curl -s -X POST http://host.docker.internal:8000/bar \
  -H "Content-Type: application/json" \
  -d '{"hello": "from sandbox"}'
# {"you_sent":{"hello":"from sandbox"},"status":"ok"}
```

If you get a `403` or `policy_denied` response, check the deny log from
the host (see Troubleshooting below):

```bash
openshell logs fastapi-demo --level warn --since 5m
```

Type `exit` to return to the host.

---

## Step 6 — Copy the Skill into the Sandbox

Skills are discovered from `/sandbox/.agents/skills/` inside the container
([base sandbox layout](https://github.com/NVIDIA/OpenShell-Community/tree/main/sandboxes/base)).

The skill directory doesn't exist by default — create it first, then copy.

```bash
# The sandbox runs inside the openshell-cluster-openshell container
CID=$(docker ps --filter name=openshell-cluster-openshell --format '{{.ID}}')

# Create the skills directory (doesn't exist by default)
docker exec "$CID" mkdir -p /sandbox/.agents/skills

# Copy the skill into the sandbox
docker cp skill/ "$CID":/sandbox/.agents/skills/fastapi-skill
```

Verify the files are in place:

```bash
openshell sandbox connect fastapi-demo

ls ~/.agents/skills/fastapi-skill/
# SKILL.md  main.py  skill.yaml

exit
```

---

## Step 7 — Test the Skill (No LLM)

Connect to the sandbox and call the skill's `run()` function directly
with `python3`. No LLM or agent is involved — this tests the full path:
**sandbox → OpenShell proxy → host.docker.internal → FastAPI app**.

```bash
openshell sandbox connect fastapi-demo
cd ~/.agents/skills/fastapi-skill
```

### Health check

```bash
python3 -c "from main import run; print(run(action='health'))"
```

Expected:
```json
{"status": "ok", "base_url": "http://host.docker.internal:8000", "response": {"message": "hi there!"}}
```

### Discover endpoints

```bash
python3 -c "from main import run; print(run(action='list_endpoints'))"
```

Expected: JSON with all four endpoints (`/hi`, `/hello/{name}`, `/foo`, `/bar`).

### Call GET /hi

```bash
python3 -c "from main import run; print(run(action='call', method='GET', path='/hi'))"
```

Expected:
```json
{"status_code": 200, "response": {"message": "hi there!"}}
```

### Call GET /hello/world

```bash
python3 -c "from main import run; print(run(action='call', method='GET', path='/hello/world'))"
```

Expected:
```json
{"status_code": 200, "response": {"message": "hello world!"}}
```

### Call GET /foo

```bash
python3 -c "from main import run; print(run(action='call', method='GET', path='/foo'))"
```

Expected:
```json
{"status_code": 200, "response": {"foo": "bar"}}
```

### Call POST /bar

```bash
python3 -c "from main import run; print(run(action='call', method='POST', path='/bar', body='{\"test\": 123}'))"
```

Expected:
```json
{"status_code": 200, "response": {"you_sent": {"test": 123}, "status": "ok"}}
```

```bash
exit
```

---

## Step 8 — Verify the OpenClaw Gateway + Execute the Skill

This step confirms the **OpenClaw gateway** is healthy inside the sandbox,
verifies the skill is registered, and exercises the full skill→API path.
The gateway was started automatically by `openclaw-start` in Step 2.

All commands below use only verified `openclaw` CLI subcommands
([CLI Reference](https://openclaws.io/docs/cli)).

```bash
openshell sandbox connect fastapi-demo
```

### 8.1 — Check the OpenClaw gateway health

```bash
openclaw gateway status
```

This probes the Gateway RPC and prints connection info (port, version,
uptime). If the gateway isn't running, start it manually:

```bash
openclaw onboard
openclaw gateway run &
```

### 8.2 — Confirm the gateway is reachable

```bash
openclaw gateway health
```

Returns a health summary. You can also probe with:

```bash
openclaw gateway probe
```

### 8.3 — List registered skills

```bash
openclaw skills list
```

You should see `fastapi-skill` in the output. If not, verify the skill
files were copied to `~/.agents/skills/fastapi-skill/` (Step 6).

### 8.4 — Execute the skill (no LLM)

The OpenClaw agent uses its `bash` tool to run skill code. Without an LLM
we replicate this directly — `python3` calls the skill's `run()` function,
which goes through the **OpenShell proxy → host.docker.internal → FastAPI**.

```bash
cd ~/.agents/skills/fastapi-skill

# Health check
python3 -c "from main import run; print(run(action='health'))"

# List endpoints
python3 -c "from main import run; print(run(action='list_endpoints'))"

# GET /hi
python3 -c "from main import run; print(run(action='call', method='GET', path='/hi'))"

# GET /hello/OpenClaw
python3 -c "from main import run; print(run(action='call', method='GET', path='/hello/OpenClaw'))"

# GET /foo
python3 -c "from main import run; print(run(action='call', method='GET', path='/foo'))"

# POST /bar
python3 -c "from main import run; print(run(action='call', method='POST', path='/bar', body='{\"from\": \"openclaw-agent\"}'))"
```

Expected POST response:
```json
{"status_code": 200, "response": {"you_sent": {"from": "openclaw-agent"}, "status": "ok"}}
```

### 8.5 — OpenClaw WebChat UI (requires LLM — not used in this example)

The `--forward 18789` flag (Step 2) forwards the OpenClaw WebChat port to
`http://127.0.0.1:18789/` on the host. However, **the UI will not load**
unless the OpenClaw gateway is fully running, which requires an LLM
provider (e.g. Anthropic, OpenAI) configured via `openclaw onboard`.

Without an LLM provider, the gateway never binds to port 18789. You'll see
this in the logs:

```
direct-tcpip: failed to connect addr=127.0.0.1:18789 error=Connection refused
```

**This is expected for a no-LLM setup.** Use the sandbox shell as shown in
8.4 above to exercise the skill directly.

```bash
exit
```

---

## Step 9 — Clean Up

```bash
openshell sandbox delete fastapi-demo
```

---

## API Endpoints

| Method | Path           | Description         |
|--------|----------------|---------------------|
| GET    | `/hi`          | Returns "hi there!" |
| GET    | `/hello/{name}`| Greets by name      |
| GET    | `/foo`         | Returns foo: bar    |
| POST   | `/bar`         | Echoes posted JSON  |

## Skill Configuration

Environment variables set **inside the sandbox** override auto-detection:

| Variable             | Default                            | Description              |
|----------------------|------------------------------------|--------------------------|
| `FASTAPI_SKILL_URL`  | `http://host.docker.internal:8000` | Full base URL override   |
| `FASTAPI_SKILL_PORT` | `8000`                             | Host port (auto-detect)  |

## OpenShell CLI Reference

| Command | Description |
|---------|-------------|
| `openshell sandbox create --name <n> --keep --from openclaw --forward 18789 -- openclaw-start` | Create an OpenClaw sandbox with UI forwarding |
| `openshell sandbox connect <name>` | Shell into a running sandbox |
| `openshell sandbox list` | List all sandboxes |
| `openshell sandbox delete <name>` | Stop and remove a sandbox |
| `openshell policy set <name> --policy f.yaml --wait` | Apply a policy (hot-reload, replaces entire policy) |
| `openshell policy get <name>` | View current policy |
| `openshell logs <name> --since 5m` | View recent logs |
| `openshell logs <name> --level warn --since 5m` | View deny/warning logs |
| `openshell status` | Gateway health check |

> Full CLI reference: `openshell --help`
> Docs: [docs.nvidia.com/openshell/latest](https://docs.nvidia.com/openshell/latest/)

## Troubleshooting

### `403 Forbidden` from proxy

Check the deny logs **from the host** (not inside the sandbox):

```bash
openshell logs fastapi-demo --level warn --since 5m
```

Common deny reasons:

#### `reason=endpoint has L7 rules; use CONNECT`

You have `protocol: rest` in your policy. The sandbox `http_proxy` uses
FORWARD mode, which is incompatible with L7 inspection. **Remove
`protocol: rest`** from the endpoint (TCP passthrough works).

#### `FORWARD blocked: internal IP without allowed_ips`

`host.docker.internal` resolves to a private RFC 1918 address
(`192.168.65.254` on Docker Desktop). The proxy blocks private IPs by
default. **Add `allowed_ips: ["192.168.65.0/24"]`** to the endpoint.
See [private-ip-routing example](https://github.com/NVIDIA/OpenShell/tree/main/examples/private-ip-routing).

#### Generic `action=deny`

The endpoint/port/binary doesn't match any policy entry. Re-apply:

```bash
openshell policy set fastapi-demo --policy openshell-policy.yaml --wait
openshell policy get fastapi-demo
```

### FastAPI app not reachable from host

```bash
lsof -i :8000
# Must show *:8000 or 0.0.0.0:8000, NOT localhost:8000
```

If bound to `127.0.0.1`, edit `app.py` and change the `uvicorn.run` host
to `0.0.0.0`.

### `/sandbox/.agents/skills` doesn't exist

The directory isn't created by default. Create it before copying:

```bash
CID=$(docker ps --filter name=openshell-cluster-openshell --format '{{.ID}}')
docker exec "$CID" mkdir -p /sandbox/.agents/skills
```

### Skill files missing inside sandbox

```bash
openshell sandbox connect fastapi-demo
ls -la ~/.agents/skills/fastapi-skill/
# Must contain: main.py  skill.yaml  SKILL.md
```

If missing, re-copy with `docker cp` (Step 6).
