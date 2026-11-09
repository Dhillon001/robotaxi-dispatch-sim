# Robotaxi Dispatch Simulator

Fleet simulator where **dispatch policy** and **vehicle reliability** interact.
Synthetic city (jittered grid near Foster City), Weibull component failures,
live Leaflet map, and a headless policy-comparison endpoint.

## Run
    pip install -r requirements.txt
    uvicorn app.main:app --reload      # open http://localhost:8000
    pytest -q

## What's modeled
- Dispatch: `nearest` (greedy FIFO), `batch` (10s Hungarian assignment, fairness-weighted), `predictive` (batch + demand-aware repositioning)
- Maintenance: `reactive` (fix after failure) vs `predictive` (service idle cars when noisy health estimate crosses threshold)
- Failures: km-since-service vs Weibull draw (shape 2.2). A failure strands the rider (re-queued, wait keeps growing) and takes the car out for a lognormal repair time.
- Metrics: wait avg/p90, utilization, deadhead %, failures, stranded riders, abandonment (10 min patience)

## Roadmap
1. Real roads via OSMnx (replace `sim/city.py:build_city`)
2. Tune/replace the repositioning heuristic (currently ~no gain over batch); try a learned demand forecast
3. Component-level telemetry (battery, lidar, brakes) feeding an actual failure-prediction model
4. Charging + depot constraints, surge/time-of-day demand from real trip data
5. Experiment runner with confidence intervals; export to parquet
