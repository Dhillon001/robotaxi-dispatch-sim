"""Synthetic city road graph.

A jittered grid centred on Foster City, CA. Swap `build_city` for an OSMnx
loader later; the rest of the sim only needs a networkx graph whose nodes
have `lat`/`lon` and whose edges have `time` (seconds to traverse).
"""
from __future__ import annotations

import math
import random

import networkx as nx

CENTER = (37.5585, -122.2711)  # Foster City, CA
M_PER_DEG_LAT = 111_000.0


def build_city(rows: int = 14, cols: int = 14, block_m: float = 220.0, seed: int = 7) -> nx.Graph:
    rng = random.Random(seed)
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(CENTER[0]))
    g = nx.Graph()
    for r in range(rows):
        for c in range(cols):
            jx, jy = rng.uniform(-25, 25), rng.uniform(-25, 25)
            y = (r - rows / 2) * block_m + jy
            x = (c - cols / 2) * block_m + jx
            g.add_node(
                (r, c),
                lat=CENTER[0] + y / M_PER_DEG_LAT,
                lon=CENTER[1] + x / m_per_deg_lon,
                x=x,
                y=y,
            )
    for r in range(rows):
        for c in range(cols):
            for dr, dc in ((0, 1), (1, 0)):
                nr, nc = r + dr, c + dc
                if nr < rows and nc < cols:
                    # drop a few edges so routing is non-trivial
                    if rng.random() < 0.06 and 0 < r < rows - 1 and 0 < c < cols - 1:
                        continue
                    a, b = g.nodes[(r, c)], g.nodes[(nr, nc)]
                    length = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                    arterial = (r % 4 == 0 and dr == 0) or (c % 4 == 0 and dc == 0)
                    speed = 13.0 if arterial else 8.0  # m/s
                    g.add_edge((r, c), (nr, nc), length=length, time=length / speed)
    # keep the largest connected component
    comp = max(nx.connected_components(g), key=len)
    return g.subgraph(comp).copy()


def zone_weights(g: nx.Graph, seed: int = 7) -> dict:
    """Static demand weights: a downtown hotspot plus a secondary one."""
    rng = random.Random(seed)
    nodes = list(g.nodes)
    hot = [rng.choice(nodes) for _ in range(2)]
    w = {}
    for n in nodes:
        a = g.nodes[n]
        s = 0.2
        for i, h in enumerate(hot):
            hh = g.nodes[h]
            d = math.hypot(a["x"] - hh["x"], a["y"] - hh["y"])
            s += (1.0 if i == 0 else 0.6) * math.exp(-((d / 600.0) ** 2))
        w[n] = s
    return w
