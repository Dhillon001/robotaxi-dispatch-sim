"""City road networks.

`City` wraps a networkx graph (nodes carry lat/lon plus local x/y metres; edges
carry `length` in metres and `time` in seconds) and provides lazy, cached
shortest-path queries so large real road networks stay fast.

Sources:
  * "grid"  - synthetic jittered grid (instant, offline)
  * others  - real roads from OpenStreetMap via OSMnx (needs internet on first
              load; graphs are cached to data/osm_cache/)
"""
from __future__ import annotations

import math
import random
import re
from collections import OrderedDict
from pathlib import Path

import networkx as nx

M_PER_DEG_LAT = 111_000.0
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "osm_cache"

# key -> label, centre (lat, lon), radius in metres.
CITIES = {
    "grid": {"label": "Synthetic grid (instant)", "center": (37.7749, -122.4194)},
    "san_francisco": {"label": "San Francisco - Downtown / SoMa", "center": (37.7870, -122.4010), "dist": 1600},
    "las_vegas": {"label": "Las Vegas - Strip", "center": (36.1147, -115.1728), "dist": 2000},
    "austin": {"label": "Austin - Downtown", "center": (30.2672, -97.7431), "dist": 1600},
    "miami": {"label": "Miami - Brickell", "center": (25.7617, -80.1918), "dist": 1600},
    "los_angeles": {"label": "Los Angeles - Downtown", "center": (34.0407, -118.2468), "dist": 1600},
}

# kph used when a road has no usable maxspeed tag
HWY_KPH = {
    "motorway": 90, "motorway_link": 55, "trunk": 60, "trunk_link": 45, "primary": 45, "primary_link": 35,
    "secondary": 40, "secondary_link": 32, "tertiary": 35, "tertiary_link": 30, "residential": 28,
    "living_street": 15, "service": 18, "unclassified": 30,
}
DEFAULT_KPH = 30.0


class City:
    def __init__(self, g: nx.Graph, name: str, center: tuple, sigma_m: float = 700.0, seed: int = 7):
        self.g, self.name, self.center = g, name, center
        self.nodes = list(g.nodes)
        self._rev = g.reverse(copy=False) if g.is_directed() else g
        self._to: OrderedDict = OrderedDict()
        self._near: OrderedDict = OrderedDict()
        self._path: dict = {}
        self._nbr = None
        self.w = zone_weights(g, sigma_m, seed)
        self.depot = min(self.nodes, key=lambda n: g.nodes[n]["x"] ** 2 + g.nodes[n]["y"] ** 2)

    # ---- travel-time queries (seconds) ----
    def to(self, target) -> dict:
        """Travel time from every node to `target`."""
        d = self._to.get(target)
        if d is None:
            d = nx.single_source_dijkstra_path_length(self._rev, target, weight="time")
            self._to[target] = d
            if len(self._to) > 500:
                self._to.popitem(last=False)
        else:
            self._to.move_to_end(target)
        return d

    def tt(self, a, b) -> float:
        return self.to(b).get(a, math.inf)

    def near(self, src, cutoff: float) -> dict:
        """Nodes reachable from `src` within `cutoff` seconds -> time."""
        key = (src, cutoff)
        d = self._near.get(key)
        if d is None:
            d = nx.single_source_dijkstra_path_length(self.g, src, cutoff=cutoff, weight="time")
            self._near[key] = d
            if len(self._near) > 6000:
                self._near.popitem(last=False)
        return d

    def neighborhoods(self, cutoff: float = 150.0) -> dict:
        if self._nbr is None:
            self._nbr = {k: list(self.near(k, cutoff)) for k in self.nodes}
        return self._nbr

    def path(self, a, b) -> list:
        key = (a, b)
        p = self._path.get(key)
        if p is None:
            if len(self._path) > 50_000:
                self._path.clear()
            p = self._path[key] = nx.shortest_path(self.g, a, b, weight="time")
        return p

    def straight_m(self, a, b) -> float:
        na, nb = self.g.nodes[a], self.g.nodes[b]
        return math.hypot(na["x"] - nb["x"], na["y"] - nb["y"])

    def geojson(self) -> dict:
        feats, seen = [], set()
        for a, b, d in self.g.edges(data=True):
            k = frozenset((a, b))
            if k in seen:
                continue
            seen.add(k)
            na, nb = self.g.nodes[a], self.g.nodes[b]
            fast = d["length"] / max(d["time"], 1e-6) > 10.0  # > 36 kph
            feats.append({"type": "Feature", "properties": {"fast": fast},
                          "geometry": {"type": "LineString",
                                       "coordinates": [[na["lon"], na["lat"]], [nb["lon"], nb["lat"]]]}})
        return {"type": "FeatureCollection", "features": feats}

    def info(self) -> dict:
        return {"name": self.name, "nodes": self.g.number_of_nodes(), "edges": self.g.number_of_edges(),
                "center": self.center}


def zone_weights(g: nx.Graph, sigma_m: float = 700.0, seed: int = 7) -> dict:
    """Static demand weights: a hotspot at the centre plus a secondary one."""
    rng = random.Random(seed)
    nodes = list(g.nodes)
    c0 = min(nodes, key=lambda n: g.nodes[n]["x"] ** 2 + g.nodes[n]["y"] ** 2)
    hot = [c0, rng.choice(nodes)]
    w = {}
    for n in nodes:
        a = g.nodes[n]
        s = 0.2
        for i, h in enumerate(hot):
            hh = g.nodes[h]
            d = math.hypot(a["x"] - hh["x"], a["y"] - hh["y"])
            s += (1.0 if i == 0 else 0.6) * math.exp(-((d / sigma_m) ** 2))
        w[n] = s
    return w


# --------------------------------------------------------------------------- synthetic grid
def build_grid(rows: int = 14, cols: int = 14, block_m: float = 220.0, seed: int = 7) -> City:
    center = CITIES["grid"]["center"]
    rng = random.Random(seed)
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(center[0]))
    g = nx.Graph()
    for r in range(rows):
        for c in range(cols):
            jx, jy = rng.uniform(-25, 25), rng.uniform(-25, 25)
            y = (r - rows / 2) * block_m + jy
            x = (c - cols / 2) * block_m + jx
            g.add_node((r, c), lat=center[0] + y / M_PER_DEG_LAT, lon=center[1] + x / m_per_deg_lon, x=x, y=y)
    for r in range(rows):
        for c in range(cols):
            for dr, dc in ((0, 1), (1, 0)):
                nr, nc = r + dr, c + dc
                if nr < rows and nc < cols:
                    if rng.random() < 0.06 and 0 < r < rows - 1 and 0 < c < cols - 1:
                        continue
                    a, b = g.nodes[(r, c)], g.nodes[(nr, nc)]
                    length = math.hypot(a["x"] - b["x"], a["y"] - b["y"])
                    arterial = (r % 4 == 0 and dr == 0) or (c % 4 == 0 and dc == 0)
                    g.add_edge((r, c), (nr, nc), length=length, time=length / (13.0 if arterial else 8.0))
    comp = max(nx.connected_components(g), key=len)
    return City(g.subgraph(comp).copy(), "Synthetic grid", center, sigma_m=600.0)


# --------------------------------------------------------------------------- OpenStreetMap
def _parse_kph(v) -> float | None:
    if isinstance(v, (list, tuple)):
        vals = [_parse_kph(x) for x in v]
        vals = [x for x in vals if x]
        return min(vals) if vals else None
    if v is None:
        return None
    m = re.match(r"\s*(\d+(?:\.\d+)?)\s*(mph|km/h|kph)?", str(v))
    if not m:
        return None
    n = float(m.group(1))
    return n * 1.609344 if (m.group(2) or "").lower() == "mph" else n


def _edge_kph(data: dict) -> float:
    kph = _parse_kph(data.get("maxspeed"))
    if kph:
        return max(8.0, min(kph, 110.0)) * 0.75  # real-world average is below the limit
    hw = data.get("highway")
    hw = hw[0] if isinstance(hw, (list, tuple)) and hw else hw
    return HWY_KPH.get(hw, DEFAULT_KPH) * 0.75


def graph_from_osmnx(G, center: tuple, name: str, sigma_m: float = 900.0) -> City:
    """Convert an OSMnx MultiDiGraph into the simple DiGraph the simulator uses."""
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(center[0]))
    d = nx.DiGraph()
    for u, v, data in G.edges(data=True):
        if u == v:
            continue
        length = float(data.get("length", 0.0)) or 1.0
        t = length / (_edge_kph(data) / 3.6)
        if d.has_edge(u, v) and d[u][v]["time"] <= t:  # keep fastest of parallel edges
            continue
        d.add_edge(u, v, length=length, time=t)
    comp = max(nx.strongly_connected_components(d), key=len)  # every node reachable from every other
    d = d.subgraph(comp).copy()
    for n in d.nodes:
        lat, lon = float(G.nodes[n]["y"]), float(G.nodes[n]["x"])
        d.nodes[n].update(lat=lat, lon=lon, x=(lon - center[1]) * m_per_deg_lon, y=(lat - center[0]) * M_PER_DEG_LAT)
    return City(d, name, center, sigma_m=sigma_m)


def load_osm(key: str, dist: int | None = None) -> City:
    spec = CITIES[key]
    dist = int(dist or spec["dist"])
    try:
        import osmnx as ox
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("OSMnx is required for real cities: pip install osmnx") from e
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    f = CACHE_DIR / f"{key}_{dist}.graphml"
    if f.exists():
        G = ox.load_graphml(f)
    else:
        G = ox.graph_from_point(spec["center"], dist=dist, network_type="drive", simplify=True)
        ox.save_graphml(G, f)
    return graph_from_osmnx(G, spec["center"], spec["label"])


_cache: dict[str, City] = {}


def get_city(key: str = "grid") -> City:
    if key not in CITIES:
        raise KeyError(f"unknown city {key!r}")
    if key not in _cache:
        _cache[key] = build_grid() if key == "grid" else load_osm(key)
    return _cache[key]
