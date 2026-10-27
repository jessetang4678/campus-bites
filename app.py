"""Campus Bites: rate the places to eat on and around campus."""
import os
import sqlite3

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

import auth
import db
import seed
from auth import login_required
from db import get_db

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["DATABASE"] = os.environ.get(
    "DATABASE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "campus_bites.db")
)
db.init_app(app)

# A brand-new database gets fictitious data so the site never looks empty.
# Set AUTO_SEED=0 to start with an empty database instead.
if os.environ.get("AUTO_SEED", "1") != "0":
    seed.seed_if_empty(app.config["DATABASE"])

app.register_blueprint(auth.bp)
app.before_request(auth.load_user)
app.before_request(auth.check_csrf)
app.jinja_env.globals["csrf_token"] = auth.csrf_token
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024     # forms here are tiny
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# Cloud Run serves over HTTPS; set SECURE_COOKIES=0 only for plain-http testing.
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("K_SERVICE") is not None \
    and os.environ.get("SECURE_COOKIES", "1") != "0"


# ------------------------------------------------------------ error pages

ERROR_TITLES = {
    400: ("Something was wrong with that request", "Please check what you entered and try again."),
    403: ("You can't do that", "That action is not allowed for your account."),
    404: ("Page not found", "We couldn't find that page. The link may be wrong or the item was removed."),
    405: ("That doesn't work here", "This page can't be used that way. Try going back and using the buttons on the page."),
    413: ("That's too much text", "What you sent is too large. Please shorten it and try again."),
    500: ("Something broke on our side", "Sorry about that. Please try again in a moment."),
}


def render_error(code, description=None):
    title, default = ERROR_TITLES.get(code, ("Error", "Something went wrong."))
    # Werkzeug's built-in descriptions are generic; prefer ours unless a view set one.
    message = description if description and not description.startswith(
        ("The requested URL", "The browser (or proxy)", "The method is not allowed",
         "The data value transmitted", "The server encountered", "You don't have the permission")
    ) else default
    return render_template("error.html", code=code, title=title, message=message), code


for _code in (400, 403, 404, 405, 413):
    app.register_error_handler(_code, lambda e: render_error(e.code, e.description))


@app.errorhandler(500)
def server_error(_e):
    return render_error(500)

# Average rating, number of reviews; ties go to the place with more reviews,
# places nobody has reviewed yet come last.
RANKING_SQL = """
    SELECT p.*, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(r.id) AS n_reviews
    FROM places p LEFT JOIN reviews r ON r.place_id = p.id
    GROUP BY p.id
    ORDER BY (COUNT(r.id) = 0), avg_rating DESC, n_reviews DESC, p.name COLLATE NOCASE
"""


SORTS = {
    "rating": "Top rated",
    "reviews": "Most reviewed",
    "name": "Name A–Z",
}


@app.route("/")
def index():
    db_ = get_db()
    ranked = db_.execute(RANKING_SQL).fetchall()
    # Overall rank, so a place keeps its number even when the list is filtered.
    rank_of = {}
    for i, p in enumerate((p for p in ranked if p["n_reviews"]), start=1):
        rank_of[p["id"]] = i

    q = request.args.get("q", "").strip()[:100]
    category = request.args.get("category", "").strip()
    sort = request.args.get("sort", "rating")
    if sort not in SORTS:
        sort = "rating"

    places = list(ranked)
    if q:
        needle = q.casefold()
        places = [p for p in places if needle in
                  f"{p['name']} {p['category']} {p['location']} {p['description']}".casefold()]
    if category:
        places = [p for p in places if p["category"].casefold() == category.casefold()]
    if sort == "reviews":
        places.sort(key=lambda p: (-p["n_reviews"], p["name"].casefold()))
    elif sort == "name":
        places.sort(key=lambda p: p["name"].casefold())

    categories = [r["category"] for r in db_.execute(
        "SELECT DISTINCT category FROM places ORDER BY category COLLATE NOCASE")]
    filtered = bool(q or category)
    return render_template("index.html", places=places, rank_of=rank_of, q=q,
                           category=category, sort=sort, sorts=SORTS,
                           categories=categories, filtered=filtered, total=len(ranked))


MAX_REVIEW = 500
MIN_REVIEW = 3


def get_place_or_404(place_id):
    row = get_db().execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    if row is None:
        abort(404, description=f"There is no place with id {place_id}. "
                               "It may have been removed, or the link is wrong.")
    return row


def render_place(place_row, form=None, status=200):
    """Place page: summary, the reviews, and the current user's own review form."""
    db_ = get_db()
    stats = db_.execute(
        "SELECT ROUND(AVG(rating), 2) AS avg_rating, COUNT(*) AS n_reviews "
        "FROM reviews WHERE place_id = ?", (place_row["id"],)
    ).fetchone()
    reviews = db_.execute(
        "SELECT r.*, u.username FROM reviews r JOIN users u ON u.id = r.user_id "
        "WHERE r.place_id = ? ORDER BY r.updated_at DESC, r.id DESC", (place_row["id"],)
    ).fetchall()
    # Ratings histogram for the chart: how many 5-star, 4-star, ... reviews.
    counts = {i: 0 for i in range(1, 6)}
    for r in reviews:
        counts[r["rating"]] += 1
    top = max(counts.values()) or 1
    histogram = [{"stars": i, "count": counts[i], "pct": round(100 * counts[i] / top)}
                 for i in range(5, 0, -1)]
    mine = None
    if g.user:
        mine = next((r for r in reviews if r["user_id"] == g.user["id"]), None)
    if form is None:
        form = {"rating": mine["rating"] if mine else "", "body": mine["body"] if mine else ""}
    return render_template("place.html", place=place_row, stats=stats, reviews=reviews,
                           mine=mine, form=form, max_review=MAX_REVIEW,
                           histogram=histogram), status


@app.route("/place/<int:place_id>")
def place(place_id):
    return render_place(get_place_or_404(place_id))


def validate_review(form):
    errors = []
    try:
        rating = int(form.get("rating", ""))
    except ValueError:
        rating = None
    if rating is None or not 1 <= rating <= 5:
        errors.append("Pick a rating from 1 to 5 stars.")
    body = form.get("body", "").strip()
    if len(body) < MIN_REVIEW:
        errors.append(f"Write a short review (at least {MIN_REVIEW} characters).")
    elif len(body) > MAX_REVIEW:
        errors.append(f"Keep your review under {MAX_REVIEW} characters "
                      f"(yours has {len(body)}).")
    return rating, body, errors


@app.route("/place/<int:place_id>/review", methods=["POST"])
@login_required
def save_review(place_id):
    """Create the user's review, or update it if they already have one."""
    place_row = get_place_or_404(place_id)
    rating, body, errors = validate_review(request.form)
    if errors:
        for e in errors:
            flash(e, "error")
        return render_place(place_row, form=request.form, status=400)
    db_ = get_db()
    existed = db_.execute("SELECT 1 FROM reviews WHERE place_id = ? AND user_id = ?",
                          (place_id, g.user["id"])).fetchone()
    # Upsert: the UNIQUE(place_id, user_id) constraint guarantees one review per
    # user per place even if the form is submitted twice at the same moment.
    db_.execute(
        "INSERT INTO reviews (place_id, user_id, rating, body) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (place_id, user_id) DO UPDATE SET rating = excluded.rating, "
        "body = excluded.body, updated_at = datetime('now')",
        (place_id, g.user["id"], rating, body))
    db_.commit()
    flash("Your review was updated." if existed else "Thanks! Your review is posted.", "success")
    return redirect(url_for("place", place_id=place_id) + "#your-review")


@app.route("/place/<int:place_id>/review/delete", methods=["POST"])
@login_required
def delete_review(place_id):
    get_place_or_404(place_id)
    db_ = get_db()
    cur = db_.execute("DELETE FROM reviews WHERE place_id = ? AND user_id = ?",
                      (place_id, g.user["id"]))
    db_.commit()
    if cur.rowcount:
        flash("Your review was deleted.", "info")
    else:
        flash("You had no review to delete for this place.", "error")
    return redirect(url_for("place", place_id=place_id))


@app.route("/places/new", methods=["GET", "POST"])
@login_required
def new_place():
    db_ = get_db()
    categories = [r["category"] for r in db_.execute(
        "SELECT DISTINCT category FROM places ORDER BY category COLLATE NOCASE")]
    form = {"name": "", "category": "", "location": "", "price": "2", "description": ""}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in form}
        errors = []
        if not 2 <= len(form["name"]) <= 60:
            errors.append("Name must be 2–60 characters.")
        if not 2 <= len(form["category"]) <= 30:
            errors.append("Category must be 2–30 characters (e.g. Pizza, Coffee, Thai).")
        if not 2 <= len(form["location"]) <= 80:
            errors.append("Say where it is (2–80 characters), e.g. “Student Union, 1st floor”.")
        if form["price"] not in ("1", "2", "3"):
            errors.append("Pick a price level: $, $$ or $$$.")
        if len(form["description"]) > 300:
            errors.append("Keep the description under 300 characters.")
        if not errors:
            dup = db_.execute("SELECT id FROM places WHERE name = ?", (form["name"],)).fetchone()
            if dup:
                flash(f"“{form['name']}” is already listed, so here it is.", "info")
                return redirect(url_for("place", place_id=dup["id"]))
            # Reuse the existing spelling of a category ("pizza" -> "Pizza").
            match = next((c for c in categories if c.casefold() == form["category"].casefold()), None)
            try:
                cur = db_.execute(
                    "INSERT INTO places (name, category, location, price, description, created_by) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (form["name"], match or form["category"], form["location"],
                     int(form["price"]), form["description"], g.user["id"]),
                )
                db_.commit()
            except sqlite3.IntegrityError:      # someone added the same name just now
                db_.rollback()
                flash(f"“{form['name']}” was just added by someone else.", "info")
                return redirect(url_for("index", q=form["name"]))
            flash(f"{form['name']} was added. Why not leave the first review?", "success")
            return redirect(url_for("place", place_id=cur.lastrowid) + "#your-review")
        for e in errors:
            flash(e, "error")
        return render_template("new_place.html", form=form, categories=categories), 400
    return render_template("new_place.html", form=form, categories=categories)


@app.route("/u/<username>")
def user_page(username):
    db_ = get_db()
    user = db_.execute("SELECT id, username, created_at FROM users WHERE username = ?",
                       (username,)).fetchone()
    if user is None:
        abort(404, description=f"There is no user called “{username}”.")
    reviews = db_.execute(
        "SELECT r.*, p.name AS place_name, p.category FROM reviews r "
        "JOIN places p ON p.id = r.place_id WHERE r.user_id = ? "
        "ORDER BY r.updated_at DESC, r.id DESC", (user["id"],)
    ).fetchall()
    avg = round(sum(r["rating"] for r in reviews) / len(reviews), 2) if reviews else None
    return render_template("user.html", user=user, reviews=reviews, avg=avg)


@app.route("/about")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
