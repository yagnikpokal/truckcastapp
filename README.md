# Truckcast

Weather-aware truck routing. A driver enters an origin, a destination, a departure, and a load weight. The app fetches three road corridors, samples the forecast at the truck's estimated arrival every 10, 25, or 50 miles, and recommends the route that stays out of the worst weather.

## Run it locally

Two processes. From the repository root:

```bash
python3.13 -m venv backend/.venv
backend/.venv/bin/pip install -r backend/requirements.txt
backend/.venv/bin/python backend/manage.py test routing

cd frontend
npm install
npm run dev
```

In another terminal:

```bash
backend/.venv/bin/python backend/manage.py runserver 8000
```

Open http://127.0.0.1:5173. The Vite server proxies `/api` to Django.

To serve the built interface from Django instead:

```bash
cd frontend && npm run build
cd ../backend && .venv/bin/python manage.py runserver 8000
```

Then open http://127.0.0.1:8000.

## How a route is scored

Weather comes from the Open-Meteo hourly forecast. Wind is miles per hour. Rain and snow are the hourly totals in inches, read as inches per hour. The hour nearest the checkpoint's ETA is the one that counts.

A value on a shared boundary is placed in the higher band. Rain of 1.00 in/hr and snow of 3.0 in/hr stay Severe, because No Travel for those hazards is strictly above those values.

| | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind (mph) | below 25 | 25–34 | 35–44 | 45–54 | 55 and above |
| Rain (in/hr) | below 0.10 | 0.10–0.24 | 0.25–0.49 | 0.50–1.00 | above 1.00 |
| Snow (in/hr) | below 0.5 | 0.5–0.9 | 1.0–1.9 | 2.0–3.0 | above 3.0 |

The checkpoint's risk is the worst of the three hazards.

Load rules raise wind risk only:

- 55 mph or more is No Travel for every load.
- 45–54 mph and a load above 30,000 lb is No Travel.
- 35–44 mph and a load above 40,000 lb is Severe.

Miles between two checkpoints take the worse of the two endpoint risks, so a severe arrival counts the miles leading into it. Average risk is the mile-weighted mean of the scores Low 1, Moderate 2, High 3, Severe 4, No Travel 5.

Recommendation order:

1. Fewest No Travel miles. No Travel is above Severe on the scale, so it is compared first.
2. Fewest Severe miles.
3. Fewest High miles.
4. Lowest average risk.
5. Shortest travel time.

If the winner still crosses No Travel or Severe weather, the card says so.

Arrival times come from the routing engine's maneuver timing, spread along the road by distance. They are not a single average speed for the whole trip.

## Corridor forecast

After the routes are drawn, the app requests one hourly forecast for a band along the corridors (the road, plus a parallel offset on each side). The slider scrubs hour 0 through hour 48 locally. Moving it does not call the weather service again.

## APIs

No API keys are required.

| Job | Service | Fallback |
| --- | --- | --- |
| Truck routes and alternate corridors | Valhalla public server | OSRM driving profile |
| Place search | Photon | Nominatim |
| Forecast | Open-Meteo | none |
| Basemap | Esri World Street Map | none |

Truck weight sent to Valhalla is the cargo weight converted to metric tons, with the default semi height, width, and length. If the truck profile cannot find a road, the app retries with the auto profile and says so on the result.

Override the endpoints with `VALHALLA_URL`, `OSRM_URL`, `PHOTON_URL`, `NOMINATIM_URL`, and `OPEN_METEO_URL`.

## Tests

```bash
backend/.venv/bin/python backend/manage.py test routing
```

The tests cover the risk bands, the load upgrades, checkpoint spacing, mile accounting, and the recommendation order. They do not call the network.

## Deploy

`Dockerfile` builds the frontend and serves it with gunicorn. `render.yaml` is a Render web service using that image. Set `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=false` in the host's environment. The container reads `PORT`.

```bash
docker build -t truckcast .
docker run -p 8000:8000 -e PORT=8000 -e DJANGO_DEBUG=false truckcast
```

## Walkthrough outline

A five to ten minute recording can follow this path:

1. Show the empty map and the inputs: origin, destination, departure, load, and the 10 / 25 / 50 mile sampler.
2. Run Chicago to Indianapolis at 45,000 lb. Point out three truck corridors, the recommended badge, and the reason (often shortest time when the forecast is calm).
3. Open a checkpoint. The popup is the wind, rain, and snow at that ETA, not at departure.
4. Switch the sample interval to 10 miles and plan again so the checkpoint spacing changes.
5. Raise the load past 40,000 lb and, on a windier day, show a High wind band becoming Severe.
6. Scrub the 0–48 hour corridor slider and press Play. The heatmap updates from data already in the browser.
7. Click the other route cards and Zoom to route. The selected corridor is drawn in full risk color; the others stay dimmed.
