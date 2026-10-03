"""Bug reports and ideas from the 💬 button, and the page that lists them."""

import json

KINDS = {"bug": "🐞 Bug", "idea": "💡 Idea", "fact": "📚 Wrong fact"}
MAX_MESSAGE = 2000
MAX_CONTEXT = 2000
OWNER_ID = 1  # the site's first account sees everyone's reports; others see their own


class FeedbackError(ValueError):
    pass


def save(db, user_id, kind, message, page, context):
    message = (message or "").strip()
    if kind not in KINDS:
        raise FeedbackError("Pick bug, idea or wrong fact.")
    if not message:
        raise FeedbackError("Write a few words about it.")
    context_json = json.dumps(context if isinstance(context, dict) else {}, ensure_ascii=False)
    db.execute(
        "INSERT INTO feedback (user_id, kind, message, page, context) VALUES (?, ?, ?, ?, ?)",
        (user_id, kind, message[:MAX_MESSAGE], str(page or "")[:200], context_json[:MAX_CONTEXT]),
    )
    db.commit()


def listing(db, user_id):
    """Reports this player may see, open ones first, newest first."""
    rows = db.execute(
        """SELECT f.id, f.kind, f.message, f.page, f.context, f.done, f.created_at, u.name
           FROM feedback f JOIN users u ON u.id = f.user_id
           WHERE ? = ? OR f.user_id = ?
           ORDER BY f.done, f.id DESC""",
        (user_id, OWNER_ID, user_id),
    ).fetchall()
    return [{**dict(r), "context": json.loads(r["context"]), "label": KINDS.get(r["kind"], r["kind"])} for r in rows]


def set_done(db, user_id, feedback_id, done):
    """The owner can tick off anything; others only their own reports."""
    db.execute("UPDATE feedback SET done = ? WHERE id = ? AND (? = ? OR user_id = ?)",
               (int(done), feedback_id, user_id, OWNER_ID, user_id))
    db.commit()
