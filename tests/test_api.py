from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def test_flow():
    assert c.post("/api/reset?dispatch=batch&maintenance=predictive&n_vehicles=8").json()["ok"]
    s = c.post("/api/step?seconds=120").json()
    assert len(s["vehicles"]) == 8 and "metrics" in s
    assert c.get("/api/graph").json()["features"]
    assert c.get("/").status_code == 200
