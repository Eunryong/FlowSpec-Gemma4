import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

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
        Adds an available counseling slot.
        start_time should be ISO 8601 formatted.
        """
        # Basic validation of ISO 8601 format (simplified)
        try:
            datetime.fromisoformat(start_time)
        except ValueError as e:
            raise ValueError(f"Invalid start_time format: {e}")

        with self._get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                    (counselor_id, start_time)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                raise ValueError(f"Slot for counselor {counselor_id} at {start_time} already exists.")

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
            # Use a transaction to ensure atomicity
            conn.execute("BEGIN TRANSACTION")
            try:
                # Check if slot exists and is available
                cursor = conn.execute(
                    "SELECT slot_id FROM slots WHERE counselor_id = ? AND start_time = ? AND is_booked = 0",
                    (counselor_id, start_time)
                )
                row = cursor.fetchone()
                
                if row is None:
                    raise ValueError("Slot is not available or does not exist.")
                
                slot_id = row['slot_id']
                
                # Mark slot as booked
                conn.execute(
                    "UPDATE slots SET is_booked = 1 WHERE slot_id = ?",
                    (slot_id,)
                )
                
                # Create booking record
                conn.execute(
                    "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                    (booking_id, slot_id, client_name, client_email, "CONFIRMED")
                )
                
                conn.commit()
                return booking_id
            except Exception as e:
                conn.rollback()
                raise e

    def lookup_booking(self, booking_id: str, client_email: str) -> Dict[str, Any]:
        """
        Looks up a booking by booking_id and verifies the client_email.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT b.*, s.counselor_id, s.start_time FROM bookings b JOIN slots s ON b.slot_id = s.slot_id WHERE b.booking_id = ?",
                (booking_id,)
            )
            row = cursor.fetchone()
            
            if row is None:
                raise ValueError("Booking not found.")
            
            if row['client_email'] != client_email:
                raise ValueError("Email mismatch. Unauthorized access to booking.")
            
            return dict(row)

    def cancel_booking(self, booking_id: str, client_email: str):
        """
        Cancels a booking and reopens the slot.
        """
        with self._get_connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                cursor = conn.execute(
                    "SELECT b.slot_id, b.client_email FROM bookings b WHERE b.booking_id = ?",
                    (booking_id,)
                )
                row = cursor.fetchone()
                
                if row is None:
                    raise ValueError("Booking not found.")
                
                if row['client_email'] != client_email:
                    raise ValueError("Email mismatch. Unauthorized cancellation.")
                
                slot_id = row['slot_id']
                
                # Update booking status
                conn.execute(
                    "UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?",
                    (booking_id,)
                )
                
                # Reopen the slot
                conn.execute(
                    "UPDATE slots SET is_booked = 0 WHERE slot_id = ?",
                    (slot_id,)
                )
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
