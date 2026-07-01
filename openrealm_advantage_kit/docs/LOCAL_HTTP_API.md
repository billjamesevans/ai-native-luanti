# Local HTTP API

Run:

```bash
python -m openrealm_creator_kernel.cli serve --port 8787
```

Health check:

```bash
curl http://127.0.0.1:8787/health
```

Plan endpoint:

```bash
curl -s http://127.0.0.1:8787/v1/plan \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Build a cozy lakeside village with floating lanterns"}' | python -m json.tool
```

The response contains:

- `ok`
- `plan`
- `safety`

The API is intentionally local-only and dependency-free. Use it to connect a launcher prototype, a Luanti mod prototype, or a future desktop app to the creator kernel.
