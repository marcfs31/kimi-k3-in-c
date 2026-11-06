#!/usr/bin/env python
"""
fit_layers.py - largest --layers N whose shards and packed trunk fit on disk.

WHY THIS EXISTS
    The released checkpoint is 1.56 TB plus a 109 GB packed trunk. A machine
    with a 1.14 TB disk cannot store that, and a partial download that is
    sized by hope fills the filesystem the OS is running from. This reads the
    Hub index (the same map layers_to_shards.py uses) and the published shard
    sizes, and reports the deepest prefix that leaves a floor of free space
    after the shards AND the trunk are both on disk.

    The trunk reserve scales the published 108.81 GB file by N/93 and adds
    one 4096-byte alignment quantum per layer. That overestimates a prefix,
    which is the safe direction: a plan that fits this number fits the packer.

    usage: fit_layers.py <index.json> <shard_sizes.txt> --free BYTES [--floor BYTES]

    stdout, always, including when nothing fits:
        layers N
        bytes NEED
    Exit 0 when N >= 1, exit 1 when even one layer does not fit, exit 2 on a
    bad index or a shard with no published size. Exit 2 is the engine's own
    convention for a usage or config problem.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from layers_to_shards import decoder_depth, required_shards

# jetson-proof-of-life.sh EXPECT_TRUNK_BYTES. The full packed trunk.
FULL_TRUNK_BYTES = 108811952128
FULL_LAYERS = 93
ALIGN = 4096
# Leave the root filesystem enough room to keep logging after the download.
DEFAULT_FLOOR = 8 * 1024 * 1024 * 1024


def trunk_reserve(n_layers: int) -> int:
    if n_layers <= 0:
        return 0
    if n_layers >= FULL_LAYERS:
        return FULL_TRUNK_BYTES
    return (FULL_TRUNK_BYTES * n_layers + FULL_LAYERS - 1) // FULL_LAYERS + n_layers * ALIGN


def load_sizes(path: str) -> dict[str, int]:
    sizes: dict[str, int] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, nbytes = line.split()
            sizes[name] = int(nbytes)
    return sizes


def prefix_bytes(weight_map: dict, sizes: dict[str, int], n_layers: int) -> int:
    shards = required_shards(weight_map, n_layers)
    missing = sorted(s for s in shards if s not in sizes)
    if missing:
        raise ValueError("no published size for %s" % ", ".join(missing))
    return sum(sizes[s] for s in shards) + trunk_reserve(n_layers)


def max_prefix(weight_map: dict, sizes: dict[str, int], free_bytes: int, floor_bytes: int) -> tuple[int, int]:
    """Return (n_layers, need_bytes). n_layers is 0 when nothing fits.
    need_bytes is the cost of the chosen prefix, or of one layer when none fit.
    """
    if free_bytes < 0 or floor_bytes < 0:
        raise ValueError("free and floor must be >= 0")
    budget = free_bytes - floor_bytes
    deepest = decoder_depth(weight_map)
    if deepest < 1:
        raise ValueError("index has no decoder layer")
    if deepest > FULL_LAYERS:
        deepest = FULL_LAYERS
    one = prefix_bytes(weight_map, sizes, 1)
    if budget < one:
        return 0, one
    best = 1
    best_need = one
    lo, hi = 2, deepest
    while lo <= hi:
        mid = (lo + hi) // 2
        need = prefix_bytes(weight_map, sizes, mid)
        if need <= budget:
            best, best_need = mid, need
            lo = mid + 1
        else:
            hi = mid - 1
    return best, best_need


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="largest --layers N that fits in free bytes")
    p.add_argument("index")
    p.add_argument("sizes")
    p.add_argument("--free", required=True, help="free bytes on the destination filesystem")
    p.add_argument("--floor", default=str(DEFAULT_FLOOR), help="bytes to leave free (default 8 GiB)")
    args = p.parse_args(argv)
    try:
        args.free = int(args.free)
        args.floor = int(args.floor)
    except ValueError:
        p.error("--free and --floor must be integers")
    if args.free < 0 or args.floor < 0:
        p.error("--free and --floor must be >= 0")
    return args


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        with open(args.index, encoding="utf-8") as f:
            index = json.load(f)
    except (OSError, ValueError) as e:
        print("fit_layers: cannot read %s: %s" % (args.index, e), file=sys.stderr)
        return 2
    weight_map = index.get("weight_map") if isinstance(index, dict) else None
    if not isinstance(weight_map, dict) or not weight_map:
        print("fit_layers: %s has no usable weight_map." % args.index, file=sys.stderr)
        return 2
    try:
        sizes = load_sizes(args.sizes)
        n_layers, need = max_prefix(weight_map, sizes, args.free, args.floor)
    except (OSError, ValueError) as e:
        print("fit_layers: %s" % e, file=sys.stderr)
        return 2
    sys.stdout.reconfigure(newline="\n")
    print("layers %d" % n_layers)
    print("bytes %d" % need)
    return 0 if n_layers >= 1 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
