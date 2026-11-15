"""LAN HUB — локальний інтерактивний сайт на Flask + SQLite.

Запуск: python app.py
Телефон: http://IP_КОМПЮТЕРА:5000 (у тій самій Wi-Fi/LAN мережі)
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
import time

from flask import Flask, jsonify, render_template, request

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "lanhub.db"
POLL_CHOICES = ("light", "game", "ai")
REACTIONS = ("🔥", "🚀", "💜", "👏")

app = Flask(__name__)
app.json.ensure_ascii = False
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024  # Достатньо для коротких JSON-запитів


@contextmanager
def db_connection():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db():
    with db_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS votes (
                client_id TEXT PRIMARY KEY,
                choice TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reactions (
                emoji TEXT PRIMARY KEY,
                total INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS clients (
                client_id TEXT PRIMARY KEY,
                last_seen INTEGER NOT NULL
            );
            """
        )
        if db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0:
            db.execute(
                "INSERT INTO messages (name, body, created_at) VALUES (?, ?, ?)",
                (
                    "LAN HUB",
                    "Вітаємо! 👋 Відкрий цей сайт із телефона та напиши щось — повідомлення побачать усі підключені пристрої.",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )


def valid_client_id(value):
    return isinstance(value, str) and re.fullmatch(r"[a-zA-Z0-9_-]{8,80}", value) is not None


def body_json():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def state():
    client_id = request.args.get("client_id", "")
    with db_connection() as db:
        latest = db.execute(
            "SELECT id, name, body, created_at FROM messages ORDER BY id DESC LIMIT 40"
        ).fetchall()
        counts = {choice: 0 for choice in POLL_CHOICES}
        for row in db.execute("SELECT choice, COUNT(*) AS n FROM votes GROUP BY choice"):
            if row["choice"] in counts:
                counts[row["choice"]] = row["n"]
        reaction_counts = {emoji: 0 for emoji in REACTIONS}
        for row in db.execute("SELECT emoji, total FROM reactions"):
            if row["emoji"] in reaction_counts:
                reaction_counts[row["emoji"]] = row["total"]
        vote_row = (
            db.execute("SELECT choice FROM votes WHERE client_id = ?", (client_id,)).fetchone()
            if valid_client_id(client_id) else None
        )
        online = db.execute(
            "SELECT COUNT(*) FROM clients WHERE last_seen >= ?", (int(time.time()) - 25,)
        ).fetchone()[0]

    return jsonify(
        messages=[dict(row) for row in reversed(latest)],
        votes=counts,
        reactions=reaction_counts,
        my_vote=vote_row["choice"] if vote_row else None,
        online=online,
    )


@app.post("/api/message")
def add_message():
    data = body_json()
    name = data.get("name", "")
    body = data.get("body", "")
    if not isinstance(name, str) or not 2 <= len(name.strip()) <= 26:
        return jsonify(error="Ім’я має містити від 2 до 26 символів."), 400
    if not isinstance(body, str) or not 1 <= len(body.strip()) <= 240:
        return jsonify(error="Повідомлення має містити від 1 до 240 символів."), 400

    with db_connection() as db:
        db.execute(
            "INSERT INTO messages (name, body, created_at) VALUES (?, ?, ?)",
            (name.strip(), body.strip(), datetime.now(timezone.utc).isoformat()),
        )
    return jsonify(ok=True), 201


@app.post("/api/vote")
def vote():
    data = body_json()
    client_id, choice = data.get("client_id"), data.get("choice")
    if not valid_client_id(client_id) or choice not in POLL_CHOICES:
        return jsonify(error="Некоректне голосування."), 400
    with db_connection() as db:
        db.execute(
            """INSERT INTO votes (client_id, choice) VALUES (?, ?)
               ON CONFLICT(client_id) DO UPDATE SET choice = excluded.choice""",
            (client_id, choice),
        )
    return jsonify(ok=True)


@app.post("/api/reaction")
def reaction():
    data = body_json()
    emoji = data.get("emoji")
    if emoji not in REACTIONS:
        return jsonify(error="Невідома реакція."), 400
    with db_connection() as db:
        db.execute(
            """INSERT INTO reactions (emoji, total) VALUES (?, 1)
               ON CONFLICT(emoji) DO UPDATE SET total = total + 1""",
            (emoji,),
        )
    return jsonify(ok=True)


@app.post("/api/ping")
def ping():
    client_id = body_json().get("client_id")
    if not valid_client_id(client_id):
        return jsonify(error="Некоректний ідентифікатор."), 400
    now = int(time.time())
    with db_connection() as db:
        db.execute(
            """INSERT INTO clients (client_id, last_seen) VALUES (?, ?)
               ON CONFLICT(client_id) DO UPDATE SET last_seen = excluded.last_seen""",
            (client_id, now),
        )
        db.execute("DELETE FROM clients WHERE last_seen < ?", (now - 90,))
    return jsonify(ok=True)


if __name__ == "__main__":
    init_db()
    print("\nLAN HUB запущено! Відкрий http://IP_КОМПЮТЕРА:5000 на телефоні.\n")
    # Тільки для локальної довіреної мережі, не для відкритого Інтернету.
    app.run(host="0.0.0.0", port=5000, debug=False)
else:
    init_db()
