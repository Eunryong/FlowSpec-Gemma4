import sqlite3
import uuid
from datetime import datetime
from typing import List, Dict, Optional

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
        self.db_path = db_path
        self._conn = None
        if db_path == ":memory:":
            self._conn = sqlite3.connect(db_path)
            self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self):
        if self._conn:
            return self._conn
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS slots (
                slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                counselor_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                status TEXT NOT NULL
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

    def add_available_slot(self, counselor_id: str, start_time: str) -> None:
        # Validate ISO 8601 format (basic check)
        try:
            # This handles formats like 2026-10-20T14:00:00+09:00
            # fromisoformat is available in Python 3.7+
            datetime.fromisoformat(start_time)
        except ValueError:
            raise ValueError("Invalid ISO 8601 format for start_time")

        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO slots (counselor_id, start_time, status) VALUES (?, ?, ?)",
                (counselor_id, start_time, "AVAILABLE")
            )
            conn.commit()

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Dict]:
        query = "SELECT * FROM slots WHERE status = 'AVAILABLE'"
        params = []

        if counselor_id:
            query += " AND counselor_id = ?"
            params.append(counselor_id)
        
        if date:
            # date is "YYYY-MM-DD", start_time is "YYYY-MM-DDTHH:MM:SS..."
            query += " AND start_time LIKE ?"
            params.append(f"{date}%")

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        with self._get_connection() as conn:
            # Step 2: Query 'slots' table for a row matching counselor_id, start_time, and status='AVAILABLE'
            cursor = conn.execute(
                "SELECT slot_id FROM slots WHERE counselor_id = ? AND start_time = ? AND status = 'AVAILABLE'",
                (counselor_id, start_time)
            )
            slot = cursor.fetchone()
            
            if not slot:
                raise ValueError("Slot unavailable")

            slot_id = slot['slot_id']
            booking_id = str(uuid.uuid4())

            try:
                # Step 3: Start transaction. Update slot status to 'BOOKED'. Insert into 'bookings' table.
                conn.execute("UPDATE slots SET status = 'BOOKED' WHERE slot_id = ?", (slot_id,))
                conn.execute(
                    "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                    (booking_id, slot_id, client_name, client_email, "CONFIRMED")
                )
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e

            return booking_id

    def lookup_booking(self, booking_id: str, client_email: str) -> Dict:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM bookings WHERE booking_id = ?",
                (booking_id,)
            )
            booking = cursor.fetchone()

            if not booking:
                raise ValueError("Booking not found")

            if booking['client_email'] != client_email:
                raise ValueError("Unauthorized")

            return dict(booking)

    def cancel_booking(self, booking_id: str, client_email: str) -> None:
        with self._get_connection() as conn:
            # Step 1: Query 'bookings' table for booking_id
            cursor = conn.execute(
                "SELECT slot_id, client_email, status FROM bookings WHERE booking_id = ?",
                (booking_id,)
            )
            booking = cursor.fetchone()

            if not booking:
                raise ValueError("Booking not found")

            # Step 2: Verify that the retrieved client_email matches the provided client_email
            if booking['client_email'] != client_email:
                raise ValueError("Unauthorized")
            
            if booking['status'] == 'CANCELLED':
                raise ValueError("Booking already cancelled")

            slot_id = booking['slot_id']

            try:
                # Step 3: Start transaction. Update booking status to 'CANCELLED'. Update associated slot status to 'AVAILABLE'.
                conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
                conn.execute("UPDATE slots SET status = 'AVAILABLE' WHERE slot_id = ?", (slot_id,))
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
