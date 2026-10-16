# Truckcast customer walkthrough

Use this while recording a 5–10 minute Loom. Each scene says what to click, what to say, and what the test on 15 Oct 2026 actually produced.

Live weather changes, so mile-by-mile numbers on a later day will differ. The behavior to point at does not: three truck routes, weather at the truck’s arrival, the risk bands, and a recommendation that puts bad weather ahead of a shorter drive.

## Requirement checklist

| Requirement | Result |
| --- | --- |
| Origin and destination | Pass. Typed cities and place suggestions both work. |
| Departure date and time | Pass. Defaults to 7:00 tomorrow on the computer’s clock. |
| Load weight | Pass. Typed pounds and 15k / 32k / 45k / 62k presets. |
| Three route options from a routing API | Pass. Valhalla truck profile returned three corridors. OSRM is the fallback if Valhalla is down. |
| Weather every 10, 25, or 50 miles, at the estimated arrival | Pass. 25 miles produced 9 checkpoints on the 186-mile corridor. 10 miles produced 22 checkpoints on the 205-mile corridor. |
| Risk bands for wind, rain, and snow | Pass. Checkpoint risk is the worst of the three. |
| Load rules | Pass in automated tests. Today’s Chicago winds were 5–18 mph, below the 35 mph load thresholds, so the live map did not change a band. |
| Recommend the safest route, then the shortest time | Pass. See the two live outcomes below. |
| Map of routes, checkpoints, risk, ETAs, and summaries | Pass. Route cards, checkpoint table, and map popup. |
| Corridor heatmap with a 0–48 hour slider | Pass. 49 hours, from the departure hour through +48 h. Moving the slider does not call the weather service again. |
| Automated tests | Pass. 23 tests, 0 failures. |
| GitHub repository | [Not created yet. This folder is not a git repo.](https://github.com/yagnikpokal/truckcastapp) |
| Hosted application | [Not deployed yet. `render.yaml` is ready for Render. There is no public URL.](https://truckcast.onrender.com/) |

## How the rules are applied

Say this once, early, so the ranking is not a surprise.

Weather at a checkpoint:

| | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind (mph) | below 25 | 25–34 | 35–44 | 45–54 | 55 and above |
| Rain (in/hr) | below 0.10 | 0.10 up to 0.25 | 0.25 up to 0.50 | 0.50–1.00 | above 1.00 |
| Snow (in/hr) | below 0.5 | 0.5 up to 1.0 | 1.0 up to 2.0 | 2.0–3.0 | above 3.0 |

A value sitting on a shared boundary goes to the higher band. Rain of 1.00 and snow of 3.0 stay Severe, because No Travel for those two is strictly above those numbers.

Load changes wind only, and only upward:

- 55 mph or more is No Travel for every load.
- 45–54 mph and a load above 30,000 lb is No Travel.
- 35–44 mph and a load above 40,000 lb is Severe.

Recommendation order:

1. Fewest No Travel miles. No Travel is worse than Severe, so it is compared first.
2. Fewest Severe miles.
3. Fewest High miles.
4. Lowest mile-weighted average risk (Low 1, Moderate 2, High 3, Severe 4, No Travel 5).
5. Shortest travel time.

Each road segment takes the worse risk of its two checkpoints, so a bad arrival colors the miles leading into it.

## Before you record

From the project root, two terminals:

```bash
backend/.venv/bin/python backend/manage.py runserver 8000
```

```bash
cd frontend
npm run dev
```

Open http://localhost:5173.

The clock on screen is the computer’s timezone. This test machine is GMT+5:30, so 7:00 AM on the form is 7:00 AM India time. On a US computer the same control shows US local time. Say that once if the customer asks.

## Shot list

### 1. Empty map (20 seconds)

Show the origin, destination, departure, load, and the 10 / 25 / 50 mile control. The map is empty and the forecast slider is disabled until a trip is planned.

Say: “The driver enters the haul. The app then asks a truck routing service for three corridors and scores the weather the truck will meet on arrival, not the weather at departure.”

### 2. Chicago to Indianapolis, 32,000 lb, every 25 miles (2 minutes)

Click **Chicago → Indianapolis**.

Observed result, departure 16 Oct 2026 at 7:00 AM GMT+5:30, 32,000 lb, every 25 miles:

| Rank | Route | Time | Distance | No Travel | Severe | High | Average | Worst checkpoint |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 Recommended | I 65 South · IL 1 | 3 h 44 min | 205 mi | 0 | 0 | 0 | 1.00 | Low at mile 205 |
| 2 | I 65 South · I 57 South | 3 h 46 min | 211 mi | 0 | 0 | 0 | 1.00 | Low at mile 211 |
| 3 | I 65 · I 94 East | 3 h 5 min | 186 mi | 0 | 0 | 0 | 1.27 | Moderate at mile 100 |

The reason on the recommended card: **Shortest travel time (3 h 44 min vs 3 h 46 min).**

Say: “The 3 hour 5 minute route is faster, and it is ranked last. Routes 1 and 2 are both average risk 1.00. Route 3 is 1.27 because mile 100 is Moderate. Time only breaks the tie between the two calm routes.”

Open route 3 and the checkpoint table. On the 25-mile sample, mile 100 read:

- ETA 8:41 AM GMT+5:30
- Wind 17 mph, Low
- Rain 0.17 in/hr, Moderate
- Snow 0.00, Low
- Checkpoint risk: Moderate, driven by rain

Click that row. The map popup repeats those three hazards and the ETA.

### 3. Same haul at 45,000 lb, every 10 miles (90 seconds)

Set load to **45k**. The hint changes to: “Above 40,000 lb, 35–44 mph wind is Severe. Above 30,000 lb, 45–54 mph wind is No Travel.”

Select **10 mi** and press **Compare routes**.

Observed result: **45,000 lb · every 10 mi**. The recommended route’s checkpoint table grew from the 25-mile spacing to **22 rows** (mile 0, then every 10 miles, then the destination at mile 205).

| Rank | Route | Time | Distance | Average | Worst checkpoint |
| --- | --- | --- | --- | --- | --- |
| 1 Recommended | I 65 South · IL 1 | 3 h 44 min | 205 mi | 1.00 | Low at mile 205 |
| 2 | I 65 South · I 57 South | 3 h 46 min | 211 mi | 1.00 | Low at mile 211 |
| 3 | I 65 · I 94 East | 3 h 5 min | 186 mi | 1.11 | Moderate at mile 100 |

Say: “Finer sampling found the same Moderate spot at mile 100, and the average on that corridor dropped from 1.27 to 1.11 because the wet stretch is a smaller share of the trip. It is still worse than the calm corridors, so the recommendation does not flip to the faster road. Today’s wind is under 20 mph, so the heavier load does not raise any band.”

### 4. Corridor slider (90 seconds)

After the routes draw, the bar reads **Hour 0** and a mix such as **Low 92% · Moderate 4% · High 1% · Severe 1% · No Travel 1%**.

Drag the slider to hour 12. On this test it became **Hour 12 · 7:00 PM GMT+5:30** and the mix changed to **Low 97% · Moderate 3%**. Press **Play** and let it advance a few hours, then **Pause**.

Say: “This is a band along the roads, including weather beside the lane, for 48 hours after departure. Scrubbing it stays in the browser. It does not re-rank the route. The route score still uses the truck’s arrival time at each checkpoint.”

### 5. The other outcome: calm weather, shortest road wins (60 seconds)

If you want a second clip where time is the only difference, plan Chicago to Indianapolis at 45,000 lb, every 25 miles, with the departure set to **16 Oct 2026, 8:00 AM America/Chicago**.

That request returned three Valhalla truck routes, all average risk 1.00, all Low:

| Rank | Route | Time | Distance | Decision |
| --- | --- | --- | --- | --- |
| 1 Recommended | I 65 · I 94 East | 3 h 5 min | 186 mi | Shortest travel time (3 h 5 min vs 3 h 44 min) |
| 2 | I 65 South · IL 1 | 3 h 44 min | 205 mi | |
| 3 | I 65 South · I 57 South | 3 h 46 min | 211 mi | |

Say: “When the forecast is calm on every corridor, the shortest trip wins. The app says so on the card.”

The corridor forecast for that same plan had 49 hours (16 Oct 8:00 AM through 18 Oct 8:00 AM, Chicago time) and 143 sample points.

### 6. Close on the rules (30 seconds)

Open **How a route is scored** at the bottom of the route list. Read the order: No Travel, Severe, High, average risk, then time.

Say: “If every option still crosses No Travel or Severe weather, the recommended card warns the driver to delay.”

## Proof that does not depend on today’s forecast

These passed in `backend/.venv/bin/python backend/manage.py test routing` (23 tests):

- Wind 24.9 Low, 25 Moderate, 35 High, 45 Severe, 55 No Travel.
- Rain 0.10 Moderate, 0.25 High, 0.50 Severe, 1.00 Severe, 1.01 No Travel.
- Snow 0.5 Moderate, 1.0 High, 2.0 Severe, 3.0 Severe, 3.01 No Travel.
- 50 mph at 30,000 lb stays Severe. 50 mph at 30,001 lb becomes No Travel.
- 40 mph at 40,000 lb stays High. 40 mph at 40,001 lb becomes Severe.
- 55 mph is No Travel even at 1,000 lb. 34 mph stays Moderate even at 80,000 lb.
- A route with No Travel miles loses to a route with Severe miles.
- Fewer Severe miles beat a faster route. Fewer High miles beat a lower-looking average. Average risk breaks a mile tie. Travel time wins only when the weather matches.
- Checkpoints include the origin, the interval, and the destination. A sample within a mile of the destination is dropped.
- A bad sample interval and a zero load are rejected.

If the customer wants to see a load upgrade on the live map, pick a windier day or corridor. The rule fires only when a checkpoint wind is at least 35 mph.
