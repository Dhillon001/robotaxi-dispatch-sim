from sim.engine import Sim, Config, compare


def test_runs_and_serves():
    m = Sim(Config(seed=3)).run(1800).metrics()
    assert m["served"] > 0
    assert 0 <= m["utilization"] <= 1


def test_deterministic():
    a = Sim(Config(seed=5)).run(900).metrics()
    b = Sim(Config(seed=5)).run(900).metrics()
    assert a == b


def test_failures_requeue_riders():
    s = Sim(Config(seed=2, weibull_scale_km=3.0)).run(1800)
    assert s.metrics()["failures"] > 0


def test_all_policies_run():
    for d in ("nearest", "batch", "predictive"):
        for mt in ("reactive", "predictive"):
            Sim(Config(dispatch=d, maintenance=mt, n_vehicles=10)).run(600)


def test_battery_drains_and_cars_charge():
    s = Sim(Config(seed=4, n_vehicles=12, start_soc_min=20.0, battery_range_km=40.0)).run(3 * 3600)
    m = s.metrics()
    assert m["charge_sessions"] > 0
    assert m["plugs_total"] > 0 and m["avg_soc"] > 0
    assert all(0 <= v.soc <= 100 for v in s.vehicles)


def test_low_battery_car_heads_to_charger():
    s = Sim(Config(seed=1, n_vehicles=6, demand_per_min=0.1))
    v = s.vehicles[0]
    v.soc = 10.0
    s.run(30)
    assert v.state in ("to_charger", "charging")
    s.run(1800)
    assert v.soc > 10.0


def test_snapshot_has_stations_and_soc():
    snap = Sim(Config(n_vehicles=10)).snapshot()
    assert snap["stations"] and "soc" in snap["vehicles"][0]
    assert snap["metrics"]["plugs_total"] >= 2
