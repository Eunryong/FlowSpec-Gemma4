from __future__ import annotations

import argparse
import json
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import date, datetime, time, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
DEFAULT_DB = ROOT / "data" / "bookings.sqlite3"
KST = ZoneInfo("Asia/Seoul")
SLOT_MINUTES = 30
MAX_BODY_BYTES = 8_192

COUNSELORS = (
    ("counselor_garam", "김가람", "커리어와 일의 방향", "커리어 상담"),
    ("counselor_haneul", "박하늘", "일상과 관계의 고민", "일상 상담"),
)


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(db_path, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA busy_timeout = 5000")
    return db


def initialize(db_path: Path) -> None:
    with closing(connect(db_path)) as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS counselors (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                focus TEXT NOT NULL,
                label TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                counselor_id TEXT NOT NULL REFERENCES counselors(id),
                starts_at TEXT NOT NULL,
                is_open INTEGER NOT NULL DEFAULT 1 CHECK (is_open IN (0, 1)),
                UNIQUE (counselor_id, starts_at)
            );
            CREATE TABLE IF NOT EXISTS bookings (
                reference TEXT PRIMARY KEY,
                slot_id INTEGER NOT NULL REFERENCES slots(id),
                client_name TEXT NOT NULL,
                email TEXT NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('CONFIRMED', 'CANCELLED')),
                created_at TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_booking_per_slot
                ON bookings(slot_id) WHERE status = 'CONFIRMED';
            """
        )
        if db.execute("SELECT COUNT(*) FROM counselors").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO counselors(id, name, focus, label) VALUES (?, ?, ?, ?)",
                COUNSELORS,
            )
        if db.execute("SELECT COUNT(*) FROM slots").fetchone()[0] == 0:
            today = datetime.now(KST).date()
            entries = []
            for offset in range(1, 22):
                slot_date = today + timedelta(days=offset)
                if slot_date.weekday() >= 5:
                    continue
                for counselor_id, *_ in COUNSELORS:
                    for hour in (10, 11, 14, 15, 16):
                        starts = datetime.combine(slot_date, time(hour, 0), KST)
                        entries.append((counselor_id, starts.isoformat(timespec="minutes")))
            db.executemany(
                "INSERT OR IGNORE INTO slots(counselor_id, starts_at) VALUES (?, ?)",
                entries,
            )
        db.commit()


def now_kst() -> datetime:
    return datetime.now(KST)


def booking_view(row: sqlite3.Row) -> dict:
    starts = datetime.fromisoformat(row["starts_at"])
    return {
        "reference": row["reference"],
        "status": row["status"],
        "client_name": row["client_name"],
        "counselor_id": row["counselor_id"],
        "counselor_name": row["counselor_name"],
        "counselor_label": row["counselor_label"],
        "starts_at": starts.isoformat(timespec="minutes"),
        "ends_at": (starts + timedelta(minutes=SLOT_MINUTES)).isoformat(timespec="minutes"),
        "duration_minutes": SLOT_MINUTES,
    }


class BookingHandler(BaseHTTPRequestHandler):
    db_path: Path

    def _send(self, status: int, payload: object, content_type: str = "application/json; charset=utf-8") -> None:
        if content_type.startswith("application/json"):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        else:
            body = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, message: str) -> None:
        self._send(status, {"error": message})

    def _body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as exc:
            raise ValueError("요청 형식이 올바르지 않습니다.") from exc
        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("요청 크기가 올바르지 않습니다.")
        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("JSON 요청을 읽을 수 없습니다.") from exc
        if not isinstance(data, dict):
            raise ValueError("요청 본문은 객체여야 합니다.")
        return data

    def _serve_static(self, name: str) -> None:
        allowed = {
            "": (STATIC / "index.html", "text/html; charset=utf-8"),
            "index.html": (STATIC / "index.html", "text/html; charset=utf-8"),
            "app.js": (STATIC / "app.js", "text/javascript; charset=utf-8"),
            "styles.css": (STATIC / "styles.css", "text/css; charset=utf-8"),
        }
        if name not in allowed:
            self._error(404, "페이지를 찾을 수 없습니다.")
            return
        path, content_type = allowed[name]
        self._send(200, path.read_bytes(), content_type)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        path = unquote(parsed.path)
        query = parse_qs(parsed.query)
        try:
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path == "/" or path in ("/index.html", "/app.js", "/styles.css"):
                self._serve_static(path.lstrip("/"))
                return
            if path == "/api/health":
                self._send(200, {"status": "ok", "timezone": "Asia/Seoul"})
                return
            if path == "/api/counselors":
                with closing(connect(self.db_path)) as db:
                    rows = db.execute(
                        "SELECT id, name, focus, label FROM counselors ORDER BY name"
                    ).fetchall()
                self._send(200, {"counselors": [dict(row) for row in rows]})
                return
            if path == "/api/dates":
                counselor_id = query.get("counselor_id", [""])[0]
                params: list[object] = [now_kst().isoformat(timespec="minutes")]
                sql = """
                    SELECT DISTINCT substr(s.starts_at, 1, 10) AS slot_date
                    FROM slots s
                    WHERE s.is_open = 1 AND s.starts_at > ?
                      AND NOT EXISTS (
                        SELECT 1 FROM bookings b
                        WHERE b.slot_id = s.id AND b.status = 'CONFIRMED'
                      )
                """
                if counselor_id:
                    sql += " AND s.counselor_id = ?"
                    params.append(counselor_id)
                sql += " ORDER BY slot_date LIMIT 21"
                with closing(connect(self.db_path)) as db:
                    rows = db.execute(sql, params).fetchall()
                self._send(200, {"dates": [row["slot_date"] for row in rows]})
                return
            if path == "/api/slots":
                counselor_id = query.get("counselor_id", [""])[0]
                slot_date = query.get("date", [""])[0]
                try:
                    date.fromisoformat(slot_date)
                except ValueError:
                    self._error(400, "날짜를 선택해 주세요.")
                    return
                with closing(connect(self.db_path)) as db:
                    rows = db.execute(
                        """
                        SELECT s.id, s.starts_at, c.name AS counselor_name
                        FROM slots s JOIN counselors c ON c.id = s.counselor_id
                        WHERE s.counselor_id = ? AND substr(s.starts_at, 1, 10) = ?
                          AND s.is_open = 1 AND s.starts_at > ?
                          AND NOT EXISTS (
                            SELECT 1 FROM bookings b
                            WHERE b.slot_id = s.id AND b.status = 'CONFIRMED'
                          )
                        ORDER BY s.starts_at
                        """,
                        (counselor_id, slot_date, now_kst().isoformat(timespec="minutes")),
                    ).fetchall()
                self._send(200, {"slots": [dict(row) for row in rows]})
                return
            if path == "/api/admin/slots":
                slot_date = query.get("date", [""])[0]
                try:
                    date.fromisoformat(slot_date)
                except ValueError:
                    self._error(400, "날짜를 선택해 주세요.")
                    return
                with closing(connect(self.db_path)) as db:
                    rows = db.execute(
                        """
                        SELECT s.id, s.starts_at, s.is_open, c.id AS counselor_id,
                               c.name AS counselor_name,
                               b.reference, b.client_name, b.status AS booking_status
                        FROM slots s JOIN counselors c ON c.id = s.counselor_id
                        LEFT JOIN bookings b ON b.slot_id = s.id AND b.status = 'CONFIRMED'
                        WHERE substr(s.starts_at, 1, 10) = ?
                        ORDER BY s.starts_at, c.name
                        """,
                        (slot_date,),
                    ).fetchall()
                result = []
                for row in rows:
                    item = dict(row)
                    item["starts_at"] = datetime.fromisoformat(item["starts_at"]).isoformat(timespec="minutes")
                    result.append(item)
                self._send(200, {"slots": result})
                return
            if path == "/api/admin/bookings":
                slot_date = query.get("date", [""])[0]
                try:
                    date.fromisoformat(slot_date)
                except ValueError:
                    self._error(400, "날짜를 선택해 주세요.")
                    return
                with closing(connect(self.db_path)) as db:
                    rows = db.execute(
                        """
                        SELECT b.reference, b.client_name, b.email, b.status,
                               s.starts_at, c.id AS counselor_id,
                               c.name AS counselor_name, c.label AS counselor_label
                        FROM bookings b JOIN slots s ON s.id = b.slot_id
                        JOIN counselors c ON c.id = s.counselor_id
                        WHERE substr(s.starts_at, 1, 10) = ?
                        ORDER BY s.starts_at, c.name
                        """,
                        (slot_date,),
                    ).fetchall()
                self._send(200, {"bookings": [booking_view(row) for row in rows]})
                return
            if path.startswith("/api/bookings/"):
                reference = path.rsplit("/", 1)[-1].upper()
                email = query.get("email", [""])[0].strip().lower()
                if not email:
                    self._error(400, "예약할 때 입력한 이메일을 입력해 주세요.")
                    return
                with closing(connect(self.db_path)) as db:
                    row = db.execute(
                        """
                        SELECT b.reference, b.status, b.client_name, b.email,
                               s.starts_at, c.id AS counselor_id,
                               c.name AS counselor_name, c.label AS counselor_label
                        FROM bookings b JOIN slots s ON s.id = b.slot_id
                        JOIN counselors c ON c.id = s.counselor_id
                        WHERE b.reference = ? AND lower(b.email) = ?
                        """,
                        (reference, email),
                    ).fetchone()
                if row is None:
                    self._error(404, "예약 정보가 일치하지 않습니다. 예약번호와 이메일을 확인해 주세요.")
                    return
                self._send(200, {"booking": booking_view(row)})
                return
            self._error(404, "요청한 주소를 찾을 수 없습니다.")
        except sqlite3.Error:
            self._error(500, "저장된 정보를 읽지 못했습니다.")

    def do_POST(self) -> None:
        path = unquote(urlsplit(self.path).path)
        try:
            data = self._body()
        except ValueError as exc:
            self._error(400, str(exc))
            return
        if path == "/api/bookings":
            self._create_booking(data)
            return
        if path.startswith("/api/bookings/") and path.endswith("/cancel"):
            reference = path.split("/")[-2].upper()
            self._cancel_booking(reference, data)
            return
        if path == "/api/admin/slots":
            self._create_slot(data)
            return
        self._error(404, "요청한 주소를 찾을 수 없습니다.")

    def do_DELETE(self) -> None:
        path = unquote(urlsplit(self.path).path)
        match = re.fullmatch(r"/api/admin/slots/(\d+)", path)
        if not match:
            self._error(404, "요청한 주소를 찾을 수 없습니다.")
            return
        slot_id = int(match.group(1))
        with closing(connect(self.db_path)) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT id FROM slots WHERE id = ? AND is_open = 1", (slot_id,)
            ).fetchone()
            if row is None:
                db.rollback()
                self._error(404, "열려 있는 시간을 찾을 수 없습니다.")
                return
            active = db.execute(
                "SELECT 1 FROM bookings WHERE slot_id = ? AND status = 'CONFIRMED'",
                (slot_id,),
            ).fetchone()
            if active:
                db.rollback()
                self._error(409, "예약된 시간은 닫을 수 없습니다. 먼저 예약을 취소해 주세요.")
                return
            db.execute("UPDATE slots SET is_open = 0 WHERE id = ?", (slot_id,))
            db.commit()
        self._send(200, {"closed": True})

    def _create_booking(self, data: dict) -> None:
        name = str(data.get("client_name", "")).strip()
        email = str(data.get("email", "")).strip().lower()
        try:
            slot_id = int(data.get("slot_id"))
        except (TypeError, ValueError):
            self._error(400, "가능한 시간을 선택해 주세요.")
            return
        if not name or len(name) > 80:
            self._error(400, "이름을 1자 이상 80자 이하로 입력해 주세요.")
            return
        if len(email) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            self._error(400, "올바른 이메일 주소를 입력해 주세요.")
            return

        db = connect(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                """
                SELECT s.id, s.starts_at, s.is_open, c.id AS counselor_id,
                       c.name AS counselor_name, c.label AS counselor_label
                FROM slots s JOIN counselors c ON c.id = s.counselor_id
                WHERE s.id = ?
                """,
                (slot_id,),
            ).fetchone()
            if row is None or not row["is_open"]:
                db.rollback()
                self._error(409, "선택한 시간이 더 이상 예약 가능하지 않습니다. 다른 시간을 골라 주세요.")
                return
            starts = datetime.fromisoformat(row["starts_at"])
            if starts <= now_kst():
                db.rollback()
                self._error(409, "이미 지난 시간은 예약할 수 없습니다.")
                return
            reference = secrets.token_hex(4).upper()
            try:
                db.execute(
                    """
                    INSERT INTO bookings(reference, slot_id, client_name, email, status, created_at)
                    VALUES (?, ?, ?, ?, 'CONFIRMED', ?)
                    """,
                    (reference, slot_id, name, email, now_kst().isoformat(timespec="seconds")),
                )
            except sqlite3.IntegrityError:
                db.rollback()
                self._error(409, "방금 다른 고객이 먼저 예약했습니다. 다른 시간을 골라 주세요.")
                return
            db.commit()
            result = {
                "reference": reference,
                "status": "CONFIRMED",
                "client_name": name,
                "counselor_id": row["counselor_id"],
                "counselor_name": row["counselor_name"],
                "counselor_label": row["counselor_label"],
                "starts_at": starts.isoformat(timespec="minutes"),
                "ends_at": (starts + timedelta(minutes=SLOT_MINUTES)).isoformat(timespec="minutes"),
                "duration_minutes": SLOT_MINUTES,
            }
            self._send(201, {"booking": result})
        except sqlite3.Error:
            db.rollback()
            self._error(500, "예약을 저장하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        finally:
            db.close()

    def _cancel_booking(self, reference: str, data: dict) -> None:
        email = str(data.get("email", "")).strip().lower()
        if not email:
            self._error(400, "예약할 때 입력한 이메일을 입력해 주세요.")
            return
        db = connect(self.db_path)
        try:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT status FROM bookings WHERE reference = ? AND lower(email) = ?",
                (reference, email),
            ).fetchone()
            if row is None:
                db.rollback()
                self._error(404, "예약 정보가 일치하지 않습니다.")
                return
            if row["status"] != "CONFIRMED":
                db.rollback()
                self._error(409, "이미 취소된 예약입니다.")
                return
            db.execute(
                "UPDATE bookings SET status = 'CANCELLED' WHERE reference = ?",
                (reference,),
            )
            db.commit()
            self._send(200, {"reference": reference, "status": "CANCELLED"})
        except sqlite3.Error:
            db.rollback()
            self._error(500, "예약을 취소하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        finally:
            db.close()

    def _create_slot(self, data: dict) -> None:
        counselor_id = str(data.get("counselor_id", ""))
        raw_date = str(data.get("date", ""))
        raw_time = str(data.get("time", ""))
        try:
            slot_date = date.fromisoformat(raw_date)
            parsed_time = time.fromisoformat(raw_time)
        except ValueError:
            self._error(400, "날짜와 시간을 확인해 주세요.")
            return
        if parsed_time.second or parsed_time.minute not in (0, 30):
            self._error(400, "상담 시간은 매시 정각 또는 30분부터 시작해야 합니다.")
            return
        starts = datetime.combine(slot_date, parsed_time, KST)
        if starts <= now_kst():
            self._error(400, "지난 시간은 열 수 없습니다.")
            return
        with closing(connect(self.db_path)) as db:
            if db.execute("SELECT 1 FROM counselors WHERE id = ?", (counselor_id,)).fetchone() is None:
                self._error(400, "상담자를 선택해 주세요.")
                return
            try:
                db.execute(
                    "INSERT INTO slots(counselor_id, starts_at, is_open) VALUES (?, ?, 1)",
                    (counselor_id, starts.isoformat(timespec="minutes")),
                )
                db.commit()
            except sqlite3.IntegrityError:
                self._error(409, "이미 등록된 시간입니다.")
                return
        self._send(201, {"slot": {"counselor_id": counselor_id, "starts_at": starts.isoformat(timespec="minutes")}})

    def log_message(self, format: str, *args: object) -> None:
        super().log_message(format, *args)


def make_handler(db_path: Path):
    class Handler(BookingHandler):
        pass
    Handler.db_path = db_path
    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="로컬 1:1 상담 예약 프로토타입")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost"):
        parser.error("개발용 개인정보 보호를 위해 localhost 주소에만 바인딩할 수 있습니다.")

    initialize(args.db)
    server = ThreadingHTTPServer((args.host, args.port), make_handler(args.db))
    print(f"상담 예약 프로토타입 실행: http://{args.host}:{args.port}")
    print(f"로컬 데이터베이스: {args.db}")
    print("중지하려면 Ctrl-C를 누르세요.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("서버를 종료합니다.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
