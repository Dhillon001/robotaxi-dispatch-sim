"""Regenerate the README screenshots from a running server.

    uvicorn app.main:app --port 8000        # in one terminal
    python scripts/screenshots.py --city san_francisco   # in another (needs: pip install playwright && playwright install chromium)

Real cities need internet (roads + map tiles), so run this on your own machine for SF shots.
"""
import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

ARGS = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--city", default="grid", help="grid | san_francisco | las_vegas | austin | miami | los_angeles")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "docs" / "images"))
    ap.add_argument("--sim-minutes", type=int, default=75, help="fast-forward the simulation before shooting")
    ap.add_argument("--load-wait", type=int, default=60, help="seconds to wait for a real city to download")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        b = p.chromium.launch(args=ARGS)
        pg = b.new_page(viewport={"width": 1500, "height": 940})
        pg.goto(a.url); pg.evaluate("localStorage.setItem('theme','dark'); localStorage.setItem('satellite','0')")
        pg.goto(f"{a.url}/?city={a.city}")
        pg.wait_for_function("!document.getElementById('reset').disabled && disp.size > 0", timeout=a.load_wait * 1000)
        pg.wait_for_timeout(3500)
        pg.click("#play")  # pause the live loop, then fast-forward deterministically
        pg.evaluate(f"""async () => {{
          for (let i = 0; i < {a.sim_minutes * 60 // 300}; i++) await fetch('/api/step?seconds=300', {{method: 'POST'}});
          ingest(await (await fetch('/api/state')).json()); renderFleet(last, true);
        }}""")
        pg.wait_for_timeout(2500)

        pg.evaluate("if (!tilt3d) set3d(true, false)"); pg.wait_for_timeout(1500)  # real cities open tilted; tilt the grid too
        pg.screenshot(path=str(out / "hero-dark-3d.png"))
        pg.locator("#strip").screenshot(path=str(out / "fleet-bar.png"))
        pg.locator("aside").screenshot(path=str(out / "sidebar.png"))
        pg.click("#theme"); pg.wait_for_timeout(2500)
        pg.screenshot(path=str(out / "hero-light.png"))
        pg.click("#b3d"); pg.wait_for_timeout(1800)                             # flatten for a top-down view
        pg.screenshot(path=str(out / "topdown-light.png"))
        pg.click("#cmp"); pg.wait_for_selector("#cmpOut table", timeout=180000)
        pg.locator("#cmpOut").scroll_into_view_if_needed()
        pg.locator("#cmpOut").screenshot(path=str(out / "policy-comparison.png"))
        b.close()
    print("wrote", sorted(f.name for f in out.glob("*.png")))


if __name__ == "__main__":
    main()
