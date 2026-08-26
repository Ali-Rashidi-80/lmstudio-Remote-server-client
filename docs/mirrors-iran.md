# Iranian mirrors (Chabokan)

**English** · [فارسی](fa/mirrors-iran.md)

Prefer local mirrors when international connectivity is restricted.

## PyPI

```
pip install -r backend/requirements.txt \
  -i https://mirror2.chabokan.net/pypi/simple/ \
  --trusted-host mirror2.chabokan.net
```

Or copy `pip.conf.example` to your pip config.

## npm

`web/.npmrc`:

```
registry=https://mirror2.chabokan.net/npm/
```

## Docker

Daemon:

```json
{ "registry-mirrors": ["https://mirror2.chabokan.net"] }
```

Or pull with prefix:

```
docker pull mirror2.chabokan.net/redis:7-alpine
```

`pgvector/pgvector:pg16` may need upstream if not cached; scripts fall back automatically.

Helpers: `scripts/install-deps.ps1` / `scripts/install-deps.sh`.

Source: https://iran.chabokan.net/
