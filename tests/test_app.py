import sqlite3

import seed
import db as db_module


# ---------------------------------------------------------------- pages

def test_home_and_about_pages(browser):
    home = browser.get("/")
    assert home.status_code == 200
    assert "Alpha Tacos" in home.get_data(as_text=True)
    assert browser.get("/about").status_code == 200


def test_missing_things_give_clear_404s(browser):
    r = browser.get("/place/999")
    assert r.status_code == 404
    assert "no place with id 999" in r.get_data(as_text=True)
    r = browser.get("/u/nobody")
    assert r.status_code == 404
    assert "no user called" in r.get_data(as_text=True)
    assert browser.get("/no/such/page").status_code == 404


# ---------------------------------------------------------------- accounts

def test_register_login_logout(browser, query):
    r = browser.register("alice")
    assert r.status_code == 302
    assert query("SELECT username FROM users") == [("alice",)]
    assert "My reviews" in browser.get("/").get_data(as_text=True)
    assert browser.post("/logout").status_code == 302
    assert "Log in" in browser.get("/").get_data(as_text=True)
    assert browser.login("ALICE").status_code == 302          # usernames ignore case


def test_password_is_hashed(browser, query):
    browser.register("alice", "secret-pass")
    (stored,), = query("SELECT password_hash FROM users")
    assert "secret-pass" not in stored


def test_register_validation(browser, other_browser, query):
    r = browser.register("a!", "short")
    assert r.status_code == 400
    text = r.get_data(as_text=True)
    assert "Username must be" in text and "at least 8" in text
    browser.register("alice")
    r = other_browser.register("Alice")
    assert r.status_code == 400
    assert "already taken" in r.get_data(as_text=True)
    assert query("SELECT COUNT(*) FROM users") == [(1,)]


def test_wrong_password(browser):
    browser.register("alice")
    browser.post("/logout")
    r = browser.login("alice", "wrong-password")
    assert r.status_code == 400
    assert "Wrong username or password" in r.get_data(as_text=True)


def test_forms_need_csrf_token(browser, query):
    r = browser.post("/register", {"username": "mallory", "password": "password123",
                                   "confirm": "password123"}, csrf=False)
    assert r.status_code == 400
    assert query("SELECT COUNT(*) FROM users") == [(0,)]


def test_login_next_only_redirects_on_site(browser):
    browser.register("alice")
    browser.post("/logout")
    r = browser.post("/login?next=//evil.example", {"username": "alice",
                                                    "password": "password123"})
    assert r.headers["Location"] == "/"


# ---------------------------------------------------------------- reviews

def test_only_logged_in_users_can_review(browser, query):
    r = browser.post("/place/1/review", {"rating": "5", "body": "Great"})
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert query("SELECT COUNT(*) FROM reviews") == [(0,)]


def test_one_review_per_place_and_editing(browser, query):
    browser.register("alice")
    assert browser.post("/place/1/review", {"rating": "5", "body": "Great tacos"}).status_code == 302
    assert browser.post("/place/1/review", {"rating": "3", "body": "Changed my mind"}).status_code == 302
    assert query("SELECT rating, body FROM reviews") == [(3, "Changed my mind")]


def test_review_validation(browser, query):
    browser.register("alice")
    for data in ({"rating": "6", "body": "Fine food"}, {"rating": "x", "body": "Fine"},
                 {"rating": "4", "body": ""}, {"rating": "4", "body": "x" * 501}):
        r = browser.post("/place/1/review", data)
        assert r.status_code == 400
        assert "flash-error" in r.get_data(as_text=True)
    assert query("SELECT COUNT(*) FROM reviews") == [(0,)]
    assert browser.post("/place/999/review", {"rating": "4", "body": "ok ok"}).status_code == 404


def test_users_only_delete_their_own_review(browser, other_browser, query):
    browser.register("alice")
    other_browser.register("bob")
    browser.post("/place/1/review", {"rating": "5", "body": "Alice loves it"})
    other_browser.post("/place/1/review", {"rating": "1", "body": "Bob does not"})
    other_browser.post("/place/1/review/delete")
    assert query("SELECT body FROM reviews") == [("Alice loves it",)]


def test_average_chart_and_ranking(browser, other_browser):
    browser.register("alice")
    other_browser.register("bob")
    browser.post("/place/2/review", {"rating": "5", "body": "Best burger"})
    other_browser.post("/place/2/review", {"rating": "4", "body": "Pretty good"})
    browser.post("/place/1/review", {"rating": "3", "body": "Okay tacos"})

    page = browser.get("/place/2").get_data(as_text=True)
    assert "4.5" in page and "average of 2 reviews" in page
    assert "5 stars 1, 4 stars 1, 3 stars 0" in page          # chart's accessible label

    home = browser.get("/").get_data(as_text=True)
    assert home.index("Beta Burgers") < home.index("Alpha Tacos") < home.index("Gamma Coffee")


def test_user_page_lists_reviews(browser):
    browser.register("alice")
    browser.post("/place/1/review", {"rating": "4", "body": "Nice salsa"})
    page = browser.get("/u/alice").get_data(as_text=True)
    assert "Nice salsa" in page and "Alpha Tacos" in page


# ---------------------------------------------------------------- search, places

def test_search_and_filter(browser):
    text = browser.get("/?q=coffee").get_data(as_text=True)
    assert "Gamma Coffee" in text and "Alpha Tacos" not in text
    text = browser.get("/?category=Burgers").get_data(as_text=True)
    assert "Beta Burgers" in text and "Gamma Coffee" not in text
    assert "No places match" in browser.get("/?q=zzzz").get_data(as_text=True)
    assert browser.get("/?sort=nonsense").status_code == 200


def test_add_place(browser, query):
    assert "/login" in browser.get("/places/new").headers["Location"]
    browser.register("alice")
    r = browser.post("/places/new", {"name": "", "category": "", "location": "", "price": "9"})
    assert r.status_code == 400
    r = browser.post("/places/new", {"name": "Delta Deli", "category": "coffee",
                                     "location": "Main St", "price": "1"})
    assert r.status_code == 302
    assert query("SELECT category FROM places WHERE name = 'Delta Deli'") == [("Coffee",)]
    r = browser.post("/places/new", {"name": "delta deli", "category": "Deli",
                                     "location": "Elsewhere", "price": "2"})
    assert r.status_code == 302                                 # sent to existing place
    assert query("SELECT COUNT(*) FROM places") == [(4,)]


# ---------------------------------------------------------------- persistence, seeding

def test_data_survives_a_restart(app, browser):
    browser.register("alice")
    browser.post("/place/1/review", {"rating": "5", "body": "Persistent"})
    # A brand-new connection (as after a server restart) still sees it.
    db_module.init_db(app.config["DATABASE"])                   # startup must not wipe
    conn = sqlite3.connect(app.config["DATABASE"])
    assert conn.execute("SELECT body FROM reviews").fetchall() == [("Persistent",)]
    conn.close()


def test_seed_fills_empty_db_once(tmp_path):
    path = str(tmp_path / "seed.db")
    db_module.init_db(path)
    users, places, reviews = seed.seed_if_empty(path)
    assert places == len(seed.PLACES) and reviews > places
    assert seed.seed_if_empty(path) is None                     # second run does nothing
