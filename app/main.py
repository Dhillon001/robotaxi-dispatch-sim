from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from sim.city import CITIES, get_city
from sim.engine import DISPATCH, MAINT, Config, Sim, compare

STATIC = Path(__file__).parent / "static"
DEFAULT_CITY = "san_francisco"
app = FastAPI(title="Robotaxi Dispatch Simulator")
state: dict = {"sim": Sim(Config())}


@app.get("/api/config")
def get_config():
    return {"dispatch": DISPATCH, "maintenance": MAINT, "current": state["sim"].cfg.__dict__,
            "cities": [{"key": k, "label": v["label"]} for k, v in CITIES.items()],
            "default_city": DEFAULT_CITY}


@app.post("/api/reset")
def reset(dispatch: str = "nearest", maintenance: str = "reactive", n_vehicles: int = 30,
          demand_per_min: float = 3.4, seed: int = 1, city: str = DEFAULT_CITY):
    try:
        c = get_city(city)  # first use of a real city downloads OSM roads (cached afterwards)
    except KeyError:
        raise HTTPException(404, f"Unknown city '{city}'")
    except Exception as e:
        raise HTTPException(502, f"Could not load roads for '{city}': {e}. Real cities need internet on first load.")
    state["sim"] = Sim(Config(dispatch=dispatch, maintenance=maintenance, n_vehicles=n_vehicles,
                              demand_per_min=demand_per_min, seed=seed), c)
    return {"ok": True, "city": c.info()}


@app.get("/api/graph")
def graph():
    return state["sim"].graph_geojson()


@app.post("/api/step")
def step(seconds: float = 10.0):
    state["sim"].run(min(seconds, 300))
    return state["sim"].snapshot()


@app.get("/api/state")
def get_state():
    return state["sim"].snapshot()


@app.get("/api/compare")
def run_compare(hours: float = 3.0, n_vehicles: int = 30, demand_per_min: float = 3.4):
    return compare(hours=min(hours, 8), seeds=(1, 2, 3), city=state["sim"].city,
                   n_vehicles=n_vehicles, demand_per_min=demand_per_min)


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


app.mount("/static", StaticFiles(directory=STATIC), name="static")
