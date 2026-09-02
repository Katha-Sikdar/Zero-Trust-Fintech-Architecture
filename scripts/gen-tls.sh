#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")/.." && pwd)/gateway/tls"
mkdir -p "$DIR"
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$DIR/server.key" \
  -out "$DIR/server.crt" -days 365 -subj "/CN=zta-testbed.local" >/dev/null 2>&1
echo "wrote self-signed TLS to gateway/tls/"
