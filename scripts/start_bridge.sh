#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/telephony/bridge"

if [ ! -f .env ]; then
  echo "No .env - copy .env.example and fill in TWILIO_* and PUBLIC_BASE_URL first."
  exit 1
fi
if [ ! -d node_modules ]; then
  npm install
fi

echo "Starting Recovery AI telephony bridge on :3100"
echo "Remember: ngrok http 3100, and PUBLIC_BASE_URL must match the ngrok URL."
npm start
