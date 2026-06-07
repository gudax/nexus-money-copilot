#!/bin/sh
# Boot the fleet inside one Cloud Run container: two A2A workers on localhost,
# then the audited service on $PORT. Real A2A transport, single deployable.
set -e
python fleet/serve_worker.py markets 8101 &
python fleet/serve_worker.py account 8102 &
for i in $(seq 1 30); do
  ok=0
  curl -sf localhost:8101/.well-known/agent-card.json >/dev/null && \
  curl -sf localhost:8102/.well-known/agent-card.json >/dev/null && ok=1
  [ "$ok" = "1" ] && break
  sleep 1
done
echo "fleet up: markets:8101 account:8102 — starting service on ${PORT:-8080}"
exec uvicorn service.app:app --host 0.0.0.0 --port "${PORT:-8080}"
