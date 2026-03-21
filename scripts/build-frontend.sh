#!/usr/bin/env bash
# build-frontend.sh — Build SvelteKit client and copy output to src/pocketpaw/webapp/
# Created: 2026-03-21

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CLIENT_DIR="$REPO_ROOT/client"
WEBAPP_DIR="$REPO_ROOT/src/pocketpaw/webapp"

if ! command -v bun &>/dev/null; then
    echo "Error: bun is required but not installed. Install from https://bun.sh" >&2
    exit 1
fi

echo "Building SvelteKit frontend..."
cd "$CLIENT_DIR"
bun install
bun run build

echo "Copying build output to src/pocketpaw/webapp/..."
rm -rf "$WEBAPP_DIR"
cp -r build "$WEBAPP_DIR"

echo "SvelteKit build copied to src/pocketpaw/webapp/"
