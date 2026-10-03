# Campus Swap - analytics back-end

Django service that answers the project's business questions about the Campus Swap marketplace and will serve the analytics dashboard. It **only reads** from the same PostgreSQL database the main back-end (`../campus-swap-backend`, NestJS + Prisma) writes to. The full pipeline is drawn in `docs/analytics-pipeline.drawio`; the stages are Flutter app, NestJS ingestion, PostgreSQL, this service, then the dashboard and the app.

## Run it

```bash
uv sync
uv run python manage.py runserver
uv run python manage.py test
```

- Python 3.13, Django 6.1, `psycopg2-binary`, `dj-database-url`, `python-dotenv`. Dependencies are managed with `uv` (`pyproject.toml`, `uv.lock`); `requirements.txt` exists for deployment.
- `.env` (never commit): `DATABASE_URL`, `SECRET_KEY`, `DEBUG=True` for local work.
- `ALLOWED_HOSTS` includes `.vercel.app`, `localhost`, `127.0.0.1` and `10.0.2.2` (Android emulator).

## Design decisions

- **One shared database, no ETL.** The business questions need operational data (materials, exchanges, users, wishlist, notifications, chats) joined with usage events (`AnalyticsEvent`), so this service reads the main database directly instead of a copy. Deliberate trade-off for a university project.
- **Read-only by design.** `config/routers.py` (`ReadOnlyRouter`) raises on any write and refuses migrations. Models are `managed = False`, so Django never creates or alters tables. `django.contrib.admin`, `auth`, `sessions` and `messages` are disabled because nothing here needs them. Note that read-only is enforced by Django only: unless `DATABASE_URL` uses a Postgres role with `SELECT` only, the database itself would still allow writes. Creating that role is the recommended hardening.
- **Prisma is the source of truth for the schema.** `analytics/models.py` mirrors it by hand, with `db_column` set to the camelCase column names and `db_table` to the Prisma model names (`'User'`, `'Exchange'`, ...). Prisma migrations do not update these models, so they must be kept in sync manually (see below).
- **Crashes and device telemetry are out of scope here.** BQ1 is answered by Firebase Crashlytics and its own console. There is deliberately no link between Crashlytics and this service.
- **Everything is a view returning JSON.** One function per business question in `analytics/views.py`, routed in `analytics/urls.py` under `/analytics/`. The same endpoints feed the dashboard and the mobile app's in-app features. `/` only returns a hello-world listing of the routes.
- **The dashboard is served by Django**, one page per business question: `/dash-board/` is the overview and `/dash-board/bq<N>/` the dedicated view (templates in `analytics/templates/analytics/dashboard/`: `base.html` layout and sidebar, `_hero.html` question and one-line answer, `_dash.js` shared helpers included inline, one `bqN.html` per question). Libraries load from a CDN because there is no static-file serving: Chart.js everywhere, plus Leaflet (OpenStreetMap tiles) for the BQ12 map. Pages fetch the `/analytics/` JSON client-side and derive their insights from it. To add a question: add an entry to `DASHBOARD_QUESTIONS` in `views.py`, a `bqN.html` page, and a `HEADLINES[N]` function in `_dash.js`. BQ5 is shifted from UTC to campus time in the browser using the offset computed from `CAMPUS_TIME_ZONE`.

## Endpoints and business questions

| Route | BQ | Status |
|---|---|---|
| `/analytics/buyer-journey-funnel/` | 2 | done |
| `/analytics/chat-to-meeting-point/` | 4 | done |
| `/analytics/activity-times/` | 5 | done |
| `/analytics/categories/` | 6 | done |
| `/analytics/wishlist-conversion/` | 7 | done |
| `/analytics/meeting-points/` (optional `?hour=0-23`) | 12 | done |
| (none yet) | 8, 9, 10, 11 | `# TODO: implement` placeholders in `views.py` |
| (none yet) | 3, 13, 14 | not started; 3 and 13 are only partly answerable by SQL |
| Firebase Crashlytics console | 1 | outside this service |

`business_questions_feasibility.md` states what the data can and cannot answer. Also check `Business-Questions.md` to know what a business question actually is.

## How to add a business question

1. Add a function in `analytics/views.py` under a `# Business Question N` comment, and a route in `analytics/urls.py` (also add it to the listing in `config/urls.py`).
2. **Split the maths from the query.** The existing views fetch rows with `.values(...)` and pass plain lists or dicts to a pure function (`calculate_buyer_journey_metrics`, `summarize_whishlist_conversion`, `calculate_chat_to_meeting_metrics`). Unit tests call the pure function with hand-made data (`SimpleTestCase`, no database needed), so follow that pattern. Tests live in `analytics/test_*.py`, one file per question.
3. Use database aggregation (`Count`, `Extract*`) when it is a simple group-by, as in BQ5 and BQ6. Fetching rows into Python is fine for window-style logic (funnel, conversion) but pulls whole tables; keep an eye on size.
4. Time of day is campus-local: the database stores UTC and `CAMPUS_TIME_ZONE = 'America/Bogota'`. See `CampusHour` in `views.py` for hour extraction in local time.
5. Count only `ExchangeStatus.COMPLETED` exchanges when a question means "completed". Pending and cancelled exchanges also exist.

## Keeping models in sync with Prisma

After any change to `../campus-swap-backend/prisma/schema.prisma`, update `analytics/models.py` the same way: same column name via `db_column`, same enum values, same nullability. Known drift at the time of writing:

- `Exchange.material` is a `OneToOneField`, but a material can now have several exchanges, so it should be a `ForeignKey` (the `Material.exchange` reverse accessor, used by BQ6, would then become a different one).
- `Exchange` is missing `orderNumber`, `createdAt`, `cancelledAt`, `receivedCondition`, `meetingStartsAt`, `meetingEndsAt`; `Message` is missing `type` and `meetingProposalId`.
- No models yet for `Rating`, `MeetingProposal` or `ScheduleBlock`; `NotificationType` lacks `ORDER_PLACED`.
- `AnalyticsEventType.MEETING_CONFIRMED` exists here but not in the Prisma enum; BQ4 already tolerates its absence and falls back to completed exchanges with a meeting point.

Views already guard against a missing column or enum value with `try/except ProgrammingError` / `DataError`. Keep that behaviour for columns that a not-yet-applied migration might lack, but do not rely on it as a substitute for syncing the models.

## Known gaps

- The analytics endpoints have no authentication. Anyone who can reach the service can read the aggregates. Decide whether to add a shared key or session before the dashboard is deployed publicly.
- Nothing in the code uses a read-only database role (see the design decisions above).
- The dashboard covers only the implemented questions (2, 4, 5, 6, 7, 12). The BQ5 endpoint itself still groups by UTC hour and weekday; only the dashboard converts it to campus time.
