import sqlite3
from typing import List, Optional, Tuple

class CounselingRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS slots (
                    slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    counselor_id TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    is_booked BOOLEAN NOT NULL DEFAULT 0,
                    UNIQUE(counselor_id, start_time)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id TEXT PRIMARY KEY,
                    slot_id INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    client_email TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY(slot_id) REFERENCES slots(slot_id)
                )
            """)
            conn.commit()

    def add_slot(self, counselor_id: str, start_time: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO slots (counselor_id, start_time) VALUES (?, ?)",
                (counselor_id, start_time)
            )
            conn.commit()
            return cursor.lastrowid

    def get_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[dict]:
        query = "SELECT * FROM slots WHERE is_booked = 0"
        params = []
        if counselor_id:
            query += " AND counselor_id = ?"
            params.append(counselor_id)
        if date:
            query += " AND start_time LIKE ?"
            params.append(f"{date}%")
        
        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [dict(row) for row in rows]

    def get_slot_by_id(self, slot_id: int) -> Optional[dict]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM slots WHERE slot_id = ?", (slot_id,)).fetchone()
            return dict(row) if row else None

    def update_slot_status(self, slot_id: int, is_booked: bool, conn=None):
        sql = "UPDATE slots SET is_booked = ? WHERE slot_id = ?"
        if conn:
            conn.execute(sql, (is_booked, slot_id))
        else:
            with self._get_connection() as conn_local:
                conn_local.execute(sql, (is_booked, slot_id))
                conn_local.commit()

    def create_booking(self, booking_id: str, slot_id: int, client_name: str, client_email: str, status: str, conn=None):
        sql = "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)"
        if conn:
            conn.execute(sql, (booking_id, slot_id, client_name, client_email, status))
        else:
            with self._get_connection() as conn_local:
                conn_local.execute(sql, (booking_id, slot_id, client_name, client_email, status))
                conn_local.commit()

    def get_booking(self, booking_id: str) -> Optional[dict]:
        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
            return dict(row) if row else None

    def update_booking_status(self, booking_id: str, status: str, conn=None):
        sql = "UPDATE bookings SET status = ? WHERE booking_id = ?"
        if conn:
            conn.execute(sql, (status, booking_id))
        else:
            with self._get_connection() as conn_local:
                conn_local.execute(sql, (status, booking_id))
                conn_local.commit()
