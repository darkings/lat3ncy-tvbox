#!/usr/bin/env bash
# Build the separately licensed drpy-node runtime at the reviewed, pinned commit.
set -euo pipefail

readonly EXPECTED_COMMIT="2f68bb00452685dcc57c3015995c178ccaac54fb"
readonly IMAGE="ponyo-drpy-node:2f68bb004526"
readonly SOURCE_ROOT="${DRPY2_SOURCE_ROOT:-/opt/ponyo-drpy-node-src}"
readonly SOURCE_DIR="$SOURCE_ROOT/$EXPECTED_COMMIT"
readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly RUNTIME_DOCKERFILE="$PROJECT_ROOT/docker/drpy2-runtime.Dockerfile"

if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "drpy-node image already present: $IMAGE"
    exit 0
fi

if [ ! -f "$SOURCE_DIR/Dockerfile" ]; then
    mkdir -p "$SOURCE_ROOT"
    git clone --filter=blob:none https://github.com/zourjke/drpy-node.git "$SOURCE_DIR"
    git -C "$SOURCE_DIR" checkout --detach "$EXPECTED_COMMIT"
fi

if [ -d "$SOURCE_DIR/.git" ]; then
    actual_commit=$(git -c "safe.directory=$SOURCE_DIR" -C "$SOURCE_DIR" rev-parse HEAD)
    if [ "$actual_commit" != "$EXPECTED_COMMIT" ]; then
        echo "Refusing unreviewed drpy-node commit: $actual_commit" >&2
        exit 1
    fi
    if ! git -c "safe.directory=$SOURCE_DIR" -C "$SOURCE_DIR" diff --quiet \
        || ! git -c "safe.directory=$SOURCE_DIR" -C "$SOURCE_DIR" diff --cached --quiet; then
        echo "Refusing a modified drpy-node source tree" >&2
        exit 1
    fi
elif [ "$(cat "$SOURCE_DIR/.ponyo-reviewed-commit" 2>/dev/null || true)" != "$EXPECTED_COMMIT" ]; then
    echo "Source snapshot lacks the reviewed-commit marker" >&2
    exit 1
fi

docker build --pull=false -f "$RUNTIME_DOCKERFILE" \
    --label "org.opencontainers.image.revision=$EXPECTED_COMMIT" \
    --label "fun.ponyo.runtime=drpys-only" \
    -t "$IMAGE" "$SOURCE_DIR"
