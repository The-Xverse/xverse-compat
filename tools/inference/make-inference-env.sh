#!/bin/bash
# Build the pinned U4 inference venv (thesis 002 Phase 8 WP-08; design record docs/engineering/phase8/review-wp08.md).
# Usage: make-inference-env.sh <envdir> <wheeldir> <lock> <record-out>
# Refuses below 2 GB free, if <envdir> exists, or if a locked wheel is missing or differs from its lock hash.
# Creates the venv --without-pip with the pyenv CPython 3.13.13 interpreter that runs U4, and installs into it with
# that interpreter's own pip (--python): --no-index --find-links <wheeldir> --require-hashes --no-deps --no-compile,
# so the venv holds no pip and no bytecode (finding 4, MEDIUM-2). Runs an offline import check through the U4
# pattern (the real interpreter, PYTHONPATH to site-packages, -s -B, single-threaded, telemetry disabled), refuses if
# any __pycache__ or .pyc exists afterwards, and writes a JSON identity record that digests every venv file, the
# standard library, libpython and the installing pip (LOW-1), and binds the lock by hash and repository path (LOW-3).
# Never downloads, never touches another venv, never starts CARLA, Maestro or a unit.
set -euo pipefail
ENV=$1; WHEELS=$2; LOCK=$3; RECORD=$4
PY313=/home/jefferson/.pyenv/versions/3.13.13/bin/python3.13
HERE=$(cd "$(dirname "$0")/../.." && pwd)
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
"${CLEAN[@]}" "$PY313" -s -B -m venv --without-pip "$ENV/venv"
PIP=("${CLEAN[@]}" "$PY313" -s -B -m pip --python "$ENV/venv/bin/python" --disable-pip-version-check --no-cache-dir)
"${PIP[@]}" install -q --no-index --find-links "$WHEELS" --require-hashes --no-deps --no-compile -r "$LOCK"
SITE="$ENV/venv/lib/python3.13/site-packages"
# ORT_DISABLE_TELEMETRY=1: the 1.31 wheel embeds 1DS telemetry (review-wp08 finding 2); the U4 unit sets it as well
check='import numpy, onnxruntime as ort; print("numpy", numpy.__version__); print("onnxruntime", ort.__version__); print("providers", ort.get_available_providers())'
import_out=$("${CLEAN[@]}" ORT_DISABLE_TELEMETRY=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 PYTHONPATH="$SITE" "$PY313" -s -B -c "$check" 2>&1) && import_rc=0 || import_rc=$?
bytecode=$(find "$ENV/venv" \( -name __pycache__ -o -name '*.pyc' \) -print | head -5)
[ -z "$bytecode" ] || { echo "refused: bytecode present after the build: $bytecode" >&2; exit 5; }
freeze=$("${PIP[@]}" freeze --all 2>/dev/null)
pip_version=$("${CLEAN[@]}" "$PY313" -s -B -m pip --version | cut -d' ' -f2)
lock_rel=$(realpath --relative-to="$HERE" "$LOCK")
revision=$(git -C "$HERE" rev-parse HEAD 2>/dev/null || echo unknown)
"${CLEAN[@]}" "$PY313" -s -I -B - "$RECORD" "$WHEELS" "$LOCK" "$lock_rel" "$revision" "$ENV/venv" "$SITE" "$PY313" "$import_rc" \
  "$import_out" "$freeze" "$pip_version" "$(du -sk "$ENV" | cut -f1)" <<'PY'
import hashlib, json, os, platform, sys, sysconfig
(record, wheels, lock, lock_rel, revision, venv, site, py, rc, out, freeze, pip_version, size) = sys.argv[1:]
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()


def tree(root, skip=()):
    """SHA-256 over sorted relative paths: a file contributes its SHA-256, a symlink its target (not followed)."""
    digest, count = hashlib.sha256(), 0
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in skip and os.path.join(base, d) not in skip)
        for name in sorted(files + [d for d in os.listdir(base) if os.path.islink(os.path.join(base, d)) and d not in files]):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, root)
            entry = "link:" + os.readlink(path) if os.path.islink(path) else sha(path)
            digest.update(f"{rel}\0{entry}\n".encode())
            count += 1
    return {"sha256": digest.hexdigest(), "entries": count}


cpu = {}
for line in open("/proc/cpuinfo"):
    key, _, value = line.partition(":")
    if key.strip() in ("model name", "flags") and key.strip() not in cpu:
        cpu[key.strip()] = value.strip()
stdlib = sysconfig.get_paths()["stdlib"]  # the base interpreter's lib/python3.13 (this script runs on it)
base_site = sysconfig.get_paths()["purelib"]
libdir = sysconfig.get_config_var("LIBDIR")
ldlibrary = sysconfig.get_config_var("INSTSONAME") or sysconfig.get_config_var("LDLIBRARY")
libpython = os.path.join(libdir, ldlibrary) if libdir and ldlibrary and os.path.isfile(os.path.join(libdir, ldlibrary)) else None
pip_dist = [d for d in os.listdir(base_site) if d.startswith("pip-") and d.endswith(".dist-info")]
rec = {"schema": "xverse-compat.inference-env-record/2",
       "lock": {"repositoryPath": lock_rel, "sha256": sha(lock), "repositoryRevision": revision},
       "wheels": [{"name": n, "sha256": sha(os.path.join(wheels, n)), "size": os.path.getsize(os.path.join(wheels, n))}
                  for n in sorted(os.listdir(wheels)) if n.endswith(".whl")],
       "installed": freeze.splitlines(), "installFlags": "--no-index --find-links <wheels> --require-hashes --no-deps --no-compile",
       "bytecode": "none (--no-compile; checked after the import check)",
       "sitePackages": site, "sitePackagesTree": tree(site), "venvTree": tree(venv),
       "interpreter": {"path": py, "sha256": sha(py), "version": platform.python_version(),
                       "libpython": None if libpython is None else {"path": os.path.realpath(libpython), "sha256": sha(libpython)},
                       "stdlib": stdlib, "stdlibTree": tree(stdlib, skip=("__pycache__", os.path.join(stdlib, "site-packages")))},
       "installer": {"pip": pip_version, "pipTree": tree(os.path.join(base_site, "pip"), skip=("__pycache__",)),
                     "pipDistInfo": {d: tree(os.path.join(base_site, d)) for d in pip_dist}},
       "glibc": platform.libc_ver(), "cpu": cpu, "importReturnCode": int(rc), "importOutput": out.splitlines(),
       "envSizeKiB": int(size), "executed": "import check only"}
open(record, "w").write(json.dumps(rec, indent=2, sort_keys=True) + "\n")
PY
echo "import=$import_rc size=$(du -sk "$ENV" | cut -f1)KiB record=$RECORD"
[ "$import_rc" = 0 ]
