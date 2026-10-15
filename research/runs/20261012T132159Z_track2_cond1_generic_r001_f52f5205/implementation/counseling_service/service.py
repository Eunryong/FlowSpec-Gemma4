import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from .exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    UnauthorizedBookingError,
    InvalidTimeFormatError
)

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
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
                    is_booked INTEGER DEFAULT 0
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

    def _validate_iso8601(self, time_str: str):
        try:
            # This is a basic check. Python's fromisoformat handles most ISO 8601.
            datetime.fromisoformat(time_str)
        except ValueError:
            raise InvalidTimeFormatError(f"Invalid ISO 8601 format: {time_str}")

    def add_available_slot(self, counselor_id: str, start_time: str):
        self._validate_iso8601(start_time)
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                (counselor_id, start_time)
            )
            conn.commit()

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Dict[str, Any]]:
        query = "SELECT counselor_id, start_time FROM slots WHERE is_booked = 0"
        params = []

        if counselor_id:
            query += " AND counselor_id = ?"
            params.append(counselor_id)
        
        if date:
            # date is YYYY-MM-DD. start_time is ISO 8601 (YYYY-MM-DDTHH:MM:SS...)
            query += " AND start_time LIKE ?"
            params.append(f"{date}%")

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        self._validate_iso8601(start_time)
        
        with self._get_connection() as conn:
            # Use a transaction to ensure atomicity
            conn.execute("BEGIN TRANSACTION")
            try:
                # Find the slot
                slot = conn.execute(
                    "SELECT slot_id, is_booked FROM slots WHERE counselor_id = ? AND start_time = ?",
                    (counselor_id, start_time)
                ).fetchone()

                if not slot:
                    raise SlotNotFoundError(f"Slot not found for counselor {counselor_id} at {start_time}")
                
                if slot['is_booked']:
                    raise SlotAlreadyBookedError(f"Slot at {start_time} is already booked")

                booking_id = str(uuid.uuid4())
                
                # Mark slot as booked
                conn.execute("UPDATE slots SET is_booked = 1 WHERE slot_id = ?", (slot['slot_id'],))
                
                # Create booking record
                conn.execute(
                    "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                    (booking_id, slot['slot_id'], client_name, client_email, "CONFIRMED")
                )
                
                conn.commit()
                return booking_id
            except Exception as e:
                conn.rollback()
                raise e

    def lookup_booking(self, booking_id: str, client_email: str) -> Dict[str, Any]:
        with self._get_connection() as conn:
            booking = conn.execute(
                """SELECT b.*, s.counselor_id, s.start_time 
                   FROM bookings b 
                   JOIN slots s ON b.slot_id = s.slot_id 
                   WHERE b.booking_id = ?""",
                (booking_id,)
            ).fetchone()

            if not booking:
                raise BookingNotFoundError(f"Booking {booking_id} not found")
            
            if booking['client_email'] != client_email:
                raise UnauthorizedBookingError("Email mismatch for this booking")
            
            return dict(booking)

    def cancel_booking(self, booking_id: str, client_email: str):
        with self._get_connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                booking = conn.execute(
                    "SELECT slot_id, client_email, status FROM bookings WHERE booking_id = ?",
                    (booking_id,)
                ).fetchone()

                if not booking:
                    raise BookingNotFoundError(f"Booking {booking_id} not found")
                
                if booking['client_email'] != client_email:
                    raise UnauthorizedBookingError("Email mismatch for this booking")
                
                if booking['status'] == "CANCELLED":
                    # The brief says "Attempting to cancel a booking that has already been cancelled" is an edge case.
                    # I'll treat it as a no-op or raise an error. Let's raise a specific error or just return.
                    # For consistency with "UnauthorizedBookingError", let's just return or raise.
                    # I'll raise a ValueError or similar.
                    raise ValueError("Booking is already cancelled")

                # Update booking status
                conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
                
                # Reopen slot
                conn.execute("UPDATE slots SET is_booked = 0 WHERE slot_id = ?", (booking['slot_id'],))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
