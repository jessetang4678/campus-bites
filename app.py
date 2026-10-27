"""Campus Bites: rate the places to eat on and around campus."""
import os

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

import auth
import db
from auth import login_required
from db import get_db

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["DATABASE"] = os.environ.get(
    "DATABASE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "campus_bites.db")
)
db.init_app(app)

app.register_blueprint(auth.bp)
app.before_request(auth.load_user)
app.before_request(auth.check_csrf)
app.jinja_env.globals["csrf_token"] = auth.csrf_token

# Average rating, number of reviews; ties go to the place with more reviews,
# places nobody has reviewed yet come last.
RANKING_SQL = """
    SELECT p.*, ROUND(AVG(r.rating), 2) AS avg_rating, COUNT(r.id) AS n_reviews
    FROM places p LEFT JOIN reviews r ON r.place_id = p.id
    GROUP BY p.id
    ORDER BY (COUNT(r.id) = 0), avg_rating DESC, n_reviews DESC, p.name COLLATE NOCASE
"""


@app.route("/")
def index():
    places = get_db().execute(RANKING_SQL).fetchall()
    return render_template("index.html", places=places)


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
    existing = db_.execute("SELECT id FROM reviews WHERE place_id = ? AND user_id = ?",
                           (place_id, g.user["id"])).fetchone()
    if existing:
        db_.execute("UPDATE reviews SET rating = ?, body = ?, updated_at = datetime('now') "
                    "WHERE id = ?", (rating, body, existing["id"]))
        flash("Your review was updated.", "success")
    else:
        db_.execute("INSERT INTO reviews (place_id, user_id, rating, body) VALUES (?, ?, ?, ?)",
                    (place_id, g.user["id"], rating, body))
        flash("Thanks! Your review is posted.", "success")
    db_.commit()
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
