# Campus Bites 🍜

**Rate the food on and around campus.** A Flask + SQLite web app (project #2, "Rate the food").

- **Home page** ranks every place by average rating (ties go to the place with more reviews), with search, a category filter and sorting.
- **Place page** shows the average, a chart of how the ratings are spread (5★ … 1★), and all reviews.
- **Accounts**: sign up, log in, log out. Passwords are hashed; every form carries a CSRF token.
- **Logged-in users only** can leave a rating (1–5) and a short review — **one per place** — and edit or delete *their own* review. They can also add a missing place.
- **User pages** (`/u/<username>`) list everything a person has reviewed.
- **Error handling**: wrong input shows a clear message next to the form; missing places/users and bad URLs get a friendly 404 page.
- **Persistent data** in a SQLite file. A brand-new database is filled with fictitious places, users and ~100 reviews so it never looks empty.

Demo login: **`demo` / `campusbites`** (or register your own account).

## Run it on your laptop

```bash
git clone <this repo> campus-bites && cd campus-bites
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open <http://localhost:8000>. The database file `campus_bites.db` is created (and seeded) on first start; stop and restart the server and everything is still there.

Handy extras:

```bash
python seed.py --reset               # wipe the database and re-seed it
AUTO_SEED=0 python app.py            # start with an empty database instead
pip install -r requirements-dev.txt && python -m pytest   # run the tests
```

To try both sides, open two browser windows (one incognito) and register two accounts.

## Deploy to Google Cloud Run

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
./deploy.sh                          # prints the https://...run.app address when done
```

`deploy.sh` runs `gcloud run deploy --source .` (built from the `Dockerfile`) with:

- `--allow-unauthenticated` so anyone can open it;
- `--max-instances 1` so every visitor uses the same SQLite file;
- `--min-instances 1` so the instance, and the data in it, isn't shut down when nobody is using it;
- a fixed `SECRET_KEY` (generated once into `.secret_key`, which git ignores) so logins survive redeploys.

> SQLite lives on the container's disk, so a **redeploy starts from a fresh, re-seeded database**. That's fine for this assignment; a real deployment would use Cloud SQL.

When grading is done: `gcloud run services delete campus-bites --region us-central1`.

## Project layout

```
app.py            routes: rankings, place page, reviews, add place, user page, errors
auth.py           register / login / logout, login_required, CSRF tokens
db.py             SQLite connection per request, creates tables on startup
schema.sql        users, places, reviews (UNIQUE(place_id, user_id) = one review each)
seed.py           fictitious demo data
templates/        Jinja templates
static/style.css  styles (mobile friendly)
tests/            pytest suite
Dockerfile        container for Cloud Run (gunicorn, 1 worker × 8 threads)
deploy.sh         one-command Cloud Run deploy
```
