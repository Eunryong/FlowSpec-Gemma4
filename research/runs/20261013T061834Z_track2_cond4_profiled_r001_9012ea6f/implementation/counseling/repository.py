import sqlite3
from typing import List, Optional, Tuple
from dataclasses import dataclass

@dataclass
class Slot:
    slot_id: int
    counselor_id: str
    start_time: str
    is_booked: bool

@dataclass
class Booking:
    booking_id: str
    slot_id: int
    client_name: str
    client_email: str
    status: str

class CounselingRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS slots (
                    slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    counselor_id TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    is_booked BOOLEAN NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id TEXT PRIMARY KEY,
                    slot_id INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    client_email TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (slot_id) REFERENCES slots (slot_id)
                )
            """)
            conn.commit()

    def add_slot(self, counselor_id: str, start_time: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "INSERT INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                (counselor_id, start_time)
            )
            return cursor.lastrowid

    def get_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Slot]:
        query = "SELECT slot_id, counselor_id, start_time, is_booked FROM slots WHERE is_booked = 0"
        params = []
        if counselor_id:
            query += " AND counselor_id = ?"
            params.append(counselor_id)
        if date:
            query += " AND start_time LIKE ?"
            params.append(f"{date}%")
        
        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [Slot(*row) for row in cursor.fetchall()]

    def get_slot_by_counselor_and_time(self, counselor_id: str, start_time: str) -> Optional[Slot]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT slot_id, counselor_id, start_time, is_booked FROM slots WHERE counselor_id = ? AND start_time = ?",
                (counselor_id, start_time)
            )
            row = cursor.fetchone()
            return Slot(*row) if row else None

    def update_slot_status(self, slot_id: int, is_booked: bool, conn=None):
        sql = "UPDATE slots SET is_booked = ? WHERE slot_id = ?"
        if conn:
            conn.execute(sql, (int(is_booked), slot_id))
        else:
            with self._get_connection() as conn_local:
                conn_local.execute(sql, (int(is_booked), slot_id))

    def create_booking(self, booking: Booking, conn=None):
        sql = "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)"
        if conn:
            conn.execute(sql, (booking.booking_id, booking.slot_id, booking.client_name, booking.client_email, booking.status))
        else:
            with self._get_connection() as conn_local:
                conn_local.execute(sql, (booking.booking_id, booking.slot_id, booking.client_name, booking.client_email, booking.status))

    def get_booking(self, booking_id: str) -> Optional[Booking]:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT booking_id, slot_id, client_name, client_email, status FROM bookings WHERE booking_id = ?",
                (booking_id,)
            )
            row = cursor.fetchone()
            return Booking(*row) if row else None

    def update_booking_status(self, booking_id: str, status: str, conn=None):
        sql = "UPDATE bookings SET status = ? WHERE booking_id = ?"
        if conn:
            conn.execute(sql, (status, booking_id))
        else:
            with self._get_connection() as conn_local:
                conn_local.execute(sql, (status, booking_id))
