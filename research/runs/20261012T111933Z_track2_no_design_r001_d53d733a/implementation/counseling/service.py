import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from .exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    BookingVerificationError
)

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _get_connection(self):
        return self._conn

    def _init_db(self):
        with self._conn:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS slots (
                    slot_id TEXT PRIMARY KEY,
                    counselor_id TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    is_booked INTEGER DEFAULT 0
                )
            """)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id TEXT PRIMARY KEY,
                    slot_id TEXT NOT NULL,
                    client_name TEXT NOT NULL,
                    client_email TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (slot_id) REFERENCES slots (slot_id)
                )
            """)


    def add_available_slot(self, counselor_id: str, start_time: str):
        """
        Adds a 30-minute counseling time slot.
        start_time should be ISO 8601 formatted.
        """
        slot_id = f"{counselor_id}_{start_time}"
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO slots (slot_id, counselor_id, start_time, is_booked) VALUES (?, ?, ?, 0)",
                (slot_id, counselor_id, start_time)
            )
            conn.commit()
        return slot_id

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Query open (unbooked) slots.
        date filter is in 'YYYY-MM-DD' format.
        """
        query = "SELECT counselor_id, start_time FROM slots WHERE is_booked = 0"
        params = []

        if counselor_id:
            query += " AND counselor_id = ?"
            params.append(counselor_id)
        
        if date:
            query += " AND start_time LIKE ?"
            params.append(f"{date}%")

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        """
        Atomically marks the slot as booked and records the booking.
        """
        slot_id = f"{counselor_id}_{start_time}"
        booking_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            # Check if slot exists and is available
            slot = conn.execute("SELECT is_booked FROM slots WHERE slot_id = ?", (slot_id,)).fetchone()
            
            if slot is None:
                raise SlotNotFoundError(f"Slot {slot_id} not found.")
            
            if slot['is_booked'] == 1:
                raise SlotAlreadyBookedError(f"Slot {slot_id} is already booked.")

            # Atomic update
            conn.execute("UPDATE slots SET is_booked = 1 WHERE slot_id = ?", (slot_id,))
            conn.execute(
                "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                (booking_id, slot_id, client_name, client_email, "CONFIRMED")
            )
            conn.commit()
        
        return booking_id

    def lookup_booking(self, booking_id: str, client_email: str) -> Dict[str, Any]:
        """
        Lookup booking by ID and verify email.
        """
        with self._get_connection() as conn:
            booking = conn.execute(
                "SELECT b.*, s.counselor_id, s.start_time FROM bookings b JOIN slots s ON b.slot_id = s.slot_id WHERE b.booking_id = ?",
                (booking_id,)
            ).fetchone()

            if booking is None:
                raise BookingNotFoundError(f"Booking {booking_id} not found.")
            
            if booking['client_email'] != client_email:
                raise BookingVerificationError("Email mismatch for the provided booking ID.")

            return dict(booking)

    def cancel_booking(self, booking_id: str, client_email: str):
        """
        Cancels booking and reopens the slot.
        """
        with self._get_connection() as conn:
            booking = conn.execute("SELECT slot_id, client_email FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()

            if booking is None:
                raise BookingNotFoundError(f"Booking {booking_id} not found.")
            
            if booking['client_email'] != client_email:
                raise BookingVerificationError("Email mismatch for the provided booking ID.")

            slot_id = booking['slot_id']
            
            # Update booking status and reopen slot
            conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
            conn.execute("UPDATE slots SET is_booked = 0 WHERE slot_id = ?", (slot_id,))
            conn.commit()
