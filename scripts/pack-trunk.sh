#!/usr/bin/env bash
# pack-trunk.sh, build the packed trunk that makes memory a dial.
#
#   scripts/pack-trunk.sh <model_dir> <trunk_dir> [n_layers]
#
# Each layer's trunk tensors form one contiguous run inside its shard, so this is one
# sequential range copy per layer rather than a scatter-gather. Afterwards, loading a
# layer is a single pread from a known offset, which is what lets the trunk stream at
# full device bandwidth and overlap compute. n_layers defaults to 93. A partial
# checkpoint passes the same N that download-model.sh recorded.
#
# Output is ~108.81 GB for all 93 layers, less for a prefix. Put it on the fastest
# local storage you have.
set -euo pipefail
MODEL="${1:?usage: pack-trunk.sh <model_dir> <trunk_dir> [n_layers]}"
TRUNK="${2:?usage: pack-trunk.sh <model_dir> <trunk_dir> [n_layers]}"
LAYERS="${3:-93}"
case "$LAYERS" in
    ''|*[!0-9]*|0*)
        echo "pack-trunk.sh: n_layers must be a positive integer, got '$LAYERS'." >&2
        exit 1 ;;
esac

command -v python3 >/dev/null || { echo "python3 required"; exit 1; }
[ -d "$MODEL" ] || { echo "no such model dir: $MODEL"; exit 1; }

# find, not `ls | wc -l`: under `set -euo pipefail` a glob that matches nothing makes
# ls exit non-zero, the pipeline fails, and the script dies AT THIS LINE -- so the
# diagnostic on the next line, which is the whole reason the check exists, never prints.
N=$(find "$MODEL" -maxdepth 1 -name '*.safetensors' | wc -l)
[ "$N" -gt 0 ] || { echo "no .safetensors in $MODEL, run download-model.sh first"; exit 1; }

mkdir -p "$TRUNK"
echo "packing trunk from $N shards -> $TRUNK ($LAYERS layers)"
python3 "$(dirname "$0")/../tools/pack_trunk.py" "$MODEL" "$TRUNK" "$LAYERS"

echo
ls -la "$TRUNK"
echo
if [ "$LAYERS" -eq 93 ]; then
    echo "next: ./bin/k3 $MODEL --trunk $TRUNK --preset server --tok $MODEL --prompt 'Hello' --incremental"
else
    echo "next: ./bin/k3 $MODEL --trunk $TRUNK --preset ultra --layers $LAYERS --tok $MODEL --prompt 'Hello' --gen 4"
fi
