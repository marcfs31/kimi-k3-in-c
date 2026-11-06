#!/usr/bin/env bash
# setup-small-linux.sh - build Kimi K3 on a terminal-only Linux box whose
# disk cannot hold the 1.56 TB checkpoint.
#
#   ./scripts/setup-small-linux.sh
#   ./scripts/setup-small-linux.sh --download ~/k3model
#
# Written for an 8 GB machine in this class: 4 cores, AVX2, one disk of about
# 1.14 TB (a Dell OptiPlex 3050 with an i5-6500T is the measured target).
# Linux with no desktop leaves enough of the 8 GB for --preset ultra. The
# full checkpoint still does not fit, so --download fetches the deepest layer
# prefix that leaves 8 GiB free after the shards and the packed trunk.
#
# A prefix is not the model. The engine prints that on every such run.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

usage() {
    echo "usage: setup-small-linux.sh [--download DIR]" >&2
    exit 2
}

if [ "$(uname -s)" != "Linux" ]; then
    echo "setup-small-linux: this path is for a Linux terminal. Detected $(uname -s)." >&2
    echo "  Build with 'make -j && make test' on other systems. The disk plan reads" >&2
    echo "  Linux free space and is what makes an 8 GB, sub-1.7 TB box able to run." >&2
    exit 1
fi

DOWNLOAD=0
DEST=""
case "${1:-}" in
    "") ;;
    --download)
        DOWNLOAD=1
        DEST="${2:-}"
        [ -n "$DEST" ] || usage
        [ -z "${3:-}" ] || usage
        ;;
    *) usage ;;
esac

missing=0
if ! command -v cc >/dev/null 2>&1 && ! command -v gcc >/dev/null 2>&1; then
    echo "missing a C compiler. On Debian or Ubuntu: sudo apt install build-essential" >&2
    missing=1
fi
if ! command -v make >/dev/null 2>&1; then
    echo "missing make. On Debian or Ubuntu: sudo apt install build-essential" >&2
    missing=1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "missing python3. On Debian or Ubuntu: sudo apt install python3 python3-venv" >&2
    missing=1
fi
[ "$missing" -eq 0 ] || exit 1

if ! grep -qm1 avx2 /proc/cpuinfo 2>/dev/null; then
    echo "warn: AVX2 not detected. The engine still runs; the matmuls take the scalar path." >&2
fi

JOBS="$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)"
make -j"$JOBS"
make test

if [ "$DOWNLOAD" -eq 0 ]; then
    cat <<'EOF'

Engine built, and the weightless tests passed.

The full checkpoint is 1.56 TB plus a 109 GB trunk. This disk does not have
that. The next command downloads the deepest layer prefix that fits, packs a
trunk for those layers, and prints the run line. A prefix is not Kimi K3;
the program says so on every run.

  ./scripts/setup-small-linux.sh --download "$HOME/k3model"
EOF
    exit 0
fi

# huggingface_hub's `hf` CLI. A venv, not a system pip: Debian's Python is
# externally managed and a root install is the wrong fix.
if ! command -v hf >/dev/null 2>&1; then
    VENV="${HOME}/.venvs/k3-hf"
    if [ ! -x "$VENV/bin/hf" ]; then
        if ! python3 -m venv "$VENV"; then
            echo "python3 -m venv failed. On Debian or Ubuntu: sudo apt install python3-venv" >&2
            exit 1
        fi
        "$VENV/bin/pip" install -U pip huggingface_hub
    fi
    export PATH="$VENV/bin:$PATH"
fi
command -v hf >/dev/null 2>&1 || { echo "the hf CLI is still not on PATH" >&2; exit 1; }

mkdir -p "$DEST"
./scripts/download-model.sh "$DEST" --fit
N="$(tr -d '[:space:]' < "$DEST/.k3_layers")"
case "$N" in
    ''|*[!0-9]*|0*) echo "download did not record a layer count in $DEST/.k3_layers" >&2; exit 1 ;;
esac
TRUNK="${DEST%/}-trunk"
./scripts/pack-trunk.sh "$DEST" "$TRUNK" "$N"

echo
if [ "$N" -eq 93 ]; then
    echo "Full 93-layer checkpoint is on disk."
    LAYERS_FLAG=""
else
    echo "PARTIAL CHECKPOINT: layers 0..$((N - 1)) of 93. This is not the full model."
    LAYERS_FLAG="--layers $N "
fi
cat <<EOF

Run it from a terminal (no display needed):

  ./bin/k3 ${DEST} --trunk ${TRUNK} --preset ultra ${LAYERS_FLAG}\\
      --tok ${DEST} --prompt "Hello" --gen 4

--preset ultra is the 8 GB plan: about 3 GB, streamed embeddings, one state
slot. It is slow on this CPU and on a spinning disk or a SATA SSD, because
each token reads the prefix from disk. Close other programs first. Drop
--incremental; the KV cache is about 2.37 MB per position and is optional
for a one-shot prompt.
EOF
