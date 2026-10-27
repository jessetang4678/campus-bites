"""Campus Bites: rate the places to eat on and around campus."""
import os

from flask import Flask, abort, render_template

import db
from db import get_db

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["DATABASE"] = os.environ.get(
    "DATABASE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "campus_bites.db")
)
db.init_app(app)

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


@app.route("/place/<int:place_id>")
def place(place_id):
    row = get_db().execute("SELECT * FROM places WHERE id = ?", (place_id,)).fetchone()
    if row is None:
        abort(404)
    return render_template("place.html", place=row)


@app.route("/about")
def about():
    return render_template("about.html")


if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5000)))
