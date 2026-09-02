#!/usr/bin/env bash
# Fetch the pinned istioctl into tools/. Pinned rather than "latest" so the
# control plane matches the istio/pilot + istio/proxyv2 images the scenarios
# reference -- a version skew between them changes sidecar behaviour and would
# silently confound the enforcement-placement comparison.
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${ISTIO_VERSION:-1.28.0}"
DEST="tools/istio-${VERSION}"

if [ -x "$DEST/bin/istioctl" ]; then
  echo "istioctl ${VERSION} already present at $DEST/bin/istioctl"; exit 0
fi

case "$(uname -s)" in
  Darwin) OS=osx ;;
  Linux)  OS=linux ;;
  *) echo "unsupported OS $(uname -s) - install istioctl ${VERSION} manually" >&2; exit 1 ;;
esac
case "$(uname -m)" in
  arm64|aarch64) ARCH=arm64 ;;
  x86_64|amd64)  ARCH=amd64 ;;
  *) echo "unsupported arch $(uname -m) - install istioctl ${VERSION} manually" >&2; exit 1 ;;
esac
# the osx amd64 archive is named without an arch suffix
if [ "$OS" = osx ] && [ "$ARCH" = amd64 ]; then TARBALL="istio-${VERSION}-osx.tar.gz"
else TARBALL="istio-${VERSION}-${OS}-${ARCH}.tar.gz"; fi

URL="https://github.com/istio/istio/releases/download/${VERSION}/${TARBALL}"
echo "downloading ${TARBALL}"
mkdir -p tools
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if ! curl -fsSL -o "$TMP/istio.tgz" "$URL"; then
  echo "download failed: $URL" >&2; exit 1
fi
tar xzf "$TMP/istio.tgz" -C tools
[ -x "$DEST/bin/istioctl" ] || { echo "archive did not contain $DEST/bin/istioctl" >&2; exit 1; }
echo "installed $("$DEST/bin/istioctl" version --remote=false 2>/dev/null) at $DEST/bin/istioctl"
