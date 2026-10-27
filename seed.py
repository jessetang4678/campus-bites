"""Fill an empty database with fictitious places, users and reviews.

    python seed.py            # seed only if there are no places yet
    python seed.py --reset    # wipe everything and seed again

All names are made up. The demo account is  demo / campusbites.
"""
import random
import secrets
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from werkzeug.security import generate_password_hash


DEMO_USER = ("demo", "campusbites")

# name, category, location, price, description, typical quality (1-5), dishes
PLACES = [
    ("The Hungry Owl", "Diner", "Student Union, ground floor", 1,
     "All-day breakfast and late-night fries, open until 2am during finals.", 4.3,
     ["pancakes", "breakfast burrito", "cheese fries", "patty melt"]),
    ("Taqueria El Patio", "Mexican", "North Gate, across from the bike shop", 1,
     "Counter-service tacos with a salsa bar that never runs out.", 4.6,
     ["al pastor tacos", "carnitas burrito", "horchata", "chips and salsa verde"]),
    ("Bao Down", "Chinese", "Engineering Quad food truck row", 2,
     "Steamed buns and dumplings from a bright red truck.", 4.1,
     ["pork belly bao", "soup dumplings", "scallion pancake", "chili oil wontons"]),
    ("Slice of Heaven", "Pizza", "University Ave & 3rd", 1,
     "Huge New York style slices, cash only before noon.", 3.8,
     ["pepperoni slice", "margherita slice", "garlic knots", "white pie"]),
    ("Grounds for Concern", "Coffee", "Library, 2nd floor", 2,
     "The study-break coffee bar inside the library.", 3.4,
     ["oat latte", "cold brew", "blueberry muffin", "chai"]),
    ("Pho Sure", "Vietnamese", "El Camino plaza", 2,
     "Big steaming bowls, fast service, plenty of tables.", 4.4,
     ["pho tai", "lemongrass vermicelli", "banh mi", "spring rolls"]),
    ("Commons Dining Hall", "Dining hall", "West Campus residences", 1,
     "The all-you-can-eat dining hall. Meal swipes accepted.", 2.7,
     ["stir-fry station", "pasta bar", "Sunday brunch", "salad bar"]),
    ("Curry Up Now-ish", "Indian", "Behind the Science Library", 2,
     "Rotating thali, generous rice portions.", 4.2,
     ["chicken tikka masala", "chana masala", "garlic naan", "mango lassi"]),
    ("Sakura Roll", "Japanese", "University Ave & 5th", 3,
     "Sit-down sushi spot, popular for birthdays.", 3.9,
     ["spicy tuna roll", "salmon nigiri", "chicken katsu", "miso soup"]),
    ("Green Bowl Co.", "Salads", "Student Union, 2nd floor", 2,
     "Build-your-own salads and grain bowls.", 3.6,
     ["harvest bowl", "kale caesar", "falafel bowl", "lemonade"]),
    ("Burger Lab", "Burgers", "Next to the stadium", 2,
     "Smash burgers and milkshakes, busy on game days.", 4.0,
     ["double smash burger", "veggie burger", "sweet potato fries", "black and white shake"]),
    ("Late Night Gyro", "Mediterranean", "Fraternity Row cart", 1,
     "Cart that shows up after 9pm. Follow the smell.", 4.5,
     ["lamb gyro", "chicken shawarma plate", "falafel wrap", "baklava"]),
    ("The Quad Café", "Café", "Main Quad, under the arches", 2,
     "Sandwiches and pastries with outdoor seating.", 3.3,
     ["turkey pesto sandwich", "croissant", "tomato soup", "iced tea"]),
    ("Seoul Food", "Korean", "El Camino plaza", 2,
     "Bibimbap, fried chicken and a very good kimchi stew.", 4.7,
     ["bibimbap", "Korean fried chicken", "kimchi jjigae", "japchae"]),
]

USERNAMES = [
    "maya_r", "jtran", "sam_eats", "priya42", "luke_w", "noodle_queen",
    "dev_ops_dan", "hannah_b", "carlos_m", "aisha_k", "ben_runs",
    "tofu_tom", "zoe_l", "kenji", "marco_polo", "ella_f",
]

GOOD = [
    "The {dish} is the best on campus, no contest.",
    "Came for the {dish}, will absolutely come back.",
    "Fast, friendly and the {dish} was perfect.",
    "My go-to after late labs. Get the {dish}.",
    "Honestly worth the walk. The {dish} is unreal.",
    "Great value for students. {Dish} was huge.",
]
OK = [
    "Solid. The {dish} was fine but nothing special.",
    "Decent {dish}, long line at lunch though.",
    "Good when you're in a hurry. {Dish} hit the spot.",
    "A bit pricey, but the {dish} was tasty.",
    "Hit or miss. Today the {dish} was a hit.",
]
BAD = [
    "The {dish} was cold and the wait was 30 minutes.",
    "Overpriced for what you get. Skip the {dish}.",
    "Not great. The {dish} tasted reheated.",
    "Wanted to like it, but the {dish} was bland.",
]


def review_text(rng, rating, dish):
    pool = GOOD if rating >= 4 else OK if rating == 3 else BAD
    return rng.choice(pool).format(dish=dish, Dish=dish[0].upper() + dish[1:])


def seed(conn, rng=None):
    rng = rng or random.Random(2026)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    user_ids = []
    demo_name, demo_pw = DEMO_USER
    for name in [demo_name] + USERNAMES:
        # Fictitious users get random passwords nobody knows; only demo can log in.
        pw = demo_pw if name == demo_name else secrets.token_urlsafe(16)
        joined = now - timedelta(days=rng.randint(60, 400))
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (name, generate_password_hash(pw), joined.strftime("%Y-%m-%d %H:%M:%S")),
        )
        user_ids.append(cur.lastrowid)
    reviewers = user_ids[1:]          # leave the demo account empty to play with

    n_reviews = 0
    for name, cat, loc, price, desc, quality, dishes in PLACES:
        cur = conn.execute(
            "INSERT INTO places (name, category, location, price, description) "
            "VALUES (?, ?, ?, ?, ?)", (name, cat, loc, price, desc))
        place_id = cur.lastrowid
        for uid in rng.sample(reviewers, rng.randint(4, 11)):
            rating = max(1, min(5, round(rng.gauss(quality, 0.9))))
            when = now - timedelta(days=rng.randint(1, 120), minutes=rng.randint(0, 1440))
            stamp = when.strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                "INSERT INTO reviews (place_id, user_id, rating, body, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (place_id, uid, rating, review_text(rng, rating, rng.choice(dishes)), stamp, stamp))
            n_reviews += 1
    conn.commit()
    return len(user_ids), len(PLACES), n_reviews


def seed_if_empty(path):
    # BEGIN IMMEDIATE takes the write lock first, so two server processes
    # starting at once can't both decide the database is empty.
    conn = sqlite3.connect(path, timeout=30, isolation_level=None)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT COUNT(*) FROM places").fetchone()[0] == 0:
            return seed(conn)
        conn.execute("ROLLBACK")
    finally:
        conn.close()
    return None


if __name__ == "__main__":
    from app import app  # noqa: E402  (creates the tables)
    path = app.config["DATABASE"]
    if "--reset" in sys.argv:
        conn = sqlite3.connect(path)
        conn.executescript("DELETE FROM reviews; DELETE FROM places; DELETE FROM users;"
                           "DELETE FROM sqlite_sequence;")
        conn.commit()
        conn.close()
    result = seed_if_empty(path)
    if result:
        print("Seeded %d users, %d places, %d reviews into %s" % (*result, path))
    else:
        print(f"{path} already has places; nothing to do (use --reset to start over).")
    print("Demo login: %s / %s" % DEMO_USER)
