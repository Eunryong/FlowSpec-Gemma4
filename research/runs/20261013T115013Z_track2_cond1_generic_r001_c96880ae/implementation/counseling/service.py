import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from counseling.exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    BookingVerificationError
)

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
        self.db_path = db_path
        self._conn = None
        self._init_db()

    def _get_connection(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

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
                    FOREIGN KEY (slot_id) REFERENCES slots (slot_id)
                )
            """)
            conn.commit()

    def add_available_slot(self, counselor_id: str, start_time: str):
        """
        Adds a 30-minute counseling time slot.
        start_time should be ISO 8601 formatted.
        """
        # Basic validation of ISO 8601 format
        try:
            datetime.fromisoformat(start_time)
        except ValueError as e:
            raise ValueError(f"Invalid ISO 8601 start_time: {e}")

        with self._get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                    (counselor_id, start_time)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                # If the slot already exists, we can treat it as a no-op or raise an error.
                # Given the brief, we'll assume it's okay if it already exists.
                pass

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Queries open (unbooked) slots.
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
        Atomically marks a slot as booked and creates a booking record.
        """
        booking_id = str(uuid.uuid4())
        
        with self._get_connection() as conn:
            # Check if slot exists and is available
            cursor = conn.execute(
                "SELECT slot_id FROM slots WHERE counselor_id = ? AND start_time = ? AND is_booked = 0",
                (counselor_id, start_time)
            )
            row = cursor.fetchone()
            
            if not row:
                # Check if it exists but is booked
                cursor = conn.execute(
                    "SELECT 1 FROM slots WHERE counselor_id = ? AND start_time = ?",
                    (counselor_id, start_time)
                )
                if cursor.fetchone():
                    raise SlotAlreadyBookedError(f"Slot {start_time} for counselor {counselor_id} is already booked.")
                else:
                    raise SlotNotFoundError(f"Slot {start_time} for counselor {counselor_id} not found.")

            slot_id = row['slot_id']
            
            # Mark slot as booked
            conn.execute("UPDATE slots SET is_booked = 1 WHERE slot_id = ?", (slot_id,))
            
            # Create booking record
            conn.execute(
                "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                (booking_id, slot_id, client_name, client_email, "CONFIRMED")
            )
            
            return booking_id

    def lookup_booking(self, booking_id: str, client_email: str) -> Dict[str, Any]:
        """
        Look up booking by ID and email verification.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT b.booking_id, b.client_name, b.client_email, b.status, s.counselor_id, s.start_time 
                FROM bookings b 
                JOIN slots s ON b.slot_id = s.slot_id 
                WHERE b.booking_id = ?
                """,
                (booking_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                raise BookingNotFoundError(f"Booking {booking_id} not found.")
            
            if row['client_email'] != client_email:
                raise BookingVerificationError("Email mismatch for the provided booking ID.")
            
            return dict(row)

    def cancel_booking(self, booking_id: str, client_email: str):
        """
        Cancels a booking and re-opens the slot.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT slot_id, client_email, status FROM bookings WHERE booking_id = ?",
                (booking_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                raise BookingNotFoundError(f"Booking {booking_id} not found.")
            
            if row['client_email'] != client_email:
                raise BookingVerificationError("Email mismatch for the provided booking ID.")
            
            if row['status'] == "CANCELLED":
                raise CounselingError("Booking is already cancelled.")

            slot_id = row['slot_id']
            
            # Update booking status
            conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
            
            # Re-open the slot
            conn.execute("UPDATE slots SET is_booked = 0 WHERE slot_id = ?", (slot_id,))
