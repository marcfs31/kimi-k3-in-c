#!/usr/bin/env python
"""Disk-fit contract for tools/fit_layers.py.

The fixture is tests/fixtures/partial_index.json plus partial_shard_sizes.txt.
Layer 7 lives only in shard 4, so a budget that pays for layers 0..6 must not
pull that shard, and a budget one byte under one layer must report layers 0
rather than a prefix that would fill the disk.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from fit_layers import (  # noqa: E402
    FULL_LAYERS,
    FULL_TRUNK_BYTES,
    main,
    prefix_bytes,
    trunk_reserve,
)
from layers_to_shards import required_shards  # noqa: E402

FIXTURES = os.path.join(ROOT, "tests", "fixtures")
INDEX = os.path.join(FIXTURES, "partial_index.json")
SIZES = os.path.join(FIXTURES, "partial_shard_sizes.txt")


def load():
    with open(INDEX, encoding="utf-8") as f:
        weight_map = json.load(f)["weight_map"]
    sizes = {}
    with open(SIZES, encoding="utf-8") as f:
        for line in f:
            name, nbytes = line.split()
            sizes[name] = int(nbytes)
    return weight_map, sizes


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


def main_test():
    weight_map, sizes = load()
    # The published full trunk is reserved whole at 93 layers, and a prefix
    # is strictly larger than a naive N/93 slice because of alignment.
    if trunk_reserve(FULL_LAYERS) != FULL_TRUNK_BYTES:
        fail("full trunk reserve %s != %s" % (trunk_reserve(FULL_LAYERS), FULL_TRUNK_BYTES))
    naive = FULL_TRUNK_BYTES // FULL_LAYERS
    if trunk_reserve(1) <= naive:
        fail("one-layer trunk reserve %s is not above the naive slice %s" % (trunk_reserve(1), naive))

    previous = 0
    for n in range(1, 9):
        need = prefix_bytes(weight_map, sizes, n)
        if need < previous:
            fail("prefix cost shrank from %d to %d at layer %d" % (previous, need, n))
        previous = need

    shards7 = required_shards(weight_map, 7)
    shards8 = required_shards(weight_map, 8)
    if "model-00004-of-00005.safetensors" in shards7:
        fail("layers 0..6 pulled the shard that holds only layer 7")
    if "model-00004-of-00005.safetensors" not in shards8:
        fail("layers 0..7 missed the shard that holds layer 7")

    one = prefix_bytes(weight_map, sizes, 1)
    seven = prefix_bytes(weight_map, sizes, 7)
    eight = prefix_bytes(weight_map, sizes, 8)

    def run(free, floor):
        return main([INDEX, SIZES, "--free", str(free), "--floor", str(floor)])

    from fit_layers import max_prefix

    n, need = max_prefix(weight_map, sizes, one - 1, 0)
    if n != 0 or need != one:
        fail("one byte under one layer returned %s %s" % (n, need))
    if run(one - 1, 0) != 1:
        fail("CLI under-budget exit was not 1")

    n, need = max_prefix(weight_map, sizes, one, 0)
    if n != 1 or need != one:
        fail("exact one-layer budget returned %s %s" % (n, need))
    if run(one, 0) != 0:
        fail("CLI exact one-layer exit was not 0")

    n, need = max_prefix(weight_map, sizes, one, 1)
    if n != 0:
        fail("a 1-byte floor on an exact one-layer budget still selected %s" % n)

    n, need = max_prefix(weight_map, sizes, seven, 0)
    if n != 7 or need != seven:
        fail("budget for 7 layers returned %s (need %s, expected %s)" % (n, need, seven))
    if eight <= seven:
        fail("layer 8 did not cost more than layer 7")
    n, _need = max_prefix(weight_map, sizes, eight - 1, 0)
    if n != 7:
        fail("one byte under 8 layers returned %s, expected 7" % n)

    n, need = max_prefix(weight_map, sizes, eight + 10**12, 0)
    if n != 8 or need != eight:
        fail("a huge disk returned %s layers, expected 8" % n)

    # A size table that omits a shard the prefix needs is a refusal, not a guess.
    missing = os.path.join(FIXTURES, "partial_shard_sizes_missing.txt")
    with open(missing, "w", encoding="utf-8") as f:
        f.write("model-00001-of-00005.safetensors 1000\n")
    try:
        rc = main([INDEX, missing, "--free", "999999999", "--floor", "0"])
    finally:
        os.remove(missing)
    if rc != 2:
        fail("missing shard size returned %s, expected 2" % rc)

    print("FIT LAYERS TESTS PASSED")


if __name__ == "__main__":
    main_test()
