---
name: fastapi-skill
description: "Calls a FastAPI app running on the host machine via host.docker.internal"
---

# FastAPI Skill

Calls a FastAPI app running on the host machine (outside this OpenShell
sandbox). The app is reachable at `host.docker.internal:8000`.

## Actions

### Health Check
```
run(action="health")
```

### List Endpoints
```
run(action="list_endpoints")
```

### Call an Endpoint
```
run(action="call", method="GET", path="/hi")
run(action="call", method="GET", path="/hello/world")
run(action="call", method="GET", path="/foo")
run(action="call", method="POST", path="/bar", body='{"key": "value"}')
```

## Rules

- Call `list_endpoints` first to discover available routes.
- Use the correct HTTP method for each endpoint.
- Pass POST/PUT/PATCH bodies as JSON strings.
