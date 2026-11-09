"""Exercises the OSMnx adapter offline using a tiny hand-made .osm file."""
import pytest

ox = pytest.importorskip("osmnx")

from sim.city import City, graph_from_osmnx
from sim.engine import Config, Sim

N = 7
LAT0, LON0, STEP = 37.7870, -122.4010, 0.0015


def _osm_xml() -> str:
    out = ['<?xml version="1.0" encoding="UTF-8"?><osm version="0.6">']
    for r in range(N):
        for c in range(N):
            out.append(f'<node id="{r * N + c + 1}" lat="{LAT0 + r * STEP:.6f}" lon="{LON0 + c * STEP * 1.25:.6f}"/>')
    wid = 1000
    for r in range(N):  # east-west streets: even rows are two-way 25 mph, odd rows one-way
        wid += 1
        nds = "".join(f'<nd ref="{r * N + c + 1}"/>' for c in range(N))
        tags = '<tag k="highway" v="secondary"/><tag k="maxspeed" v="25 mph"/>' if r % 2 == 0 else \
               '<tag k="highway" v="residential"/><tag k="oneway" v="yes"/>'
        out.append(f'<way id="{wid}">{nds}{tags}</way>')
    for c in range(N):  # north-south streets, two-way
        wid += 1
        nds = "".join(f'<nd ref="{r * N + c + 1}"/>' for r in range(N))
        out.append(f'<way id="{wid}">{nds}<tag k="highway" v="tertiary"/></way>')
    out.append("</osm>")
    return "".join(out)


@pytest.fixture()
def city(tmp_path):
    f = tmp_path / "t.osm"
    f.write_text(_osm_xml())
    G = ox.graph_from_xml(f, simplify=True)
    return graph_from_osmnx(G, (LAT0 + 3 * STEP, LON0 + 3 * STEP * 1.25), "Test")


def test_adapter_shape(city):
    assert isinstance(city, City)
    g = city.g
    assert g.is_directed() and g.number_of_nodes() >= 20
    n = next(iter(g.nodes))
    assert {"lat", "lon", "x", "y"} <= set(g.nodes[n])
    for _, _, d in g.edges(data=True):
        assert d["length"] > 0 and d["time"] > 0


def test_strongly_connected_and_routable(city):
    import networkx as nx
    assert nx.is_strongly_connected(city.g)
    a, b = city.nodes[0], city.nodes[-1]
    assert city.tt(a, b) < float("inf")
    p = city.path(a, b)
    assert p[0] == a and p[-1] == b


def test_geojson_dedupes_two_way(city):
    gj = city.geojson()
    assert 0 < len(gj["features"]) <= city.g.number_of_edges()


def test_sim_runs_on_osm_city(city):
    for d in ("nearest", "batch", "predictive"):
        s = Sim(Config(dispatch=d, n_vehicles=8, demand_per_min=2.0), city).run(1200)
        assert s.metrics()["served"] > 0
        s.snapshot()
