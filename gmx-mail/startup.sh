#!/bin/sh
set -eu
cd /workspace
node scripts/preview.mjs stop || true

if ! curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8765/health; then
  PYTHONPATH=/workspace python3 -m gmxmail serve --host 127.0.0.1 --port 8765 >>/tmp/gmxmail.log 2>&1 &
fi

if curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8080/; then
  exit 0
fi

export GMX_API_URL=http://127.0.0.1:8765
npm run dev >>/tmp/app-startup.log 2>&1 &
