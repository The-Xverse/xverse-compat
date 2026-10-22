#!/bin/bash
# Create the pinned CARLA 0.9.15 cp310 client environment (thesis 028 P4b-T01; decision DLG-1).
# Usage: make-client-env.sh <envdir> <wheeldir> <record-out>
# Refuses below 2 GB free; downloads the pinned wheel only if absent or mismatched; verifies size and
# SHA-256; python3.10 -m venv; pip install --no-deps; offline import check; py_compile of
# xverse_compat_carla; writes a JSON record. Never starts CARLA, the bridge or zenohd.
set -euo pipefail
ENV=$1; WHEELS=$2; RECORD=$3
WHEEL=carla-0.9.15-cp310-cp310-manylinux_2_27_x86_64.whl
SHA=61449e33260f6a0cfd2f88d56f2463a5797a0b51bc46618beec07365422d4ad6
SIZE=31895950
URL=https://files.pythonhosted.org/packages/86/5a/74cf6657e5bb4b8ffe790ef92a01d7f44592a992d758c7053cd6bc75bd96/$WHEEL
HERE=$(cd "$(dirname "$0")/../.." && pwd)
mkdir -p "$WHEELS"
free_kb=$(df -Pk "$(dirname "$ENV")" | awk 'NR==2{print $4}')
[ "$free_kb" -ge 2097152 ] || { echo "refused: less than 2 GB free" >&2; exit 2; }
if [ ! -f "$WHEELS/$WHEEL" ] || [ "$(sha256sum "$WHEELS/$WHEEL" | cut -d' ' -f1)" != "$SHA" ]; then
  curl -fsSL --max-time 600 -o "$WHEELS/$WHEEL" "$URL"
fi
[ "$(stat -c %s "$WHEELS/$WHEEL")" = "$SIZE" ] && [ "$(sha256sum "$WHEELS/$WHEEL" | cut -d' ' -f1)" = "$SHA" ] || { echo "refused: wheel hash or size mismatch" >&2; exit 3; }
[ ! -e "$ENV" ] || { echo "refused: $ENV exists" >&2; exit 4; }
env -i PATH=/usr/bin HOME=/nonexistent-carla-home /usr/bin/python3.10 -m venv "$ENV"
env -i PATH=/usr/bin HOME=/nonexistent-carla-home "$ENV/bin/python" -s -m pip install --no-deps --no-index -q "$WHEELS/$WHEEL"
import_out=$(env -i PATH=/usr/bin HOME=/nonexistent-carla-home "$ENV/bin/python" -s -c 'import carla, importlib.metadata as m; print(m.version("carla")); print(carla.__file__)' 2>&1) && import_rc=0 || import_rc=$?
compile_rc=0
if [ -d "$HERE/src/xverse_compat_carla" ]; then
  env -i PATH=/usr/bin HOME=/nonexistent-carla-home "$ENV/bin/python" -s -m compileall -q -x '__pycache__' "$HERE/src/xverse_compat_carla" > /dev/null || compile_rc=$?
  find "$HERE/src/xverse_compat_carla" -name '__pycache__' -type d -prune -exec rm -rf {} +
fi
freeze=$(env -i PATH=/usr/bin HOME=/nonexistent-carla-home "$ENV/bin/python" -s -m pip freeze --all 2>/dev/null)
size_kb=$(du -sk "$ENV" | cut -f1)
python3 - "$RECORD" <<PY
import json, sys, hashlib
rec = {"schema": "xverse-compat.carla-env-record/1", "wheel": "$WHEEL", "wheelSha256": "$SHA", "wheelSize": $SIZE,
       "wheelSource": "$URL", "interpreter": "/usr/bin/python3.10", "envSizeKiB": $size_kb,
       "importReturnCode": $import_rc, "importOutput": """$import_out""".splitlines(),
       "pipFreeze": """$freeze""".splitlines(), "pyCompileReturnCode": $compile_rc,
       "networkSessions": "none (download only)", "executed": "none of CARLA, bridge, zenohd"}
open(sys.argv[1], "w").write(json.dumps(rec, indent=2, sort_keys=True) + "\n")
PY
echo "import=$import_rc compile=$compile_rc size=${size_kb}KiB"
[ "$import_rc" = 0 ]
