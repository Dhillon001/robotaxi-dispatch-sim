"""Regenerate the README screenshots from a running server.

    uvicorn app.main:app --port 8000                      # terminal 1
    python scripts/screenshots.py                         # terminal 2 (San Francisco, 3D street map)
    python scripts/screenshots.py --extra-cities las_vegas austin miami los_angeles

Needs: pip install playwright && playwright install chromium

Real cities need internet (OSM roads on first load + OpenFreeMap vector tiles), so run this
on your own machine. Every shot is the 3D street map with satellite OFF, tilted ~60 deg and rotated so buildings
show from the side, in a close and a far view.
Add --software-gl only on a headless box without a GPU (slower, lower fidelity).
"""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

SOFT_GL = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
READY = "!document.getElementById('reset').disabled && disp.size > 0"
TILES = "map.loaded() && map.areTilesLoaded()"


def load_city(pg, url, city, wait_s, theme="dark"):
    """Open a city with satellite off and 3D on, wait for roads, cars and map tiles."""
    pg.goto(url)
    pg.evaluate(f"localStorage.setItem('theme','{theme}'); localStorage.setItem('satellite','0')")
    pg.goto(f"{url}/?city={city}")
    pg.wait_for_function(READY, timeout=wait_s * 1000)
    pg.evaluate("if (typeof satellite !== 'undefined' && satellite) document.getElementById('bsat')?.click()")
    pg.evaluate("if (!tilt3d) set3d(true, false)")
    pg.wait_for_function(TILES, timeout=wait_s * 1000)
    pg.wait_for_timeout(3000)


# Side-angle 3D camera: tilted + rotated so the extruded buildings show (street map, no satellite).
CAMS = {"close": dict(zoom=15.7, pitch=62, bearing=-20), "far": dict(zoom=14.3, pitch=60, bearing=-20)}


def cam(pg, name):
    c = CAMS[name]
    pg.evaluate(f"""() => {{ const m = map.getCenter(); set3dQuiet(true);
      map.jumpTo({{center: [m.lng, m.lat], zoom: {c['zoom']}, pitch: {c['pitch']}, bearing: {c['bearing']}}}); }}""")
    pg.wait_for_timeout(1500)
    pg.wait_for_function(TILES, timeout=90000)
    pg.wait_for_timeout(1500)


def fast_forward(pg, minutes):
    pg.click("#play")  # pause the live loop, then fast-forward deterministically
    pg.evaluate(f"""async () => {{
      for (let i = 0; i < {minutes * 60 // 300}; i++) await fetch('/api/step?seconds=300', {{method: 'POST'}});
      ingest(await (await fetch('/api/state')).json()); renderFleet(last, true);
    }}""")
    pg.wait_for_timeout(2500)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--city", default="san_francisco", help="grid | san_francisco | las_vegas | austin | miami | los_angeles")
    ap.add_argument("--extra-cities", nargs="*", default=[], help="also write city-<key>.png (3D, no satellite)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "images"))
    ap.add_argument("--sim-minutes", type=int, default=75, help="fast-forward the simulation before shooting")
    ap.add_argument("--load-wait", type=int, default=90, help="seconds to wait for roads + tiles")
    ap.add_argument("--software-gl", action="store_true", help="force SwiftShader (no GPU)")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        b = p.chromium.launch(args=SOFT_GL if a.software_gl else [])
        pg = b.new_page(viewport={"width": 1500, "height": 940}, device_scale_factor=2)

        load_city(pg, a.url, a.city, a.load_wait)
        fast_forward(pg, a.sim_minutes)
        pg.wait_for_function(TILES, timeout=a.load_wait * 1000)
        cam(pg, "close")
        pg.screenshot(path=str(out / "hero-dark-3d.png"))
        cam(pg, "far")
        pg.screenshot(path=str(out / "hero-dark-3d-far.png"))
        cam(pg, "close")
        pg.locator("#strip").screenshot(path=str(out / "fleet-bar.png"))
        pg.locator("aside").screenshot(path=str(out / "sidebar.png"))
        pg.click("#theme"); pg.wait_for_timeout(3000)
        pg.wait_for_timeout(1500)
        pg.screenshot(path=str(out / "hero-light.png"))
        cam(pg, "far")
        pg.screenshot(path=str(out / "hero-light-far.png"))
        pg.click("#b3d"); pg.wait_for_timeout(2000)                             # flatten for a top-down view
        pg.screenshot(path=str(out / "topdown-light.png"))
        pg.click("#cmp"); pg.wait_for_selector("#cmpOut table", timeout=180000)
        pg.locator("#cmpOut").scroll_into_view_if_needed()
        pg.locator("#cmpOut").screenshot(path=str(out / "policy-comparison.png"))

        for key in a.extra_cities:
            load_city(pg, a.url, key, a.load_wait)
            fast_forward(pg, 45)
            pg.wait_for_function(TILES, timeout=a.load_wait * 1000)
            cam(pg, "close")
            pg.screenshot(path=str(out / f"city-{key}.png"))
            cam(pg, "far")
            pg.screenshot(path=str(out / f"city-{key}-far.png"))
        b.close()
    print("wrote", sorted(f.name for f in out.glob("*.png")))


if __name__ == "__main__":
    main()
