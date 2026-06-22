"""
Message statistics manager.

Keeps the legacy message_stats table compatible while recording detailed
message_events for inbound, outbound and postback activity.
"""

import os
import sqlite3
import sys
from typing import Dict, List, Optional, Tuple

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DB_DIR = os.path.join(BASE_DIR, "database")
os.makedirs(DB_DIR, exist_ok=True)
DB_PATH = os.path.join(DB_DIR, "plates.db")

MESSAGE_PREVIEW_LIMIT = 300
_INITIALIZED = False


def _connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return conn


def _preview(text) -> Tuple[Optional[str], int]:
    if text is None:
        return None, 0
    value = str(text)
    clean = value.replace("\r", " ").replace("\n", " ").strip()
    if len(clean) > MESSAGE_PREVIEW_LIMIT:
        clean = clean[:MESSAGE_PREVIEW_LIMIT]
    return clean, len(value)


def _safe_context(runtime_context=None) -> Dict:
    ctx = runtime_context or {}
    if not isinstance(ctx, dict):
        return {}
    last = ctx.get("last_pipeline_stats") or {}
    if not isinstance(last, dict):
        last = {}

    def pick(*keys, default=None):
        for key in keys:
            if key in last and last.get(key) not in (None, ""):
                return last.get(key)
            if key in ctx and ctx.get(key) not in (None, ""):
                return ctx.get(key)
        return default

    return {
        "skill": pick("skill", "ai_skill"),
        "business_domain": pick("business_domain", "domain"),
        "intent": pick("intent"),
        "action": pick("action"),
        "provider": pick("provider", "ai_provider"),
        "model": pick("model", "ai_model"),
        "rag_source": pick("rag_source"),
        "rag_used": 1 if pick("rag_used", default=False) else 0,
        "rag_hit_count": int(pick("rag_hit_count", default=0) or 0),
        "queue_wait_ms": pick("queue_wait_ms"),
        "processing_ms": pick("processing_ms"),
        "ai_latency_ms": pick("ai_latency_ms"),
        "send_latency_ms": pick("send_latency_ms"),
        "total_latency_ms": pick("total_latency_ms"),
    }


def _add_column(cursor, table: str, column_sql: str):
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_sql}")
    except sqlite3.OperationalError:
        pass


def init_message_stats_table():
    """Create and migrate message statistics tables."""
    global _INITIALIZED
    if _INITIALIZED:
        return
    conn = _connect()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS message_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id TEXT NOT NULL,
                sender_psid TEXT NOT NULL,
                sender_name TEXT,
                message_count INTEGER DEFAULT 0,
                first_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_message_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(page_id, sender_psid)
            )
            """
        )

        for column_sql in [
            "inbound_count INTEGER DEFAULT 0",
            "outbound_count INTEGER DEFAULT 0",
            "postback_count INTEGER DEFAULT 0",
            "first_inbound_at TIMESTAMP",
            "last_inbound_at TIMESTAMP",
            "last_outbound_at TIMESTAMP",
            "last_skill TEXT",
            "last_domain TEXT",
            "last_intent TEXT",
            "last_action TEXT",
            "avg_response_ms INTEGER DEFAULT 0",
            "last_response_ms INTEGER DEFAULT 0",
        ]:
            _add_column(cursor, "message_stats", column_sql)

        cursor.execute(
            """
            UPDATE message_stats
            SET inbound_count = message_count,
                first_inbound_at = COALESCE(first_inbound_at, first_message_at),
                last_inbound_at = COALESCE(last_inbound_at, last_message_at)
            WHERE COALESCE(message_count, 0) > COALESCE(inbound_count, 0)
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS message_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                page_id TEXT NOT NULL,
                sender_psid TEXT,
                sender_name TEXT,
                message_mid TEXT,
                direction TEXT NOT NULL,
                event_type TEXT DEFAULT 'message',
                message_text_preview TEXT,
                text_length INTEGER DEFAULT 0,
                skill TEXT,
                business_domain TEXT,
                intent TEXT,
                action TEXT,
                provider TEXT,
                model TEXT,
                rag_source TEXT,
                rag_used INTEGER DEFAULT 0,
                rag_hit_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'success',
                error_message TEXT,
                queue_wait_ms INTEGER,
                processing_ms INTEGER,
                ai_latency_ms INTEGER,
                send_latency_ms INTEGER,
                total_latency_ms INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(page_id, message_mid, direction)
            )
            """
        )

        for sql in [
            "CREATE INDEX IF NOT EXISTS idx_message_stats_page ON message_stats(page_id)",
            "CREATE INDEX IF NOT EXISTS idx_message_stats_sender ON message_stats(sender_psid)",
            "CREATE INDEX IF NOT EXISTS idx_message_events_page_created ON message_events(page_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_message_events_sender ON message_events(page_id, sender_psid)",
            "CREATE INDEX IF NOT EXISTS idx_message_events_skill ON message_events(skill, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_message_events_direction ON message_events(direction, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_message_events_action ON message_events(action, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_message_events_intent ON message_events(intent, created_at)",
        ]:
            cursor.execute(sql)
        conn.commit()
        _INITIALIZED = True
        print("Message stats tables initialized")
    except Exception as exc:
        print(f"[STATS] init failed: {exc}")
    finally:
        conn.close()


def _where(filters: Dict) -> Tuple[str, List]:
    clauses = []
    params = []
    if filters.get("date_from"):
        clauses.append("created_at >= ?")
        params.append(filters["date_from"])
    if filters.get("date_to"):
        clauses.append("created_at < datetime(?, '+1 day')")
        params.append(filters["date_to"])
    if filters.get("page_id"):
        clauses.append("page_id = ?")
        params.append(filters["page_id"])
    if filters.get("skill"):
        clauses.append("skill = ?")
        params.append(filters["skill"])
    if filters.get("direction"):
        clauses.append("direction = ?")
        params.append(filters["direction"])
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def record_message_event(
    page_id: str,
    sender_psid: Optional[str] = None,
    sender_name: Optional[str] = None,
    message_mid: Optional[str] = None,
    direction: str = "inbound",
    event_type: str = "message",
    text: Optional[str] = None,
    runtime_context: Optional[Dict] = None,
    status: str = "success",
    error_message: Optional[str] = None,
    send_latency_ms: Optional[int] = None,
    **extra,
) -> bool:
    """Insert a detailed event. Returns False when a UNIQUE mid prevents duplicates."""
    if not page_id or not direction:
        return False
    init_message_stats_table()
    message_mid = str(message_mid).strip() if message_mid not in (None, "") else None
    preview, text_length = _preview(text)
    ctx = _safe_context(runtime_context)
    if send_latency_ms is not None:
        ctx["send_latency_ms"] = send_latency_ms
    for key, value in extra.items():
        if value is not None and key in ctx:
            ctx[key] = value
    try:
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO message_events (
                page_id, sender_psid, sender_name, message_mid, direction, event_type,
                message_text_preview, text_length, skill, business_domain, intent, action,
                provider, model, rag_source, rag_used, rag_hit_count, status, error_message,
                queue_wait_ms, processing_ms, ai_latency_ms, send_latency_ms, total_latency_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                page_id,
                sender_psid,
                sender_name,
                message_mid,
                direction,
                event_type,
                preview,
                text_length,
                ctx.get("skill"),
                ctx.get("business_domain"),
                ctx.get("intent"),
                ctx.get("action"),
                ctx.get("provider"),
                ctx.get("model"),
                ctx.get("rag_source"),
                ctx.get("rag_used"),
                ctx.get("rag_hit_count"),
                status,
                _preview(error_message)[0],
                ctx.get("queue_wait_ms"),
                ctx.get("processing_ms"),
                ctx.get("ai_latency_ms"),
                ctx.get("send_latency_ms"),
                ctx.get("total_latency_ms"),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    except Exception as exc:
        print(f"[STATS] record event failed: {exc}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _ensure_sender(cursor, page_id, sender_psid, sender_name=None):
    cursor.execute(
        """
        INSERT OR IGNORE INTO message_stats (page_id, sender_psid, sender_name, message_count)
        VALUES (?, ?, ?, 0)
        """,
        (page_id, sender_psid, sender_name),
    )


def record_inbound_message(page_id, sender_psid, sender_name, message_mid=None, text=None, runtime_context=None):
    inserted = record_message_event(
        page_id,
        sender_psid,
        sender_name,
        message_mid=message_mid,
        direction="inbound",
        event_type="message",
        text=text,
        runtime_context=runtime_context,
    )
    if not inserted:
        return False
    try:
        conn = _connect()
        cursor = conn.cursor()
        ctx = _safe_context(runtime_context)
        _ensure_sender(cursor, page_id, sender_psid, sender_name)
        cursor.execute(
            """
            UPDATE message_stats
            SET message_count = message_count + 1,
                inbound_count = inbound_count + 1,
                first_message_at = COALESCE(first_message_at, CURRENT_TIMESTAMP),
                last_message_at = CURRENT_TIMESTAMP,
                first_inbound_at = COALESCE(first_inbound_at, CURRENT_TIMESTAMP),
                last_inbound_at = CURRENT_TIMESTAMP,
                sender_name = COALESCE(?, sender_name),
                last_skill = COALESCE(?, last_skill),
                last_domain = COALESCE(?, last_domain),
                last_intent = COALESCE(?, last_intent),
                last_action = COALESCE(?, last_action)
            WHERE page_id = ? AND sender_psid = ?
            """,
            (
                sender_name,
                ctx.get("skill"),
                ctx.get("business_domain"),
                ctx.get("intent"),
                ctx.get("action"),
                page_id,
                sender_psid,
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        print(f"[STATS] record inbound failed: {exc}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def record_outbound_message(
    page_id,
    sender_psid,
    sender_name,
    text=None,
    runtime_context=None,
    status="success",
    send_latency_ms=None,
    error_message=None,
):
    inserted = record_message_event(
        page_id,
        sender_psid,
        sender_name,
        direction="outbound",
        event_type="message",
        text=text,
        runtime_context=runtime_context,
        status=status,
        send_latency_ms=send_latency_ms,
        error_message=error_message,
    )
    if not inserted:
        return False
    try:
        conn = _connect()
        cursor = conn.cursor()
        ctx = _safe_context(runtime_context)
        response_ms = int(ctx.get("total_latency_ms") or ctx.get("processing_ms") or 0)
        _ensure_sender(cursor, page_id, sender_psid, sender_name)
        cursor.execute(
            """
            UPDATE message_stats
            SET outbound_count = outbound_count + 1,
                last_outbound_at = CURRENT_TIMESTAMP,
                sender_name = COALESCE(?, sender_name),
                last_skill = COALESCE(?, last_skill),
                last_domain = COALESCE(?, last_domain),
                last_intent = COALESCE(?, last_intent),
                last_action = COALESCE(?, last_action),
                last_response_ms = ?,
                avg_response_ms = CASE
                    WHEN ? > 0 AND outbound_count > 0 THEN ((avg_response_ms * outbound_count) + ?) / (outbound_count + 1)
                    WHEN ? > 0 THEN ?
                    ELSE avg_response_ms
                END
            WHERE page_id = ? AND sender_psid = ?
            """,
            (
                sender_name,
                ctx.get("skill"),
                ctx.get("business_domain"),
                ctx.get("intent"),
                ctx.get("action"),
                response_ms,
                response_ms,
                response_ms,
                response_ms,
                response_ms,
                page_id,
                sender_psid,
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        print(f"[STATS] record outbound failed: {exc}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def record_postback(page_id, sender_psid, sender_name, payload=None, runtime_context=None):
    inserted = record_message_event(
        page_id,
        sender_psid,
        sender_name,
        direction="inbound",
        event_type="postback",
        text=payload,
        runtime_context=runtime_context,
    )
    if not inserted:
        return False
    try:
        conn = _connect()
        cursor = conn.cursor()
        ctx = _safe_context(runtime_context)
        _ensure_sender(cursor, page_id, sender_psid, sender_name)
        cursor.execute(
            """
            UPDATE message_stats
            SET message_count = message_count + 1,
                inbound_count = inbound_count + 1,
                postback_count = postback_count + 1,
                first_inbound_at = COALESCE(first_inbound_at, CURRENT_TIMESTAMP),
                last_inbound_at = CURRENT_TIMESTAMP,
                last_message_at = CURRENT_TIMESTAMP,
                sender_name = COALESCE(?, sender_name),
                last_skill = COALESCE(?, last_skill),
                last_domain = COALESCE(?, last_domain),
                last_intent = COALESCE(?, last_intent),
                last_action = COALESCE(?, last_action)
            WHERE page_id = ? AND sender_psid = ?
            """,
            (
                sender_name,
                ctx.get("skill"),
                ctx.get("business_domain"),
                ctx.get("intent"),
                ctx.get("action"),
                page_id,
                sender_psid,
            ),
        )
        conn.commit()
        return True
    except Exception as exc:
        print(f"[STATS] record postback failed: {exc}")
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def record_message(page_id: str, sender_psid: str, sender_name: str = None):
    """Legacy inbound counter wrapper."""
    return record_inbound_message(page_id, sender_psid, sender_name)


def get_sender_stat(page_id, sender_psid) -> Optional[Dict]:
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT *
            FROM message_stats
            WHERE page_id = ? AND sender_psid = ?
            """,
            (page_id, sender_psid),
        )
        row = cursor.fetchone()
        return dict(row) if row else None
    except Exception as exc:
        print(f"[STATS] get sender failed: {exc}")
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_page_stats(page_id: str, limit: int = 100) -> Dict:
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT COALESCE(SUM(message_count), 0), COUNT(*),
                   COALESCE(SUM(inbound_count), 0), COALESCE(SUM(outbound_count), 0),
                   COALESCE(SUM(postback_count), 0)
            FROM message_stats
            WHERE page_id = ?
            """,
            (page_id,),
        )
        row = cursor.fetchone()
        cursor.execute(
            """
            SELECT sender_psid, sender_name, message_count, first_message_at, last_message_at,
                   inbound_count, outbound_count, postback_count, last_skill, last_domain,
                   last_intent, last_action, avg_response_ms, last_response_ms
            FROM message_stats
            WHERE page_id = ?
            ORDER BY message_count DESC
            LIMIT ?
            """,
            (page_id, max(1, int(limit or 100))),
        )
        senders = [
            {
                "sender_psid": r["sender_psid"],
                "sender_name": r["sender_name"] or "Unknown",
                "message_count": r["message_count"],
                "first_message_at": r["first_message_at"],
                "last_message_at": r["last_message_at"],
                "inbound_count": r["inbound_count"],
                "outbound_count": r["outbound_count"],
                "postback_count": r["postback_count"],
                "last_skill": r["last_skill"],
                "last_domain": r["last_domain"],
                "last_intent": r["last_intent"],
                "last_action": r["last_action"],
                "avg_response_ms": r["avg_response_ms"],
                "last_response_ms": r["last_response_ms"],
            }
            for r in cursor.fetchall()
        ]
        return {
            "page_id": page_id,
            "total_messages": row[0] if row else 0,
            "unique_senders": row[1] if row else 0,
            "inbound_count": row[2] if row else 0,
            "outbound_count": row[3] if row else 0,
            "postback_count": row[4] if row else 0,
            "senders": senders,
        }
    except Exception as exc:
        print(f"[STATS] get page failed: {exc}")
        return {"page_id": page_id, "total_messages": 0, "unique_senders": 0, "senders": []}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_all_pages_stats() -> List[Dict]:
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT page_id,
                   COALESCE(SUM(message_count), 0) AS total_messages,
                   COUNT(*) AS unique_senders,
                   COALESCE(SUM(inbound_count), 0) AS inbound_count,
                   COALESCE(SUM(outbound_count), 0) AS outbound_count,
                   COALESCE(SUM(postback_count), 0) AS postback_count,
                   MAX(COALESCE(last_inbound_at, last_message_at, last_outbound_at)) AS last_interaction_at
            FROM message_stats
            GROUP BY page_id
            ORDER BY total_messages DESC
            """
        )
        return [
            {
                "page_id": row["page_id"],
                "total_messages": row["total_messages"],
                "unique_senders": row["unique_senders"],
                "inbound_count": row["inbound_count"],
                "outbound_count": row["outbound_count"],
                "postback_count": row["postback_count"],
                "last_interaction_at": row["last_interaction_at"],
            }
            for row in cursor.fetchall()
        ]
    except Exception as exc:
        print(f"[STATS] get all pages failed: {exc}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_page_stats_summary(date_from=None, date_to=None, page_id=None, skill=None) -> List[Dict]:
    if not date_from and not date_to and not skill:
        rows = get_all_pages_stats()
        if page_id:
            rows = [row for row in rows if str(row.get("page_id")) == str(page_id)]
        return rows
    where, params = _where({"date_from": date_from, "date_to": date_to, "page_id": page_id, "skill": skill})
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT
                page_id,
                SUM(CASE WHEN direction = 'inbound' AND event_type = 'message' THEN 1 ELSE 0 END) AS inbound_count,
                SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END) AS outbound_count,
                SUM(CASE WHEN event_type = 'postback' THEN 1 ELSE 0 END) AS postback_count,
                COUNT(DISTINCT CASE WHEN direction = 'inbound' AND sender_psid IS NOT NULL THEN sender_psid END) AS unique_senders,
                MAX(created_at) AS last_interaction_at
            FROM message_events
            {where}
            GROUP BY page_id
            ORDER BY inbound_count DESC, last_interaction_at DESC
            """
            ,
            params,
        )
        rows = [
            {
                "page_id": row["page_id"],
                "total_messages": row["inbound_count"] or 0,
                "unique_senders": row["unique_senders"] or 0,
                "inbound_count": row["inbound_count"] or 0,
                "outbound_count": row["outbound_count"] or 0,
                "postback_count": row["postback_count"] or 0,
                "last_interaction_at": row["last_interaction_at"],
            }
            for row in cursor.fetchall()
        ]
        if rows:
            return rows
        return _legacy_page_stats_summary(cursor, date_from, date_to, page_id, skill)
    except Exception as exc:
        print(f"[STATS] page summary failed: {exc}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _legacy_page_stats_summary(cursor, date_from=None, date_to=None, page_id=None, skill=None) -> List[Dict]:
    where, params = _legacy_stats_where(date_from, date_to, page_id, skill)
    cursor.execute(
        f"""
        SELECT
            page_id,
            COALESCE(SUM(message_count), 0) AS total_messages,
            COUNT(*) AS unique_senders,
            COALESCE(SUM(CASE WHEN inbound_count > 0 THEN inbound_count ELSE message_count END), 0) AS inbound_count,
            COALESCE(SUM(outbound_count), 0) AS outbound_count,
            COALESCE(SUM(postback_count), 0) AS postback_count,
            MAX(COALESCE(last_inbound_at, last_message_at, last_outbound_at)) AS last_interaction_at
        FROM message_stats
        {where}
        GROUP BY page_id
        ORDER BY inbound_count DESC, last_interaction_at DESC
        """,
        params,
    )
    return [
        {
            "page_id": row["page_id"],
            "total_messages": row["total_messages"],
            "unique_senders": row["unique_senders"],
            "inbound_count": row["inbound_count"],
            "outbound_count": row["outbound_count"],
            "postback_count": row["postback_count"],
            "last_interaction_at": row["last_interaction_at"],
        }
        for row in cursor.fetchall()
    ]


def get_top_senders(limit: int = 10) -> List[Dict]:
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT page_id, sender_psid, sender_name, message_count, inbound_count, outbound_count
            FROM message_stats
            ORDER BY message_count DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "page_id": row["page_id"],
                "sender_psid": row["sender_psid"],
                "sender_name": row["sender_name"] or "Unknown",
                "message_count": row["message_count"],
                "inbound_count": row["inbound_count"],
                "outbound_count": row["outbound_count"],
            }
            for row in cursor.fetchall()
        ]
    except Exception as exc:
        print(f"[STATS] get top senders failed: {exc}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_message_overview(date_from=None, date_to=None, page_id=None, skill=None) -> Dict:
    filters = {"date_from": date_from, "date_to": date_to, "page_id": page_id, "skill": skill}
    where, params = _where(filters)
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        if not date_from and not date_to:
            overview = _legacy_message_stats_overview(cursor, date_from, date_to, page_id, skill)
            event_counts = _event_overview_counts(cursor, date_from, date_to, page_id, skill)
            overview.update({
                "rag_used_count": event_counts["rag_used_count"],
                "send_failed_count": event_counts["send_failed_count"],
                "legacy_fallback": True,
            })
            return overview
        cursor.execute(
            f"""
            SELECT
                SUM(CASE WHEN direction = 'inbound' AND event_type = 'message' THEN 1 ELSE 0 END) AS inbound_count,
                SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END) AS outbound_count,
                COUNT(DISTINCT CASE WHEN direction = 'inbound' AND sender_psid IS NOT NULL THEN page_id || ':' || sender_psid END) AS unique_senders,
                SUM(CASE WHEN event_type = 'postback' THEN 1 ELSE 0 END) AS postback_count,
                SUM(CASE WHEN rag_used = 1 THEN 1 ELSE 0 END) AS rag_used_count,
                SUM(CASE WHEN direction = 'outbound' AND status != 'success' THEN 1 ELSE 0 END) AS send_failed_count,
                MAX(created_at) AS last_updated_at
            FROM message_events
            {where}
            """,
            params,
        )
        row = cursor.fetchone() or {}
        overview = {
            "inbound_count": row["inbound_count"] or 0,
            "outbound_count": row["outbound_count"] or 0,
            "unique_senders": row["unique_senders"] or 0,
            "new_senders": _event_new_senders(cursor, date_from, date_to, page_id, skill),
            "today_senders": _event_today_senders(cursor, page_id, skill),
            "postback_count": row["postback_count"] or 0,
            "rag_used_count": row["rag_used_count"] or 0,
            "send_failed_count": row["send_failed_count"] or 0,
            "last_updated_at": row["last_updated_at"],
        }
        if (
            overview["inbound_count"] == 0
            and overview["outbound_count"] == 0
            and overview["unique_senders"] == 0
            and overview["postback_count"] == 0
        ):
            fallback = _legacy_message_stats_overview(cursor, date_from, date_to, page_id, skill)
            overview.update({
                "inbound_count": fallback["inbound_count"],
                "unique_senders": fallback["unique_senders"],
                "new_senders": fallback["new_senders"],
                "today_senders": fallback["today_senders"],
                "outbound_count": fallback["outbound_count"],
                "postback_count": fallback["postback_count"],
                "last_updated_at": fallback["last_updated_at"],
                "legacy_fallback": True,
            })
        else:
            overview["legacy_fallback"] = False
        return overview
    except Exception as exc:
        print(f"[STATS] overview failed: {exc}")
        return {
            "inbound_count": 0,
            "outbound_count": 0,
            "unique_senders": 0,
            "postback_count": 0,
            "rag_used_count": 0,
            "send_failed_count": 0,
        }
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _legacy_stats_where(date_from=None, date_to=None, page_id=None, skill=None) -> Tuple[str, List]:
    clauses = []
    params = []
    if date_from:
        clauses.append("last_message_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("last_message_at < datetime(?, '+1 day')")
        params.append(date_to)
    if page_id:
        clauses.append("page_id = ?")
        params.append(page_id)
    if skill:
        clauses.append("last_skill = ?")
        params.append(skill)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return where, params


def _legacy_message_stats_overview(cursor, date_from=None, date_to=None, page_id=None, skill=None) -> Dict:
    where, params = _legacy_stats_where(date_from, date_to, page_id, skill)
    cursor.execute(
        f"""
        SELECT
            COALESCE(SUM(CASE WHEN inbound_count > 0 THEN inbound_count ELSE message_count END), 0) AS inbound_count,
            COALESCE(SUM(outbound_count), 0) AS outbound_count,
            COUNT(DISTINCT CASE WHEN sender_psid IS NOT NULL THEN page_id || ':' || sender_psid END) AS unique_senders,
            COALESCE(SUM(postback_count), 0) AS postback_count,
            MAX(COALESCE(last_inbound_at, last_message_at, last_outbound_at)) AS last_updated_at
        FROM message_stats
        {where}
        """,
        params,
    )
    row = cursor.fetchone() or {}
    return {
        "inbound_count": row["inbound_count"] or 0,
        "outbound_count": row["outbound_count"] or 0,
        "unique_senders": row["unique_senders"] or 0,
        "new_senders": _legacy_new_senders(cursor, date_from, date_to, page_id, skill),
        "today_senders": _legacy_today_senders(cursor, page_id, skill),
        "postback_count": row["postback_count"] or 0,
        "last_updated_at": row["last_updated_at"],
        "rag_used_count": 0,
        "send_failed_count": 0,
    }


def _event_overview_counts(cursor, date_from=None, date_to=None, page_id=None, skill=None) -> Dict:
    where, params = _where({"date_from": date_from, "date_to": date_to, "page_id": page_id, "skill": skill})
    cursor.execute(
        f"""
        SELECT
            SUM(CASE WHEN rag_used = 1 THEN 1 ELSE 0 END) AS rag_used_count,
            SUM(CASE WHEN direction = 'outbound' AND status != 'success' THEN 1 ELSE 0 END) AS send_failed_count
        FROM message_events
        {where}
        """,
        params,
    )
    row = cursor.fetchone() or {}
    return {
        "rag_used_count": row["rag_used_count"] or 0,
        "send_failed_count": row["send_failed_count"] or 0,
    }


def _event_new_senders(cursor, date_from=None, date_to=None, page_id=None, skill=None) -> int:
    filters = {"page_id": page_id, "skill": skill}
    where, params = _where(filters)
    where = where + (" AND " if where else " WHERE ") + "direction = 'inbound' AND sender_psid IS NOT NULL"
    having = []
    if date_from:
        having.append("first_seen >= ?")
        params.append(date_from)
    if date_to:
        having.append("first_seen < datetime(?, '+1 day')")
        params.append(date_to)
    having_sql = " HAVING " + " AND ".join(having) if having else ""
    cursor.execute(
        f"""
        SELECT COUNT(*) AS count
        FROM (
            SELECT page_id, sender_psid, MIN(created_at) AS first_seen
            FROM message_events
            {where}
            GROUP BY page_id, sender_psid
            {having_sql}
        )
        """,
        params,
    )
    row = cursor.fetchone()
    return (row["count"] if row else 0) or 0


def _event_today_senders(cursor, page_id=None, skill=None) -> int:
    filters = {"page_id": page_id, "skill": skill}
    where, params = _where(filters)
    where = where + (" AND " if where else " WHERE ") + "direction = 'inbound' AND sender_psid IS NOT NULL AND date(created_at) = date('now', 'localtime')"
    cursor.execute(
        f"SELECT COUNT(DISTINCT page_id || ':' || sender_psid) AS count FROM message_events {where}",
        params,
    )
    row = cursor.fetchone()
    return (row["count"] if row else 0) or 0


def _legacy_new_senders(cursor, date_from=None, date_to=None, page_id=None, skill=None) -> int:
    clauses = []
    params = []
    if page_id:
        clauses.append("page_id = ?")
        params.append(page_id)
    if skill:
        clauses.append("last_skill = ?")
        params.append(skill)
    if date_from:
        clauses.append("COALESCE(first_inbound_at, first_message_at) >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("COALESCE(first_inbound_at, first_message_at) < datetime(?, '+1 day')")
        params.append(date_to)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    cursor.execute(f"SELECT COUNT(*) AS count FROM message_stats {where}", params)
    row = cursor.fetchone()
    return (row["count"] if row else 0) or 0


def _legacy_today_senders(cursor, page_id=None, skill=None) -> int:
    clauses = ["date(COALESCE(last_inbound_at, last_message_at)) = date('now', 'localtime')"]
    params = []
    if page_id:
        clauses.append("page_id = ?")
        params.append(page_id)
    if skill:
        clauses.append("last_skill = ?")
        params.append(skill)
    cursor.execute(
        f"SELECT COUNT(*) AS count FROM message_stats WHERE {' AND '.join(clauses)}",
        params,
    )
    row = cursor.fetchone()
    return (row["count"] if row else 0) or 0


def get_message_events(date_from=None, date_to=None, page_id=None, skill=None, direction=None, limit=100, offset=0) -> List[Dict]:
    filters = {"date_from": date_from, "date_to": date_to, "page_id": page_id, "skill": skill, "direction": direction}
    where, params = _where(filters)
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT page_id, sender_psid, sender_name, message_mid, direction, event_type,
                   message_text_preview, text_length, skill, business_domain, intent, action,
                   provider, model, rag_source, rag_used, rag_hit_count, status, error_message,
                   queue_wait_ms, processing_ms, ai_latency_ms, send_latency_ms, total_latency_ms,
                   created_at
            FROM message_events
            {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            params + [max(1, int(limit or 100)), max(0, int(offset or 0))],
        )
        return [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        print(f"[STATS] events failed: {exc}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_top_interactors(date_from=None, date_to=None, page_id=None, skill=None, limit=50) -> List[Dict]:
    filters = {"date_from": date_from, "date_to": date_to, "page_id": page_id, "skill": skill}
    where, params = _where(filters)
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        if not date_from and not date_to:
            return _legacy_top_interactors(cursor, date_from, date_to, page_id, skill, limit)
        cursor.execute(
            f"""
            SELECT
                page_id,
                sender_psid,
                COALESCE(MAX(NULLIF(sender_name, '')), '') AS sender_name,
                SUM(CASE WHEN direction = 'inbound' AND event_type = 'message' THEN 1 ELSE 0 END) AS inbound_count,
                SUM(CASE WHEN direction = 'outbound' THEN 1 ELSE 0 END) AS outbound_count,
                SUM(CASE WHEN event_type = 'postback' THEN 1 ELSE 0 END) AS postback_count,
                MIN(CASE WHEN direction = 'inbound' THEN created_at END) AS first_inbound_at,
                MAX(CASE WHEN direction = 'inbound' THEN created_at END) AS last_inbound_at,
                MAX(NULLIF(skill, '')) AS last_skill
            FROM message_events
            {where}
            GROUP BY page_id, sender_psid
            HAVING sender_psid IS NOT NULL AND sender_psid != '' AND sender_psid != page_id
            ORDER BY inbound_count DESC, last_inbound_at DESC
            LIMIT ?
            """,
            params + [max(1, int(limit or 50))],
        )
        rows = [_interactor_row(row) for row in cursor.fetchall()]
        if rows:
            return rows
        return _legacy_top_interactors(cursor, date_from, date_to, page_id, skill, limit)
    except Exception as exc:
        print(f"[STATS] top interactors failed: {exc}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _interactor_row(row) -> Dict:
    inbound = row["inbound_count"] or 0
    outbound = row["outbound_count"] or 0
    postback = row["postback_count"] or 0
    return {
        "page_id": row["page_id"],
        "sender_psid": row["sender_psid"],
        "sender_name": row["sender_name"] or "",
        "inbound_count": inbound,
        "outbound_count": outbound,
        "postback_count": postback,
        "total_interactions": inbound + outbound + postback,
        "first_inbound_at": row["first_inbound_at"],
        "last_inbound_at": row["last_inbound_at"],
        "last_skill": row["last_skill"],
    }


def _legacy_top_interactors(cursor, date_from=None, date_to=None, page_id=None, skill=None, limit=50) -> List[Dict]:
    where, params = _legacy_stats_where(date_from, date_to, page_id, skill)
    where = where + (" AND " if where else " WHERE ") + "sender_psid IS NOT NULL AND sender_psid != '' AND sender_psid != page_id"
    cursor.execute(
        f"""
        SELECT
            page_id,
            sender_psid,
            sender_name,
            CASE WHEN COALESCE(inbound_count, 0) > 0 THEN inbound_count ELSE COALESCE(message_count, 0) END AS inbound_count,
            COALESCE(outbound_count, 0) AS outbound_count,
            COALESCE(postback_count, 0) AS postback_count,
            COALESCE(first_inbound_at, first_message_at) AS first_inbound_at,
            COALESCE(last_inbound_at, last_message_at) AS last_inbound_at,
            last_skill
        FROM message_stats
        {where}
        ORDER BY inbound_count DESC, last_inbound_at DESC
        LIMIT ?
        """,
        params + [max(1, int(limit or 50))],
    )
    return [_interactor_row(row) for row in cursor.fetchall()]


def get_sender_interaction_detail(page_id, sender_psid, limit=50) -> Dict:
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        stat = get_sender_stat(page_id, sender_psid) or {}
        cursor.execute(
            """
            SELECT page_id, sender_psid, sender_name, direction, event_type,
                   message_text_preview, status, skill, action, intent, created_at
            FROM message_events
            WHERE page_id = ? AND sender_psid = ?
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (page_id, sender_psid, max(1, int(limit or 50))),
        )
        events = [dict(row) for row in cursor.fetchall()]
        inbound = stat.get("inbound_count") or stat.get("message_count") or 0
        outbound = stat.get("outbound_count") or 0
        postback = stat.get("postback_count") or 0
        detail = {
            "page_id": page_id,
            "sender_psid": sender_psid,
            "sender_name": stat.get("sender_name") or "",
            "inbound_count": inbound,
            "outbound_count": outbound,
            "postback_count": postback,
            "total_interactions": inbound + outbound + postback,
            "first_inbound_at": stat.get("first_inbound_at") or stat.get("first_message_at"),
            "last_inbound_at": stat.get("last_inbound_at") or stat.get("last_message_at"),
            "last_skill": stat.get("last_skill"),
            "events": events,
            "has_event_history": bool(events),
        }
        if events:
            detail["sender_name"] = detail["sender_name"] or events[0].get("sender_name") or ""
        return detail
    except Exception as exc:
        print(f"[STATS] sender detail failed: {exc}")
        return {"page_id": page_id, "sender_psid": sender_psid, "events": [], "has_event_history": False}
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _top(field, date_from=None, date_to=None, page_id=None, skill=None, limit=10) -> List[Dict]:
    if field not in {"intent", "action"}:
        return []
    where, params = _where({"date_from": date_from, "date_to": date_to, "page_id": page_id, "skill": skill})
    where = where + (" AND " if where else " WHERE ") + f"{field} IS NOT NULL AND {field} != ''"
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT {field} AS name, COUNT(*) AS count
            FROM message_events
            {where}
            GROUP BY {field}
            ORDER BY count DESC
            LIMIT ?
            """,
            params + [limit],
        )
        rows = [{"name": row["name"], "count": row["count"]} for row in cursor.fetchall()]
        if rows:
            return rows
        return _legacy_top_stats(cursor, field, date_from, date_to, page_id, skill, limit)
    except Exception as exc:
        print(f"[STATS] top {field} failed: {exc}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_top_intents(date_from=None, date_to=None, page_id=None, skill=None, limit=10) -> List[Dict]:
    return _top("intent", date_from, date_to, page_id, skill, limit)


def get_top_actions(date_from=None, date_to=None, page_id=None, skill=None, limit=10) -> List[Dict]:
    return _top("action", date_from, date_to, page_id, skill, limit)


def _legacy_top_stats(cursor, field, date_from=None, date_to=None, page_id=None, skill=None, limit=10) -> List[Dict]:
    legacy_field = "last_intent" if field == "intent" else "last_action"
    where, params = _legacy_stats_where(date_from, date_to, page_id, skill)
    where = where + (" AND " if where else " WHERE ") + f"{legacy_field} IS NOT NULL AND {legacy_field} != ''"
    cursor.execute(
        f"""
        SELECT {legacy_field} AS name, COUNT(*) AS count
        FROM message_stats
        {where}
        GROUP BY {legacy_field}
        ORDER BY count DESC
        LIMIT ?
        """,
        params + [limit],
    )
    return [{"name": row["name"], "count": row["count"]} for row in cursor.fetchall()]


def get_rag_stats(date_from=None, date_to=None, page_id=None, skill=None) -> Dict:
    where, params = _where({"date_from": date_from, "date_to": date_to, "page_id": page_id, "skill": skill})
    try:
        init_message_stats_table()
        conn = _connect()
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT COUNT(*) AS total_events,
                   SUM(CASE WHEN rag_used = 1 THEN 1 ELSE 0 END) AS rag_used_count,
                   COALESCE(SUM(rag_hit_count), 0) AS rag_hit_count
            FROM message_events
            {where}
            """,
            params,
        )
        row = cursor.fetchone() or {}
        return {
            "total_events": row["total_events"] or 0,
            "rag_used_count": row["rag_used_count"] or 0,
            "rag_hit_count": row["rag_hit_count"] or 0,
        }
    except Exception as exc:
        print(f"[STATS] rag stats failed: {exc}")
        return {"total_events": 0, "rag_used_count": 0, "rag_hit_count": 0}
    finally:
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    init_message_stats_table()
    print("Stats:", get_all_pages_stats())
