#!/bin/bash
# Build the pinned U4 inference venv (thesis 002 Phase 8 WP-08; design record docs/engineering/phase8/review-wp08.md).
# Usage: make-inference-env.sh <envdir> <wheeldir> <lock> <record-out>
# Refuses below 2 GB free, if <envdir> exists, or if a locked wheel is missing or differs from its lock hash;
# creates the venv with the pyenv CPython 3.13.13 interpreter that runs U4; pip install --no-index --require-hashes
# --no-deps from the local wheelhouse only; runs an offline import check through the U4 pattern (the real interpreter
# with PYTHONPATH to site-packages, single-threaded, telemetry disabled); writes a JSON identity record. Never downloads, never touches
# another venv, never starts CARLA, Maestro or a unit.
set -euo pipefail
ENV=$1; WHEELS=$2; LOCK=$3; RECORD=$4
PY313=/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13
CLEAN=(env -i PATH=/usr/bin HOME=/nonexistent-inference-home)
[ -x "$PY313" ] || { echo "refused: $PY313 missing" >&2; exit 2; }
free_kb=$(df -Pk "$(dirname "$ENV")" | awk 'NR==2{print $4}')
[ "$free_kb" -ge 2097152 ] || { echo "refused: less than 2 GB free" >&2; exit 2; }
[ ! -e "$ENV" ] || { echo "refused: $ENV exists" >&2; exit 4; }
# every locked requirement must name exactly one wheel in the wheelhouse whose SHA-256 equals its lock hash
grep -Ev '^\s*(#|$)' "$LOCK" | while read -r req hash; do
  name=${req%%==*}; version=${req#*==}; want=${hash#--hash=sha256:}
  matches=("$WHEELS/${name}-${version}-"*.whl)
  [ "${#matches[@]}" = 1 ] && [ -f "${matches[0]}" ] || { echo "refused: no unique wheel for $req" >&2; exit 3; }
  [ "$(sha256sum "${matches[0]}" | cut -d' ' -f1)" = "$want" ] || { echo "refused: hash mismatch for ${matches[0]}" >&2; exit 3; }
done
"${CLEAN[@]}" "$PY313" -s -m venv "$ENV/venv"
"${CLEAN[@]}" "$ENV/venv/bin/python" -s -m pip install -q --disable-pip-version-check --no-index --find-links "$WHEELS" \
  --require-hashes --no-deps -r "$LOCK"
SITE="$ENV/venv/lib/python3.13/site-packages"
check='import numpy, onnxruntime as ort; print("numpy", numpy.__version__); print("onnxruntime", ort.__version__); print("providers", ort.get_available_providers())'
# ORT_DISABLE_TELEMETRY=1: the 1.31 wheel embeds 1DS telemetry (review-wp08 finding 2); the U4 unit sets it as well
import_out=$("${CLEAN[@]}" ORT_DISABLE_TELEMETRY=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH="$SITE" "$PY313" -s -B -c "$check" 2>&1) && import_rc=0 || import_rc=$?
freeze=$("${CLEAN[@]}" "$ENV/venv/bin/python" -s -m pip freeze --all --disable-pip-version-check 2>/dev/null)
"${CLEAN[@]}" "$PY313" -s -I - "$RECORD" "$WHEELS" "$LOCK" "$SITE" "$PY313" "$import_rc" "$import_out" "$freeze" "$(du -sk "$ENV" | cut -f1)" <<'PY'
import hashlib, json, os, platform, sys
record, wheels, lock, site, py, rc, out, freeze, size = sys.argv[1:]
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
tree = hashlib.sha256()
for root, dirs, files in os.walk(site):
    dirs[:] = sorted(d for d in dirs if d != "__pycache__")
    for name in sorted(files):
        path = os.path.join(root, name)
        tree.update(f"{os.path.relpath(path, site)}\0{sha(path)}\n".encode())
cpu = {}
for line in open("/proc/cpuinfo"):
    key, _, value = line.partition(":")
    if key.strip() in ("model name", "flags") and key.strip() not in cpu:
        cpu[key.strip()] = value.strip()
rec = {"schema": "xverse-compat.inference-env-record/1", "lock": os.path.abspath(lock), "lockSha256": sha(lock),
       "wheels": [{"name": n, "sha256": sha(os.path.join(wheels, n)), "size": os.path.getsize(os.path.join(wheels, n))}
                  for n in sorted(os.listdir(wheels)) if n.endswith(".whl")],
       "pipFreeze": freeze.splitlines(), "sitePackages": site, "sitePackagesTreeSha256": tree.hexdigest(),
       "interpreter": py, "interpreterSha256": sha(py), "glibc": platform.libc_ver(), "cpu": cpu,
       "importReturnCode": int(rc), "importOutput": out.splitlines(), "envSizeKiB": int(size),
       "installFlags": "--no-index --find-links <wheels> --require-hashes --no-deps", "executed": "import check only"}
open(record, "w").write(json.dumps(rec, indent=2, sort_keys=True) + "\n")
PY
echo "import=$import_rc size=$(du -sk "$ENV" | cut -f1)KiB record=$RECORD"
[ "$import_rc" = 0 ]
