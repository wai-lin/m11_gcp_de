## Dependency sync

Cloud Build reads `requirements.txt`, so keep it in sync with `uv` after dependency changes.

Use this wrapper instead of plain `uv add`:

```bash
./scripts/uv-add-sync.sh 'starlette>=0.46.0,<1.0.0'
```

It runs `uv add` and then regenerates `requirements.txt` from the lockfile.
