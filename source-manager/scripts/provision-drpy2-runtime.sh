#!/usr/bin/env bash
# Build the isolated, reviewed drpy2 script runtime. It does not replace drpyS.
set -euo pipefail

readonly EXPECTED_COMMIT="dbf89cf8611b807d1ff270d1cb935f51749ea7f6"
readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly SOURCE_ROOT="${DRPY2_SOURCE_ROOT:-/opt/ponyo-drpy2-src}"
readonly SOURCE_DIR="$SOURCE_ROOT/$EXPECTED_COMMIT"
readonly SOURCE_ARCHIVE="${DRPY2_SOURCE_ARCHIVE:-}"
readonly GIT_URL="${DRPY2_GIT_URL:-https://github.com/zourjke/drpy-node.git}"
readonly BUNDLE_DIR="${DRPY2_BUNDLE_DIR:-$PROJECT_ROOT/data/drpy2-runtime}"
readonly PATCH_FILE="$PROJECT_ROOT/drpy2/runtime/drpy2-runtime.patch"
readonly LOCK_FILE="$PROJECT_ROOT/drpy2/runtime/package-lock.json"
readonly SOURCE_ARCHIVE_HASH_FILE="$PROJECT_ROOT/drpy2/runtime/source-archive.sha256"
readonly RUNTIME_DOCKERFILE="$PROJECT_ROOT/docker/drpy2-script-runtime.Dockerfile"

for file in "$PATCH_FILE" "$LOCK_FILE" "$SOURCE_ARCHIVE_HASH_FILE" "$RUNTIME_DOCKERFILE" "$BUNDLE_DIR/rule-map.json"; do
  if [[ ! -f "$file" ]]; then
    echo "required drpy2 runtime file missing: $file" >&2
    exit 2
  fi
done
if [[ ! -d "$BUNDLE_DIR/rules" ]]; then
  echo "reviewed drpy2 rules directory missing: $BUNDLE_DIR/rules" >&2
  exit 2
fi

bundle_hash="$(python3 - "$BUNDLE_DIR" <<'PY'
import hashlib
import sys
from pathlib import Path

root = Path(sys.argv[1])
digest = hashlib.sha256()
for path in [root / "rule-map.json", *sorted((root / "rules").glob("*.js"))]:
    digest.update(path.relative_to(root).as_posix().encode())
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")
print(digest.hexdigest()[:12])
PY
)"
readonly IMAGE="ponyo-drpy2-runtime:dbf89cf-p1-$bundle_hash"
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "$IMAGE"
  exit 0
fi

build_dir="$(mktemp -d /tmp/ponyo-drpy2-build.XXXXXX)"
worktree_created=0
cleanup() {
  if [[ "$worktree_created" == "1" ]]; then
    git -C "$SOURCE_DIR" worktree remove --force "$build_dir" >/dev/null 2>&1 || true
  else
    rm -rf "$build_dir"
  fi
}
trap cleanup EXIT

if [[ -n "$SOURCE_ARCHIVE" ]]; then
  if [[ ! -f "$SOURCE_ARCHIVE" ]]; then
    echo "reviewed source archive missing: $SOURCE_ARCHIVE" >&2
    exit 2
  fi
  expected_archive_hash="$(awk 'NR==1 {print $1}' "$SOURCE_ARCHIVE_HASH_FILE")"
  actual_archive_hash="$(sha256sum "$SOURCE_ARCHIVE" | awk '{print $1}')"
  if [[ "$actual_archive_hash" != "$expected_archive_hash" ]]; then
    echo "reviewed source archive hash mismatch" >&2
    exit 2
  fi
  python3 - "$SOURCE_ARCHIVE" "$build_dir" <<'PY'
import sys
import tarfile
from pathlib import Path, PurePosixPath

archive, target = Path(sys.argv[1]), Path(sys.argv[2])
with tarfile.open(archive, "r:gz") as handle:
    for member in handle.getmembers():
        path = PurePosixPath(member.name)
        if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
            raise SystemExit(f"unsafe source archive member: {member.name}")
    handle.extractall(target)
PY
else
  mkdir -p "$SOURCE_ROOT"
  if [[ ! -d "$SOURCE_DIR/.git" ]]; then
    git clone --filter=blob:none "$GIT_URL" "$SOURCE_DIR"
  fi
  if ! git -C "$SOURCE_DIR" cat-file -e "$EXPECTED_COMMIT^{commit}" 2>/dev/null; then
    git -C "$SOURCE_DIR" fetch --quiet origin "$EXPECTED_COMMIT"
  fi
  if [[ "$(git -C "$SOURCE_DIR" rev-parse "$EXPECTED_COMMIT^{commit}")" != "$EXPECTED_COMMIT" ]]; then
    echo "unable to resolve reviewed drpy2 commit" >&2
    exit 2
  fi
  rmdir "$build_dir"
  git -C "$SOURCE_DIR" worktree add --quiet --detach "$build_dir" "$EXPECTED_COMMIT"
  worktree_created=1
fi
git -C "$build_dir" apply --check "$PATCH_FILE"
git -C "$build_dir" apply "$PATCH_FILE"
install -m 0644 "$LOCK_FILE" "$build_dir/package-lock.json"
install -m 0644 "$RUNTIME_DOCKERFILE" "$build_dir/Dockerfile.ponyo"
install -m 0644 "$BUNDLE_DIR"/rules/*.js "$build_dir/spider/js_dr2/"

python3 - "$BUNDLE_DIR/rule-map.json" "$build_dir/spider/js_dr2" <<'PY'
import json
import hashlib
import sys
from pathlib import Path

registry = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
rules = registry.get("rules", registry)
if not isinstance(rules, dict) or not rules:
    raise SystemExit("rule-map.json must contain a non-empty object")
root = Path(sys.argv[2])
for url, entry in rules.items():
    module = entry if isinstance(entry, str) else entry.get("module")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        raise SystemExit(f"invalid registry URL: {url!r}")
    if not isinstance(module, str) or not module or any(c in module for c in "/\\?#%"):
        raise SystemExit(f"invalid registry module: {module!r}")
    rule_file = root / f"{module.removesuffix('.js')}.js"
    if not rule_file.is_file():
        raise SystemExit(f"registry module file missing: {module}")
    declared_sha256 = entry.get("sha256") if isinstance(entry, dict) else None
    actual_sha256 = hashlib.sha256(rule_file.read_bytes()).hexdigest()
    if declared_sha256 != actual_sha256:
        raise SystemExit(f"registry hash mismatch: {module}")
PY

docker build --pull=false \
  -f "$build_dir/Dockerfile.ponyo" \
  --label "org.opencontainers.image.revision=$EXPECTED_COMMIT" \
  --label "fun.ponyo.runtime=drpy2-isolated" \
  --label "fun.ponyo.bundle=$bundle_hash" \
  -t "$IMAGE" "$build_dir"

echo "$IMAGE"
