# SlopeGuard NER

Working demonstration for **SIH26001: AI-Based early warning and landslide Risk Monitoring System in NER**, Ministry of Development of North Eastern Region.

## Run

Python 3.12+:

```sh
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m pytest -q
```

Open http://localhost:8000. Interactive API documentation: `/docs`.

## Demonstrate

1. Inspect a priority location on Overview, then open Risk explorer.
2. Open Forecast & simulator. Compare dry and extreme-rainfall presets, then inspect rule contributions.
3. Enter the Field officer demo from the account menu. Create an observation with optional photo/video evidence.
4. Turn off connectivity after the app has loaded. Submit another observation; it is retained in IndexedDB. Reconnect and sync.
5. Sign out and enter the District official demo. Verify a report, acknowledge an advisory, dispatch a response team and close it.
6. Inspect the audit trail in Data & model. Update corridor access and export CSV records.
7. Open Project briefing and use Presentation mode to explain the complete solution.

Demo roles: `official@demo.slopeguard.app`, `field@demo.slopeguard.app`, `citizen@demo.slopeguard.app`. Shared sample password: `Demo@SlopeGuard26`. These are intentionally public demo identities, not administrator credentials. Account-menu buttons enter these sample workspaces directly.

## Implementation

- FastAPI, Pydantic validation, signed HttpOnly session cookies, SameSite and origin checks, request size and write-rate limits.
- Scikit-learn Random Forest trained reproducibly on 2,400 explicitly synthetic, rule-generated samples; 25% held out for an engineering benchmark.
- Risk index = 65% rule score + 35% Random Forest output. Thresholds: low <35, moderate 35–54, high 55–74, critical >=75. None are operationally calibrated.
- Leaflet GIS, OpenStreetMap basemap, optional Esri satellite imagery, illustrative risk footprints, road segments, settlements and infrastructure.
- Open-Meteo modelled precipitation retrieval and next-24-hour context, with explicit provider failure handling and cache provenance. Not IMD observations.
- IndexedDB evidence queue, idempotent uploads, cached PWA shell. Background sync occurs when the app is open and connectivity returns; it is not guaranteed after the browser is closed.
- Report verification, validated alert state transitions, road updates, CSV formula-injection protection, and role-restricted audit access.
- Administrator-only `/api/ingest` validates feature records and generates a deduplicated in-app advisory for high/critical readings.
- PostgreSQL support through `DATABASE_URL`, SQLite fallback for local or disposable presentation sessions.

## Deployment

Source is placed under `slopeguard-ner/` on the isolated `slopeguard-ner` branch of `hackerncet/demo`. Existing repository files and main are preserved.

Render build command from repository root:

```sh
pip install -r slopeguard-ner/requirements.txt
```

Start command:

```sh
cd slopeguard-ner && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Set `SESSION_SECRET` to a long random secret. Optional `ADMIN_EMAIL` and `ADMIN_PASSWORD` enable administrator login; they must never be committed. Set `DATABASE_URL` for durable records. Set `DEMO_MODE=false` before a controlled pilot to disable the public sample identities.

**Free Render limit:** SQLite records and uploaded evidence on a free web service may disappear on restart or redeploy. The selected account already has its one permitted free PostgreSQL instance, so a second free database cannot be provisioned. Durable rollout requires a supplied PostgreSQL URL or a configured persistent disk on a suitable paid service. No paid resource is silently provisioned. Free web services may cold-start after inactivity.

## Requirements and honest scope

| SIH requirement | Working implementation | Real pilot dependency |
|---|---|---|
| AI risk analytics | Explainable hybrid rule/RF engine and sensitivity simulator | Labelled geotechnical inventory, time/spatial holdouts, calibration and independent validation |
| Rainfall/soil/slope/history | Schema validation, authenticated ingestion, optional modelled weather | IMD permission, surveyed DEM/slope and sensor commissioning |
| GIS and road connectivity | Interactive GIS, road access status, illustrative settlements and exposure | Verified road graph and GIS assets; no navigational routing guarantee |
| Satellite feeds | Satellite basemap and ingestion of derived vegetation features | Remote-sensing change-detection pipeline is not implemented |
| Geo-tagged photo/video reports | JPEG/PNG/MP4/WebM upload up to 5 MB, verification and protected evidence endpoint | Production object storage, malware scanning and stronger identity |
| Alerts and multilingual access | English/Hindi/Assamese advisory composer, in-app records and response tracking | SMS provider, authorized recipients, translations and operating procedures |
| Offline access | Cached shell/snapshot, per-user IndexedDB queue and reconnect sync | Device-management policy and field acceptance tests |
| Security and accountability | Role checks, audit events, session security and exports | Organizational SSO, scoped districts, privacy review and infrastructure hardening |

This is a presentation prototype, not a validated life-safety warning service. Synthetic benchmark numbers do not establish real-world accuracy, event probabilities or warning lead times. Low scores do not establish safety. No affiliation with MDoNER, IMD, GSI or NDMA is implied.

## References

- Official SIH statement: https://sih.gov.in/sih2026PS (SIH26001).
- Uploaded Landslide Risk Monitoring Synopsis: used as the primary project brief; personal student details are not copied into the public source.
- GSI landslide activities: https://bhusanket.gsi.gov.in/Activities_V9.html
- Open-Meteo documentation: https://open-meteo.com/en/docs
- Leaflet 1.9.4: BSD-2-Clause; bundled assets retain their original license headers. https://github.com/Leaflet/Leaflet/blob/v1.9.4/LICENSE
- Map data © OpenStreetMap contributors. Satellite tiles © Esri and its data providers.
