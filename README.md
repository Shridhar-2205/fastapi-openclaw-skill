# FastAPI Skill in OpenShell Sandbox

Connect a Python skill inside an [NVIDIA OpenShell](https://github.com/NVIDIA/OpenShell)
sandbox to a FastAPI app running on the host. No LLM required — test the
skill directly with `python3` and `curl` from inside the sandbox.

```
HOST                                   OPENSHELL SANDBOX (Docker)
┌──────────────┐                       ┌─────────────────────┐
│  app.py      │ ← HTTP (port 8000) ─ │  skill/main.py      │
│  0.0.0.0:8000│                       │       ↑ run()       │
│              │  host.docker.internal │                     │
└──────────────┘                       └─────────────────────┘
```

> **Docs:** [docs.nvidia.com/openshell/latest](https://docs.nvidia.com/openshell/latest/)
> — [Policy Schema](https://docs.nvidia.com/openshell/latest/reference/policy-schema.html)
> — [First Network Policy tutorial](https://docs.nvidia.com/openshell/latest/tutorials/first-network-policy.html)

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
connections are blocked. We need a policy that allows `python3` and `curl`
inside the sandbox to reach `host.docker.internal:8000`.

The included `openshell-policy.yaml` does exactly this. Apply it:

```bash
openshell policy set fastapi-demo --policy openshell-policy.yaml --wait
```

- `--wait` blocks until the sandbox confirms the policy is loaded.
- **Hot-reloads** — no sandbox restart needed.
- `policy set` **replaces the entire policy**, which is why the file
  includes `filesystem_policy`, `landlock`, and `process` sections too.

Verify the policy is active:

```bash
openshell policy get fastapi-demo
```

You should see the `host_fastapi` network policy with
`host: host.docker.internal`, `port: 8000`, `access: read-write`.

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

If you get a `403` or `policy_denied` response, the policy wasn't applied.
Check the deny log from the host:

```bash
openshell logs fastapi-demo --level warn --since 5m
```

Look for `action=deny` or `l7_decision=deny` entries. Re-apply the policy
with `openshell policy set fastapi-demo --policy openshell-policy.yaml --wait`.

Type `exit` to return to the host.

---

## Step 6 — Copy the Skill into the Sandbox

Skills are discovered from `/sandbox/.agents/skills/` inside the container
([base sandbox layout](https://github.com/NVIDIA/OpenShell-Community/tree/main/sandboxes/base)).

```bash
# Find the container ID
docker ps --filter name=fastapi-demo --format '{{.ID}}'

# Copy the skill directory into the sandbox
docker cp skill/ <container-id>:/sandbox/.agents/skills/fastapi-skill
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

### 8.5 — Access the OpenClaw WebChat UI (optional)

If you created the sandbox with `--forward 18789` (Step 2), the OpenClaw
WebChat UI is available in your browser at:

```
http://127.0.0.1:18789/
```

From WebChat you can interact with the agent (requires an LLM provider
configured via `openclaw onboard`). Without an LLM, use the sandbox shell
as shown in 8.4 above.

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

### `curl: (56) Received HTTP code 403 from proxy after CONNECT`

The sandbox proxy blocked the request. No network policy matches.

```bash
# Re-apply the policy
openshell policy set fastapi-demo --policy openshell-policy.yaml --wait

# Check deny logs
openshell logs fastapi-demo --level warn --since 5m
# Look for: action=deny dst_host=host.docker.internal dst_port=8000
```

### `l7_decision=deny` in logs

The connection was allowed but the HTTP method was blocked by L7 inspection.
The policy uses `access: read-write` which permits GET, HEAD, OPTIONS, POST,
PUT, PATCH. DELETE is not included — change to `access: full` if needed.

### FastAPI app not reachable from host

```bash
lsof -i :8000
# Must show *:8000 or 0.0.0.0:8000, NOT localhost:8000
```

If bound to `127.0.0.1`, edit `app.py` and change the `uvicorn.run` host
to `0.0.0.0`.

### Skill files missing inside sandbox

```bash
openshell sandbox connect fastapi-demo
ls -la ~/.agents/skills/fastapi-skill/
# Must contain: main.py  skill.yaml  SKILL.md
```

If missing, re-copy with `docker cp` (Step 6).
