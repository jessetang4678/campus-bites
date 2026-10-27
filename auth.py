"""Accounts: register, log in, log out, plus the login_required decorator."""
import functools
import hmac
import re
import secrets
import sqlite3

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,20}$")
MIN_PASSWORD = 8


# ---------------------------------------------------------------- helpers

def load_user():
    """Runs before every request: put the logged-in user (or None) on g."""
    user_id = session.get("user_id")
    g.user = None
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT id, username, created_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if g.user is None:          # account no longer exists
            session.clear()


def login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to do that.", "info")
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)
    return wrapped


def csrf_token():
    """A per-session secret every form posts back, so other sites can't post for you."""
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def check_csrf():
    if request.method != "POST":
        return
    sent = request.form.get("csrf_token", "")
    expected = session.get("csrf", "")
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, description="Your form expired or was sent from another site. "
                               "Please go back, reload the page and try again.")


def safe_next(target):
    """Only follow `next` to a page on this site."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("index")


# ---------------------------------------------------------------- views

@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("index"))
    errors = []
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if not USERNAME_RE.match(username):
            errors.append("Username must be 3–20 characters: letters, numbers or underscores.")
        if len(password) < MIN_PASSWORD:
            errors.append(f"Password must be at least {MIN_PASSWORD} characters.")
        if password != confirm:
            errors.append("The two passwords do not match.")
        db = get_db()
        if not errors and db.execute(
                "SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
            errors.append(f"The username “{username}” is already taken.")
        if not errors:
            try:
                cur = db.execute(
                    "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                    (username, generate_password_hash(password)),
                )
                db.commit()
            except sqlite3.IntegrityError:   # taken a moment ago by someone else
                db.rollback()
                flash(f"The username “{username}” is already taken.", "error")
                return render_template("register.html", username=username), 400
            session.clear()
            session["user_id"] = cur.lastrowid
            flash(f"Welcome to Campus Bites, {username}!", "success")
            return redirect(url_for("index"))
        for e in errors:
            flash(e, "error")
    return render_template("register.html", username=username), (400 if errors else 200)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("index"))
    username = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Wrong username or password.", "error")
            return render_template("login.html", username=username), 400
        session.clear()
        session["user_id"] = user["id"]
        flash(f"Welcome back, {user['username']}.", "success")
        return redirect(safe_next(request.args.get("next")))
    return render_template("login.html", username=username)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You are logged out.", "info")
    return redirect(url_for("index"))
