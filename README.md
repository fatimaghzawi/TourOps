# TourOps

TourOps is an operations platform for travel agencies. Staff plan packages and dated tours, book customers, hold supplier inventory, collect payment, and read profit from the same records they work in day to day.

The product is a Django HTML application with a JSON API under `/api/`. Staff accounts live in Django (`AUTH_USER_MODEL`). Customers, tours, invoices, and all other operational data live in MongoDB through PyMongo—not the Django ORM.

```
Request → URL → View → Form / validators → Service → Repository → MongoDB
```

Services own business rules. Repositories persist documents. Views do not write Mongo directly.

## Capabilities

- **Catalog** — suppliers, sellable services (each tied to a supplier), package templates, and dated tours
- **Operations** — customers, bookings, and supplier reservations (holds must be confirmed before client seats are sold)
- **Receivables** — invoices, payments, receipts, and refunds
- **Payables** — tour and general expenses, then supplier payouts
- **Finance & reports** — balances and P&L are calculated from source documents; they are not stored as editable masters
- **Platform** — roles (travel agent, accountant, owner/admin), attachments, notifications, and audit logs

Packages are templates. Customers book tours. Catalog services cannot exist without a supplier; package and tour `services[]` lines are snapshots of that catalog.

## Requirements

- Python 3.12 or later
- MongoDB (local, Atlas, or the MongoDB service in Docker Compose)
- Docker Desktop if you deploy with Compose
- A virtualenv is recommended for local (non-Docker) development

## Local setup

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

Then:

```bash
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed_demo_user
python manage.py runserver
```

On macOS or Linux, use `cp .env.example .env` instead of `copy`. Keep `DJANGO_DEBUG=true` in local `.env` so the development server can run without a production secret.

Open [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/).

### Demo staff

These accounts exist only for local development. Change them before any shared or public deploy. `seed_demo_user` refuses to run when `DEBUG` is false.

| Email | Password | Role |
| --- | --- | --- |
| `owner@tourops.local` | `changeme` | Owner / Admin |
| `agent@tourops.local` | `changeme` | Travel Agent |
| `accountant@tourops.local` | `changeme` | Accountant |

### Sample business data

Staff logins alone do not fill Mongo. Use one of:

```bash
python manage.py seed_demo_data
python manage.py seed_istanbul_escape
```

`seed_demo_data` loads a Cedar Routes agency dataset. `seed_istanbul_escape` replaces business records with the Istanbul Escape walkthrough (15–20 September, 30 seats, tour photos, paid bookings, and supplier holds). Both commands are intended for local `DEBUG` use.


## Tests

```bash
pytest
```

## Deploy with Docker

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/) (or Docker Engine plus the Compose plugin).

1. Copy environment defaults and set a real secret:

```bash
copy .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Paste the generated string into `DJANGO_SECRET_KEY` in `.env`.

2. For a public host, also set:

```
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=app.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://app.example.com
DJANGO_SECURE=true
```

Leave `DJANGO_SECURE=false` while you test on `http://localhost:8000`. Turn it on only behind HTTPS (a reverse proxy that sets `X-Forwarded-Proto`).

3. Build and start the app and MongoDB:

```bash
docker compose up --build -d
```

Compose always points the app at the `mongo` service (`mongodb://mongo:27017`), even if `.env` still says `localhost`. Staff users persist on the `sqlite_data` volume; uploads persist on `media_data`.

4. Open [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/). Create the first owner (this prompts for email, first name, last name, and password):

```bash
docker compose exec web gosu appuser python manage.py createsuperuser
```

`seed_demo_user` and the Istanbul seed refuse to run when `DEBUG` is false. Use them only on a local stack with `DJANGO_DEBUG=true`.

Useful commands:

```bash
docker compose logs -f web
docker compose exec web gosu appuser python manage.py ensure_indexes
docker compose down
```

`docker compose down` stops containers. Add `-v` only if you intend to wipe Mongo, SQLite, and media volumes.

Put TLS in front of port 8000 in production (Caddy, nginx, or a cloud load balancer). Serve files through TourOps attachment preview URLs, not raw `/media/` paths.

## Production checklist

Do not ship demo passwords or `DJANGO_DEBUG=true`.

- Long random `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG=false`
- `DJANGO_SECURE=true` behind HTTPS
- `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS` set to the public host
- Indexes: `python manage.py ensure_indexes` (the container entrypoint and WSGI startup also run this)
- Gunicorn workers: set `GUNICORN_WORKERS` if you need more than the default of 3

Profit is invoice revenue (`total_amount − refunded_amount` on issued, partial, paid, and refunded invoices) minus expense documents. Pending bookings do not count. Cash flow is customer payments in, minus supplier payouts and completed refunds. Invoice remaining is `max(total − paid, 0)`; refunds do not reopen the receivable.
