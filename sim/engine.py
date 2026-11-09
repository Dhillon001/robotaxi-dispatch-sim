"""Discrete-time robotaxi fleet simulator with reliability coupling.

Dispatch strategies : nearest | batch | predictive
Maintenance policies: reactive | predictive
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

import networkx as nx
import numpy as np
from scipy.optimize import linear_sum_assignment

from .city import City, get_city

DISPATCH = ("nearest", "batch", "predictive")
MAINT = ("reactive", "predictive")

IDLE, TO_PICKUP, RIDING, REPOSITION, SERVICE, DOWN, TO_CHARGER, CHARGING = (
    "idle", "to_pickup", "riding", "reposition", "service", "down", "to_charger", "charging",
)
MAX_WAIT_S = 600.0
BATCH_EVERY_S = 10.0
PLANNED_SERVICE_S = 300.0


@dataclass
class Config:
    n_vehicles: int = 30
    demand_per_min: float = 3.4
    dispatch: str = "nearest"
    maintenance: str = "reactive"
    seed: int = 1
    dt: float = 2.0
    # reliability: failure when km-since-service passes a Weibull draw
    weibull_shape: float = 2.2
    weibull_scale_km: float = 90.0
    repair_mean_s: float = 900.0
    health_noise: float = 0.08
    service_threshold: float = 0.6
    start_hour: float = 7.0
    # battery / charging
    battery_range_km: float = 90.0   # full-charge range
    charge_below: float = 30.0       # idle cars below this % go charge
    charge_to: float = 90.0          # unplug at this %
    charge_minutes: float = 45.0     # 0 -> 100% at a DC fast charger
    start_soc_min: float = 28.0      # starting battery is random in [this, 100]
    n_stations: int = 0              # 0 = auto
    plugs_per_station: int = 0       # 0 = auto


@dataclass
class Vehicle:
    id: int
    node: tuple
    state: str = IDLE
    route: list = field(default_factory=list)  # remaining nodes to visit
    leg_left: float = 0.0  # seconds left on current edge
    leg_total: float = 0.0
    prev: Optional[tuple] = None
    request: Optional["Request"] = None
    km: float = 0.0  # since last service
    fail_at_km: float = 0.0
    timer: float = 0.0  # for SERVICE / DOWN
    odometer_m: float = 0.0
    revenue_m: float = 0.0
    busy_s: float = 0.0
    failures: int = 0
    planned_services: int = 0
    heading: float = 0.0  # degrees, 0 = north, clockwise
    soc: float = 100.0    # battery %
    station: Optional[int] = None
    plugged: bool = False
    charges: int = 0


@dataclass
class Station:
    id: int
    name: str
    node: tuple
    plugs: int
    occupied: list = field(default_factory=list)  # vehicle ids on a plug
    queue: list = field(default_factory=list)     # vehicle ids waiting


@dataclass
class Request:
    id: int
    t: float
    origin: tuple
    dest: tuple
    picked_at: Optional[float] = None
    done_at: Optional[float] = None
    vehicle: Optional[int] = None
    requeued: int = 0


class Sim:
    def __init__(self, cfg: Config | None = None, city: City | None = None):
        self.cfg = cfg or Config()
        assert self.cfg.dispatch in DISPATCH and self.cfg.maintenance in MAINT
        self.rng = random.Random(self.cfg.seed)
        self.np = np.random.default_rng(self.cfg.seed)
        self.city = city or get_city("grid")
        self.g = self.city.g
        self.nodes = self.city.nodes
        self.w = self.city.w
        self._w_list = [self.w[n] for n in self.nodes]
        self.depot = self.city.depot
        self._need: dict | None = None
        self.t = 0.0
        self.next_req = 0
        self.pending: list[Request] = []
        self.done: list[Request] = []
        self.abandoned = 0
        self.charge_sessions = 0
        self.vehicles = [self._new_vehicle(i) for i in range(self.cfg.n_vehicles)]
        self.stations = self._place_stations()
        self._last_batch = -1e9
        self.events: list[str] = []

    # ---------------- helpers ----------------
    def _new_vehicle(self, i: int) -> Vehicle:
        v = Vehicle(id=i, node=self.rng.choice(self.nodes))
        v.fail_at_km = self._draw_failure_km()
        v.soc = self.rng.uniform(self.cfg.start_soc_min, 100.0)
        return v

    # ---------------- charging ----------------
    def _place_stations(self) -> list:
        cfg = self.cfg
        n = cfg.n_stations or max(2, math.ceil(cfg.n_vehicles / 8))
        plugs = cfg.plugs_per_station or math.ceil(0.25 * cfg.n_vehicles / n) + 1
        maxw = max(self.w.values())
        chosen = [self.depot]
        while len(chosen) < n:  # spread out, biased toward where demand is
            chosen.append(max(self.nodes, key=lambda k: min(self.city.straight_m(k, c) for c in chosen) * (0.4 + self.w[k] / maxw)))
        return [Station(i, f"Charger {chr(65 + i % 26)}", node, plugs) for i, node in enumerate(chosen)]

    def _pick_station(self, v: Vehicle) -> Station:
        def score(st: Station) -> float:
            backlog = max(0, len(st.occupied) + len(st.queue) - st.plugs + 1)
            return self._eta(v, st.node) + backlog * 600.0
        return min(self.stations, key=score)

    def _charge_logic(self) -> None:
        for v in self.vehicles:
            if v.state in (IDLE, REPOSITION) and v.request is None and v.soc < self.cfg.charge_below:
                st = self._pick_station(v)
                v.station = st.id
                v.state = TO_CHARGER
                if v.node == st.node and not v.route:
                    self._arrive(v)
                else:
                    self._assign_route(v, st.node)

    def _arrive(self, v: Vehicle) -> None:
        st = self.stations[v.station]
        v.heading = 0.0
        v.state = CHARGING
        if len(st.occupied) < st.plugs:
            st.occupied.append(v.id)
            v.plugged = True
            self.events.append(f"t={int(self.t)} car {v.id} plugged in at {st.name} ({round(v.soc)}%)")
        else:
            st.queue.append(v.id)
            v.plugged = False

    def _release(self, v: Vehicle) -> None:
        st = self.stations[v.station]
        st.occupied.remove(v.id)
        v.plugged, v.station, v.state = False, None, IDLE
        v.charges += 1
        self.charge_sessions += 1
        self.events.append(f"t={int(self.t)} car {v.id} finished charging ({round(v.soc)}%)")
        while st.queue and len(st.occupied) < st.plugs:
            u = self.vehicles[st.queue.pop(0)]
            st.occupied.append(u.id)
            u.plugged = True
            self.events.append(f"t={int(self.t)} car {u.id} plugged in at {st.name} ({round(u.soc)}%)")

    def _draw_failure_km(self) -> float:
        return self.cfg.weibull_scale_km * self.np.weibull(self.cfg.weibull_shape)

    def tt(self, a, b) -> float:
        return self.city.tt(a, b)

    def path(self, a, b) -> list:
        return self.city.path(a, b)

    def sensor_health(self, v: Vehicle) -> float:
        """Noisy 0..1+ health estimate. >1 means 'past typical failure point'."""
        est = v.km / max(self.cfg.weibull_scale_km, 1e-6)
        return est + self.np.normal(0, self.cfg.health_noise)

    def _assign_route(self, v: Vehicle, dest) -> None:
        if v.route and v.leg_total > 0:
            # mid-edge: finish the current edge, then route onward
            nxt = v.route[0]
            v.route = [nxt] + (self.path(nxt, dest)[1:] if nxt != dest else [])
            return
        v.route = list(self.path(v.node, dest)[1:])
        v.leg_left = 0.0
        v.leg_total = 0.0

    def _edge_time(self, a, b) -> float:
        return self.g.edges[a, b]["time"]

    def _edge_len(self, a, b) -> float:
        return self.g.edges[a, b]["length"]

    def position(self, v: Vehicle) -> tuple[float, float]:
        a = self.g.nodes[v.node]
        if v.state == CHARGING and v.station is not None:  # park neatly in a grid around the charger
            st = self.stations[v.station]
            idx = st.occupied.index(v.id) if v.plugged else st.plugs + st.queue.index(v.id)
            return a["lat"] + (idx // 3) * 0.00005, a["lon"] + (idx % 3 - 1) * 0.00006
        if v.route and v.leg_total > 0:
            b = self.g.nodes[v.route[0]]
            f = 1.0 - v.leg_left / v.leg_total
            return a["lat"] + (b["lat"] - a["lat"]) * f, a["lon"] + (b["lon"] - a["lon"]) * f
        return a["lat"], a["lon"]

    # ---------------- demand ----------------
    def demand_multiplier(self) -> float:
        hr = (self.cfg.start_hour + self.t / 3600.0) % 24
        # morning and evening commute peaks
        return 0.6 + 0.8 * math.exp(-((hr - 8.5) ** 2) / 1.2) + 0.7 * math.exp(-((hr - 17.5) ** 2) / 1.5)

    def _spawn_requests(self) -> None:
        lam = self.cfg.demand_per_min / 60.0 * self.cfg.dt * self.demand_multiplier()
        n = self.np.poisson(lam)
        for _ in range(n):
            o = self.rng.choices(self.nodes, weights=self._w_list)[0]
            d = self.rng.choices(self.nodes, weights=self._w_list)[0]
            tries = 0
            while (d == o or self.city.straight_m(o, d) < 350) and tries < 20:
                d = self.rng.choices(self.nodes, weights=self._w_list)[0]
                tries += 1
            if d == o:
                continue
            self.pending.append(Request(self.next_req, self.t, o, d))
            self.next_req += 1

    # ---------------- dispatch ----------------
    def _idle_vehicles(self):
        return [v for v in self.vehicles if v.state in (IDLE, REPOSITION) and v.request is None]

    def _send_to_pickup(self, v: Vehicle, r: Request) -> None:
        v.state = TO_PICKUP
        v.request = r
        r.vehicle = v.id
        if v.node == r.origin and not v.route:
            self._begin_ride(v)
        else:
            self._assign_route(v, r.origin)

    def _begin_ride(self, v: Vehicle) -> None:
        r = v.request
        r.picked_at = self.t
        v.state = RIDING
        self._assign_route(v, r.dest)

    def _dispatch_nearest(self) -> None:
        for r in list(self.pending):
            idle = self._idle_vehicles()
            if not idle:
                return
            v = min(idle, key=lambda x: self._eta(x, r.origin))
            self.pending.remove(r)
            self._send_to_pickup(v, r)

    def _dispatch_batch(self) -> None:
        if self.t - self._last_batch < BATCH_EVERY_S:
            return
        self._last_batch = self.t
        idle = self._idle_vehicles()
        if not idle or not self.pending:
            return
        reqs = self.pending[:]
        cost = np.zeros((len(reqs), len(idle)))
        for i, r in enumerate(reqs):
            for j, v in enumerate(idle):
                # cost: pickup ETA, minus bonus for older requests (fairness)
                cost[i, j] = self._eta(v, r.origin) - 0.5 * (self.t - r.t)
        ri, vj = linear_sum_assignment(cost)
        for i, j in zip(ri, vj):
            self.pending.remove(reqs[i])
            self._send_to_pickup(idle[j], reqs[i])

    def _eta(self, v: Vehicle, node) -> float:
        # idle/repositioning vehicles: finish current edge then route
        if v.route:
            nxt = v.route[0]
            return v.leg_left + self.tt(nxt, node)
        return self.tt(v.node, node)

    def _reposition(self) -> None:
        """Predictive: nudge a few idle cars toward under-served demand.

        Each node's 'need' is its demand weight share times fleet size; cars
        move only if a nearby node (<=4 min away) is short of supply and their
        own spot is already well covered. Capped per cycle to limit deadheading.
        """
        idle = [v for v in self.vehicles if v.state == IDLE and not v.route]
        if len(idle) < 2:
            return
        total_w = sum(self._w_list)
        supply = {}
        for v in self.vehicles:
            if v.state in (IDLE, REPOSITION, TO_PICKUP):
                tgt = v.route[-1] if v.route else v.node
                supply[tgt] = supply.get(tgt, 0) + 1
        n = len(self.vehicles)
        nbr = self.city.neighborhoods(150.0)
        if self._need is None:  # x3: neighborhoods overlap
            self._need = {k: sum(self.w[j] for j in nbr[k]) / total_w * n * 3.0 for k in self.nodes}
        need = self._need

        def local_supply(k):
            return sum(supply.get(j, 0) for j in nbr[k])

        moved = 0
        for v in idle:
            if moved >= 3:
                break
            if local_supply(v.node) - need[v.node] < 0.6:
                continue
            best, best_gap = None, 0.6
            for k in self.city.near(v.node, 300.0):
                if k == v.node:
                    continue
                gap = need[k] - local_supply(k)
                if gap > best_gap:
                    best, best_gap = k, gap
            if best is None:
                continue
            v.state = REPOSITION
            self._assign_route(v, best)
            supply[best] = supply.get(best, 0) + 1
            supply[v.node] = supply.get(v.node, 0) - 1
            moved += 1

    # ---------------- maintenance ----------------
    def _predictive_maintenance(self) -> None:
        for v in self.vehicles:
            if v.state == IDLE and not v.route and self.sensor_health(v) >= self.cfg.service_threshold:
                v.state = SERVICE
                v.timer = PLANNED_SERVICE_S
                v.planned_services += 1
                v.km = 0.0
                v.fail_at_km = self._draw_failure_km()

    def _fail(self, v: Vehicle, reason: str = "FAILED") -> None:
        v.failures += 1
        v.station = None
        v.state = DOWN
        v.timer = max(120.0, self.np.lognormal(math.log(self.cfg.repair_mean_s), 0.4))
        r = v.request
        if r is not None:
            # stranded rider: re-queue (keeps original request time -> wait grows)
            r.vehicle = None
            r.picked_at = None
            r.requeued += 1
            self.pending.append(r)
            v.request = None
        v.route = []
        v.leg_left = v.leg_total = 0
        self.events.append(f"t={int(self.t)} car {v.id} {reason}")

    # ---------------- stepping ----------------
    def _move(self, v: Vehicle, dt: float) -> None:
        budget = dt
        while budget > 0 and v.route:
            if v.leg_total == 0:
                nxt = v.route[0]
                v.leg_total = v.leg_left = self._edge_time(v.node, nxt)
            use = min(budget, v.leg_left)
            frac = use / v.leg_total if v.leg_total else 1.0
            dist = self._edge_len(v.node, v.route[0]) * frac
            v.odometer_m += dist
            v.km += dist / 1000.0
            v.soc -= dist / 1000.0 * 100.0 / self.cfg.battery_range_km
            if v.state == RIDING:
                v.revenue_m += dist
            v.leg_left -= use
            budget -= use
            if v.leg_left <= 1e-9:
                v.node = v.route.pop(0)
                v.leg_left = v.leg_total = 0.0
            if v.soc <= 0:
                v.soc = 0.0
                self._fail(v, "ran out of charge")
                return
            if v.km >= v.fail_at_km:
                self._fail(v)
                return

    def step(self) -> None:
        cfg = self.cfg
        self._spawn_requests()

        # abandon
        keep = []
        for r in self.pending:
            if self.t - r.t > MAX_WAIT_S:
                self.abandoned += 1
            else:
                keep.append(r)
        self.pending = keep

        self._charge_logic()
        if cfg.dispatch == "nearest":
            self._dispatch_nearest()
        else:
            self._dispatch_batch()
            if cfg.dispatch == "predictive" and int(self.t) % 30 == 0:
                self._reposition()
        if cfg.maintenance == "predictive" and int(self.t) % 20 == 0:
            self._predictive_maintenance()

        rate = 100.0 / (cfg.charge_minutes * 60.0)  # % per second on a plug
        for v in self.vehicles:
            if v.state in (SERVICE, DOWN):
                v.timer -= cfg.dt
                if v.timer <= 0:
                    if v.state == DOWN:
                        v.km = 0.0
                        v.fail_at_km = self._draw_failure_km()
                        v.soc = max(v.soc, 40.0)  # tow / roadside charge
                    v.state = IDLE
                continue
            if v.state == CHARGING:
                if v.plugged:
                    v.soc = min(100.0, v.soc + rate * cfg.dt)
                    if v.soc >= cfg.charge_to:
                        self._release(v)
                continue
            if v.state in (RIDING, TO_PICKUP):
                v.busy_s += cfg.dt
            if v.route:
                self._move(v, cfg.dt)
            if v.state == DOWN:
                continue
            if not v.route:
                if v.state == TO_PICKUP:
                    self._begin_ride(v)
                elif v.state == RIDING:
                    r = v.request
                    r.done_at = self.t
                    self.done.append(r)
                    v.request = None
                    v.state = IDLE
                elif v.state == REPOSITION:
                    v.state = IDLE
                elif v.state == TO_CHARGER:
                    self._arrive(v)
        self.t += cfg.dt

    def run(self, seconds: float) -> "Sim":
        end = self.t + seconds
        while self.t < end:
            self.step()
        return self

    # ---------------- metrics ----------------
    def metrics(self) -> dict:
        waits = [r.picked_at - r.t for r in self.done if r.picked_at is not None]
        total_m = sum(v.odometer_m for v in self.vehicles)
        rev_m = sum(v.revenue_m for v in self.vehicles)
        elapsed = max(self.t, 1.0)
        arr = np.array(waits) if waits else np.array([0.0])
        total_req = len(self.done) + self.abandoned + len(self.pending)
        return {
            "t_s": self.t,
            "requests": total_req,
            "served": len(self.done),
            "abandoned": self.abandoned,
            "pending": len(self.pending),
            "service_rate": round(len(self.done) / max(total_req - len(self.pending), 1), 3),
            "avg_wait_s": round(float(arr.mean()), 1),
            "p90_wait_s": round(float(np.percentile(arr, 90)), 1),
            "utilization": round(sum(v.busy_s for v in self.vehicles) / (elapsed * len(self.vehicles)), 3),
            "deadhead_pct": round(100 * (1 - rev_m / total_m), 1) if total_m else 0.0,
            "failures": sum(v.failures for v in self.vehicles),
            "planned_services": sum(v.planned_services for v in self.vehicles),
            "stranded_riders": sum(r.requeued for r in self.done) + sum(r.requeued for r in self.pending),
            "fleet_available": sum(1 for v in self.vehicles if v.state not in (DOWN, SERVICE, CHARGING, TO_CHARGER)),
            "charging": sum(1 for v in self.vehicles if v.state == CHARGING and v.plugged),
            "queued": sum(1 for v in self.vehicles if v.state == CHARGING and not v.plugged),
            "to_charger": sum(1 for v in self.vehicles if v.state == TO_CHARGER),
            "plugs_total": sum(st.plugs for st in self.stations),
            "avg_soc": round(sum(v.soc for v in self.vehicles) / len(self.vehicles), 1),
            "min_soc": round(min(v.soc for v in self.vehicles), 1),
            "charge_sessions": self.charge_sessions,
        }

    def snapshot(self) -> dict:
        vs = []
        for v in self.vehicles:
            lat, lon = self.position(v)
            if v.route:
                a, b = self.g.nodes[v.node], self.g.nodes[v.route[0]]
                dx = (b["lon"] - a["lon"]) * math.cos(math.radians(a["lat"]))
                dy = b["lat"] - a["lat"]
                if abs(dx) + abs(dy) > 1e-12:
                    v.heading = math.degrees(math.atan2(dx, dy))
            route = []
            if v.route and v.state in (TO_PICKUP, RIDING, REPOSITION, TO_CHARGER):
                route = [[round(lon, 6), round(lat, 6)]] + [
                    [round(self.g.nodes[n]["lon"], 6), round(self.g.nodes[n]["lat"], 6)] for n in v.route[:30]]
            vs.append({
                "id": v.id, "lat": lat, "lon": lon, "state": v.state, "heading": round(v.heading, 1), "route": route,
                "health": round(min(v.km / max(v.fail_at_km, 1e-6), 1.5), 2),
                "km": round(v.km, 1),
                "soc": round(v.soc), "plugged": v.plugged, "station": v.station,
            })
        reqs = [{
            "id": r.id, "lat": self.g.nodes[r.origin]["lat"], "lon": self.g.nodes[r.origin]["lon"],
            "wait": round(self.t - r.t),
        } for r in self.pending]
        sts = [{"id": st.id, "name": st.name, "lat": self.g.nodes[st.node]["lat"], "lon": self.g.nodes[st.node]["lon"],
                "plugs": st.plugs, "in_use": len(st.occupied), "queue": len(st.queue)} for st in self.stations]
        return {"t": self.t, "vehicles": vs, "pending": reqs, "stations": sts, "metrics": self.metrics(),
                "events": self.events[-8:]}

    def graph_geojson(self) -> dict:
        return self.city.geojson()


def compare(hours: float = 2.0, seeds=(1, 2, 3), city: City | None = None, **overrides) -> list[dict]:
    """Headless policy comparison, averaged over seeds."""
    rows = []
    for d in DISPATCH:
        for m in MAINT:
            acc = []
            for s in seeds:
                cfg = Config(dispatch=d, maintenance=m, seed=s, **overrides)
                acc.append(Sim(cfg, city).run(hours * 3600).metrics())
            keys = ["service_rate", "avg_wait_s", "p90_wait_s", "utilization", "deadhead_pct",
                    "failures", "planned_services", "stranded_riders", "abandoned", "charge_sessions", "avg_soc"]
            row = {"dispatch": d, "maintenance": m}
            for k in keys:
                row[k] = round(float(np.mean([a[k] for a in acc])), 3)
            rows.append(row)
    return rows
