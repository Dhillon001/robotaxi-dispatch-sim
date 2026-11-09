# 🚕 Robotaxi Dispatch Simulator

**A live, interactive simulator of an autonomous ride-hailing fleet, built to answer one question: *how should a robotaxi fleet dispatch, charge and maintain its cars?***

Run a fleet of robotaxis on a real city map (San Francisco, Las Vegas, Austin, Miami, Los Angeles), watch every car drive in 3D, then compare dispatch and maintenance strategies on wait time, utilization, breakdowns and battery health.

<p align="center">
  <img src="docs/images/sf-3d-close.jpg" alt="Robotaxi fleet driving through 3D downtown San Francisco, street map view" width="100%">
</p>

![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![MapLibre](https://img.shields.io/badge/MapLibre%20GL-396CB2)
![OpenStreetMap](https://img.shields.io/badge/data-OpenStreetMap-7EBC6F?logo=openstreetmap&logoColor=white)
![Tests](https://img.shields.io/badge/tests-14%20passing-brightgreen)
![License](https://img.shields.io/badge/license-MIT-blue)


---

## Highlights

| | |
|---|---|
| 🗺️ **Real cities** | Road networks from OpenStreetMap for 5 US cities, plus an instant offline grid. Add your own city with one line of config. |
| 🧭 **Cinematic map** | 3D tilted view with buildings, satellite toggle, orbiting camera, light and dark themes. Cars glide smoothly at 60 fps and show glowing route lines to their pickup, dropoff or charger. |
| 🧠 **Three dispatch strategies** | Greedy nearest-car, batched optimal assignment (Hungarian algorithm) and demand-aware repositioning. |
| 🔧 **Reliability model** | Each car wears out and fails on a Weibull curve. A failure strands the rider. Compare reactive repair with predictive maintenance. |
| 🔋 **Battery and charging** | Cars drain as they drive, route to the least-busy charger, queue for plugs and unplug at 90%. Every car's battery is visible. |
| 📊 **Policy comparison** | One click runs all six policy combinations headless across several random seeds and highlights the winner. |
| ⚡ **Fast** | Lazy, cached shortest-path routing keeps city-scale road graphs (thousands of intersections) responsive. |
| ✅ **Tested** | 14 automated tests cover the simulation, the OpenStreetMap adapter (offline, against real OSMnx output) and the API. |

---

## Screenshots

<table>
  <tr>
    <td colspan="2"><img src="docs/images/sf-3d-close.jpg" alt="San Francisco 3D street map with robotaxis and charging stations"><br><sub><b>San Francisco, 3D street map.</b> Tilted side angle over real OpenStreetMap roads and extruded buildings, with robotaxis and charger markers.</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/topdown-light.png" alt="Top-down light theme"><br><sub><b>Top-down, light theme.</b> Cars are colored by state; lines show where each car is heading.</sub></td>
    <td width="50%"><img src="docs/images/hero-light.png" alt="3D view, light theme"><br><sub><b>3D view, light theme.</b> Tilt, rotate and orbit the camera.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/images/sidebar.png" alt="Charging stations and per-car battery list"><br><sub><b>Charging stations and per-car batteries.</b> Plug usage per charger, every car's battery sorted lowest first.</sub></td>
    <td><img src="docs/images/policy-comparison.png" alt="Policy comparison table"><br><sub><b>Policy comparison.</b> Six policy combinations, averaged over seeds, best one highlighted.</sub></td>
  </tr>
</table>

<p align="center"><img src="docs/images/fleet-bar.png" alt="Fleet dashboard bar" width="100%"><br><sub><b>Fleet bar.</b> Total robotaxis, a live breakdown by state, charging load, average battery, riders waiting and utilization.</sub></p>

**Car colors:** 🟢 with passenger · 🟡 heading to rider · 🔵 available · 🟣 repositioning · 🩵 going to charge · 🟩 charging · ⚪ maintenance · 🔴 broken down · 🟠 waiting rider (pulsing).

---

## How it works

```mermaid
flowchart LR
  B["Browser<br/>map, controls, dashboard"] -->|"asks for the latest state<br/>every ~0.2 s"| S["FastAPI server"]
  S --> E["Simulation engine<br/>(Python)"]
  E --> G["City road graph<br/>(OpenStreetMap)"]
  S -->|"JSON snapshot"| B
```

The simulation runs in Python on the server. The browser just asks for the current state a few times a second and animates the cars smoothly between updates.

**Every 2 simulated seconds, the engine does four things:**

1. **New riders appear.** Requests arrive randomly (more at rush hour) at places weighted toward the city center.
2. **Dispatch.** Waiting riders are matched to free cars. *Nearest* gives each rider the closest car. *Batch* looks at all riders and cars together and finds the assignment with the lowest total pickup time (the Hungarian algorithm), which is the version that wins.
3. **Cars move.** Each car follows the shortest path on the road graph (Dijkstra), picks up the rider, and drops them off.
4. **Wear and battery.** Cars drain battery as they drive and head to a charger below 30%. They also wear out and can break down, which strands the rider. *Predictive maintenance* sends worn cars for service before that happens.

```mermaid
flowchart LR
  R["Rider requests a ride"] --> D["Dispatch picks a car"] --> P["Car drives to pickup"] --> T["Drives rider to destination"] --> F["Free again<br/>(or goes to charge / service)"]
  F --> D
```

**Why these choices:** Python for the engine because SciPy and NetworkX do the hard parts (optimal matching, shortest paths). Polling instead of WebSockets because it is the simplest thing that works. Shortest paths are computed lazily and cached, because precomputing every pair does not scale to a real city. MapLibre with OpenFreeMap because it needs no API key.

---

## Tech stack

| Layer | Technology | Why |
|---|---|---|
| Simulation | **Python**, **NumPy**, **SciPy** | Vectorized math, `linear_sum_assignment` for optimal dispatch |
| Road graph and routing | **NetworkX**, **OSMnx** | Dijkstra shortest paths; real road networks from OpenStreetMap |
| API server | **FastAPI** + **Uvicorn** | Small, typed, auto-validated REST API that also serves the frontend |
| Frontend | Vanilla **JavaScript**, HTML, CSS | No build step: clone and run. Library is vendored, so it works offline |
| Map rendering | **MapLibre GL JS** (WebGL) | Smooth vector maps, 3D buildings, custom GPU-drawn layers |
| Basemaps | **OpenFreeMap** (vector, 3D buildings), **Esri World Imagery** (satellite) | Free, no API key |
| Tests | **pytest**, FastAPI `TestClient` | Simulation, OSM adapter and API are covered |
| Screenshots | **Playwright** | `scripts/screenshots.py` regenerates this page's images |

---

## API reference

Base URL: `http://localhost:8000`. All responses are JSON. Interactive docs are generated by FastAPI at **`/docs`**.

| Method | Path | Parameters | Returns |
|---|---|---|---|
| `GET` | `/` | | The web app |
| `GET` | `/api/config` | | Available policies, cities, default city, current config |
| `POST` | `/api/reset` | `city`, `dispatch`, `maintenance`, `n_vehicles`, `demand_per_min`, `seed` | Creates a new simulation. Returns city info. `404` unknown city, `502` roads failed to load |
| `GET` | `/api/graph` | | The active city's road network as GeoJSON |
| `POST` | `/api/step` | `seconds` (default 10, max 300) | Advances the simulation, returns a snapshot |
| `GET` | `/api/state` | | The current snapshot without advancing |
| `GET` | `/api/compare` | `hours` (max 8), `n_vehicles`, `demand_per_min` | Headless comparison of all 6 policy combinations over 3 seeds |

**Example**

```bash
# start a fresh San Francisco simulation with batch dispatch and predictive maintenance
curl -X POST "localhost:8000/api/reset?city=san_francisco&dispatch=batch&maintenance=predictive&n_vehicles=40"

# simulate 2 minutes and read the result
curl -X POST "localhost:8000/api/step?seconds=120"
```

**Snapshot shape** (`/api/step`, `/api/state`), trimmed:

```jsonc
{
  "t": 120.0,                         // simulated seconds since 07:00
  "vehicles": [{
    "id": 0, "lat": 37.7688, "lon": -122.4179, "heading": 91.4,   // degrees, 0 = north
    "state": "to_pickup",             // idle | to_pickup | riding | reposition | to_charger | charging | service | down
    "soc": 68,                        // battery %
    "plugged": false, "station": null,
    "km": 0.8, "health": 0.01,        // km since service, wear ratio
    "route": [[-122.4179, 37.7688], [-122.4170, 37.7687]],  // upcoming path as [lon, lat]
    "eta_s": 95, "dist_m": 640        // time and distance left on the current route
  }],
  "pending": [{ "id": 12, "lat": 37.77, "lon": -122.41, "wait": 45 }],     // riders waiting
  "stations": [{ "id": 0, "name": "Charger A", "lat": 37.7748, "lon": -122.4191, "plugs": 3, "in_use": 1, "queue": 0 }],
  "metrics": {
    "served": 218, "abandoned": 0, "pending": 0,
    "avg_wait_s": 59.0, "p90_wait_s": 140.0, "utilization": 0.39, "deadhead_pct": 31.0,
    "failures": 2, "planned_services": 0, "stranded_riders": 2,
    "charging": 1, "queued": 0, "to_charger": 0, "plugs_total": 12,
    "avg_soc": 61.0, "min_soc": 30.0, "charge_sessions": 4
  },
  "events": ["t=7220 car 6 plugged in at Charger D (31%)"]
}
```

You can also pre-select a city with a URL: `http://localhost:8000/?city=austin`.

---

## Results

Synthetic grid, 30 robotaxis, 3.4 requests/min, 4 simulated hours (07:00 to 11:00, including the morning peak), averaged over 5 random seeds. Reproduce with `GET /api/compare`, or:

```python
from sim.engine import compare
for row in compare(hours=4, seeds=(1, 2, 3, 4, 5)): print(row)
```

| Dispatch | Maintenance | Avg wait | P90 wait | Deadhead | Breakdowns | Riders who gave up |
|---|---|---:|---:|---:|---:|---:|
| nearest | reactive | 318 s | 708 s | 42.8% | 21.4 | 35.8 |
| nearest | predictive | 328 s | 725 s | 43.6% | 17.8 | 47.2 |
| **batch** | reactive | **122 s** | **261 s** | **32.4%** | 16.6 | **0.0** |
| batch | predictive | 126 s | 261 s | 33.8% | **10.4** | 0.0 |
| predictive | reactive | 122 s | 261 s | 32.4% | 16.6 | 0.0 |
| predictive | predictive | 127 s | 265 s | 33.6% | 10.2 | 0.0 |

**What the numbers say**

1. **Optimal batching is the big win.** Compared with greedy nearest-car dispatch, `batch` cuts average wait by about 62% (318 s to 122 s), cuts the 90th-percentile wait from 708 s to 261 s, reduces wasted driving by about 10 points, and eliminates riders giving up entirely.
2. **Predictive maintenance cuts breakdowns by about 37%** (16.6 to 10.4 under `batch`), which means fewer stranded riders. The price is a few seconds of extra wait (122 s to 126 s), because cars spend time in planned service. Whether that trade is worth it depends on how costly a stranded rider is.
3. **Demand-aware repositioning shows no benefit yet.** `predictive` dispatch matches `batch` almost exactly, because the simple heuristic rarely moves a car in the default scenario. That is an honest negative result and the first roadmap item below.
4. **Charging has a real fleet cost.** With a limited number of plugs, cars spend time charging and queuing, which is part of why waits are higher than a fleet with unlimited range would see (about 72 s average wait for `batch` + `reactive` with the battery model switched off, versus 122 s with it).

---

## Getting started

```bash
git clone https://github.com/Dhillon001/robotaxi-dispatch-sim
cd robotaxi-dispatch-sim
python3 -m pip install -r requirements.txt
python3 -m uvicorn app.main:app --port 8000
```

Open **http://localhost:8000**. Keep the terminal window open while you use the app.

- **Real cities** (San Francisco is the default) download their roads from OpenStreetMap the first time you load them, which takes 10 to 30 seconds, and then load instantly from the `data/osm_cache/` folder. If a city can't be loaded, the app falls back to the synthetic grid and says why.
- **Run the tests:** `python3 -m pytest -q`
- **Regenerate the screenshots:** `pip install playwright && playwright install chromium`, then with the server running, `python3 scripts/screenshots.py --city san_francisco`

**Controls**

| Control | What it does |
|---|---|
| City, dispatch, maintenance, vehicles, demand | Choose the scenario, then **Reset & apply** (picking a city applies it immediately) |
| Pause / speed (10x, 30x, 90x) | Control simulation speed |
| 3D view, Orbit | Camera modes |
| Car number box (or click a car) | Chase camera: rides along with that car, with a turn-by-turn card. Esc to stop |
| Satellite | Switch the real-city map to aerial imagery |
| Sun / moon button | Light and dark themes |
| Run headless comparison | Compare all policy combinations |
| Hover a car, click a charger or a car in the list | Inspect or fly to it |

---

## Configuration

Defaults live in `Config` (`sim/engine.py`). The most useful knobs are also exposed in the UI and API.

| Setting | Default | Meaning |
|---|---:|---|
| `n_vehicles` | 30 | Fleet size |
| `demand_per_min` | 3.4 | Average ride requests per minute (scaled by commute-hour peaks) |
| `dispatch` | `nearest` | `nearest`, `batch` or `predictive` |
| `maintenance` | `reactive` | `reactive` or `predictive` |
| `weibull_shape`, `weibull_scale_km` | 2.2, 90 | Failure curve (wear-out behavior) |
| `repair_mean_s` | 900 | Average repair time |
| `service_threshold` | 0.6 | Predictive maintenance triggers at this wear estimate |
| `battery_range_km` | 90 | Range on a full battery |
| `charge_below`, `charge_to` | 30, 90 | Charge trigger and target (%) |
| `charge_minutes` | 45 | Time to charge 0 to 100% |
| `n_stations`, `plugs_per_station` | auto | Charger count and plugs (0 = automatic) |
| `seed` | 1 | Random seed. Same seed gives identical runs |

To add a city, add an entry to `CITIES` in `sim/city.py` with a center latitude and longitude and a radius in meters.

---

## Project structure

```
robotaxi-dispatch-sim/
├── app/
│   ├── main.py                 FastAPI app: REST endpoints and static hosting
│   └── static/
│       ├── index.html          The whole frontend (UI, map layers, animation)
│       └── vendor/             MapLibre GL JS, vendored so the app works offline
├── sim/
│   ├── city.py                 Road graphs: synthetic grid, OSMnx adapter, routing caches
│   └── engine.py               Simulation: demand, dispatch, reliability, battery, metrics
├── tests/
│   ├── test_sim.py             Engine behavior, determinism, charging, failures
│   ├── test_osm.py             OSMnx adapter, tested offline against a hand-made .osm file
│   └── test_api.py             API endpoints
├── scripts/screenshots.py      Regenerates the images in docs/images
├── docs/images/                Screenshots used in this README
├── data/osm_cache/             Downloaded road networks (git-ignored)
└── requirements.txt
```

---

## Limitations and roadmap

**Known limitations**

- Demand is synthetic: a time-of-day curve with two hotspots, not real trip data.
- Travel times come from speed limits (at 75%), with no live traffic, signals or turn penalties.
- Roads are drawn as straight segments between intersections, so cars cut corners slightly on curvy streets.
- One shared simulation per server process (fine for a demo, not for many simultaneous viewers).
- The `predictive` dispatch repositioning heuristic currently has no measurable effect.

**Roadmap**

- [x] Chase camera: pick any car by number and follow it turn by turn
- [ ] Fix and tune the repositioning heuristic, then try a learned demand forecast
- [ ] Split-screen race: two strategies on identical demand with a live scoreboard
- [ ] Click-to-place charging stations and a what-if analysis of charger count
- [ ] Real demand data and traffic-aware travel times
- [ ] Component-level telemetry (battery health, brakes, sensors) feeding a failure-prediction model
- [ ] Curved road geometry and one-way arrows in the animation
- [ ] Deployment with a bundled city graph, plus CI

---

## License

MIT. See [LICENSE](LICENSE). Map data © OpenStreetMap contributors. Basemap tiles from OpenFreeMap; satellite imagery © Esri, Maxar, Earthstar Geographics.
