# Robotaxi Dispatch Simulator

Fleet simulator where **dispatch policy** and **vehicle reliability** interact.
Synthetic city (jittered grid), Weibull component failures,
live Leaflet map, and a headless policy-comparison endpoint.

## Run
    pip install -r requirements.txt
    uvicorn app.main:app --reload      # open http://localhost:8000
    pytest -q

## Map
MapLibre GL with free OpenFreeMap vector tiles (no API key): street names at every zoom, 3D buildings,
light/dark themes. Cars are map-aligned icons that glide between sim updates; glowing lines show each
car's route to its pickup / dropoff; waiting riders pulse. Buttons: 3D view, Orbit, Follow a car.

## Cities
Pick a city in the sidebar: a synthetic grid (instant, offline) or real OpenStreetMap roads for
San Francisco, Las Vegas, Austin, Miami, Los Angeles. Real cities download roads
via OSMnx on first use (needs internet, ~10-30s) and are cached in `data/osm_cache/`.
Add your own in `sim/city.py:CITIES` (centre lat/lon + radius in metres).

## What's modeled
- Dispatch: `nearest` (greedy FIFO), `batch` (10s Hungarian assignment, fairness-weighted), `predictive` (batch + demand-aware repositioning)
- Maintenance: `reactive` (fix after failure) vs `predictive` (service idle cars when noisy health estimate crosses threshold)
- Failures: km-since-service vs Weibull draw (shape 2.2). A failure strands the rider (re-queued, wait keeps growing) and takes the car out for a lognormal repair time.
- Metrics: wait avg/p90, utilization, deadhead %, failures, stranded riders, abandonment (10 min patience)

## Roadmap
1. Curved road geometry and one-way/turn restrictions in the animation; traffic-aware travel times
2. Tune/replace the repositioning heuristic (currently ~no gain over batch); try a learned demand forecast
3. Component-level telemetry (battery, lidar, brakes) feeding an actual failure-prediction model
4. Charging + depot constraints, surge/time-of-day demand from real trip data
5. Experiment runner with confidence intervals; export to parquet
