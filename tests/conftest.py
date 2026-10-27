import os
import re
import sqlite3
import sys
import tempfile

import pytest

# Never touch the real database, and start every test with an empty one.
os.environ["AUTO_SEED"] = "0"
os.environ["DATABASE"] = os.path.join(tempfile.mkdtemp(), "import.db")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db as db_module  # noqa: E402
from app import app as flask_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    path = str(tmp_path / "test.db")
    flask_app.config.update(TESTING=True, DATABASE=path)
    db_module.init_db(path)
    conn = sqlite3.connect(path)
    conn.executemany(
        "INSERT INTO places (name, category, location, price) VALUES (?, ?, ?, ?)",
        [("Alpha Tacos", "Mexican", "North Gate", 1),
         ("Beta Burgers", "Burgers", "Stadium", 2),
         ("Gamma Coffee", "Coffee", "Library", 2)],
    )
    conn.commit()
    conn.close()
    yield flask_app


@pytest.fixture
def query(app):
    def run(sql, *args):
        conn = sqlite3.connect(app.config["DATABASE"])
        try:
            return conn.execute(sql, args).fetchall()
        finally:
            conn.close()
    return run


class Browser:
    """A test client that remembers the CSRF token, like a real browser tab."""

    def __init__(self, client):
        self.c = client

    def token(self):
        html = self.c.get("/login" if not self.logged_in() else "/").get_data(as_text=True)
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def logged_in(self):
        with self.c.session_transaction() as s:
            return "user_id" in s

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, csrf=True, **kw):
        data = dict(data or {})
        if csrf:
            data["csrf_token"] = self.token()
        return self.c.post(url, data=data, **kw)

    def register(self, username, password="password123"):
        return self.post("/register", {"username": username, "password": password,
                                       "confirm": password})

    def login(self, username, password="password123"):
        return self.post("/login", {"username": username, "password": password})


@pytest.fixture
def browser(app):
    return Browser(app.test_client())


@pytest.fixture
def other_browser(app):
    return Browser(app.test_client())
