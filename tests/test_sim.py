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
