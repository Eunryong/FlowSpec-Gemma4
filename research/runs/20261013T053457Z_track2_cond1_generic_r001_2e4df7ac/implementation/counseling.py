import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

class CounselingError(Exception):
    """Base exception for counseling service."""
    pass

class SlotNotFoundError(CounselingError):
    """Raised when a requested slot does not exist."""
    pass

class SlotAlreadyBookedError(CounselingError):
    """Raised when a requested slot is already booked."""
    pass

class BookingNotFoundError(CounselingError):
    """Raised when a booking ID is not found."""
    pass

class BookingVerificationError(CounselingError):
    """Raised when the email does not match the booking."""
    pass

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
        # Basic validation of ISO 8601 (simplified)
        try:
            datetime.fromisoformat(start_time)
        except ValueError as e:
            raise ValueError(f"Invalid ISO 8601 format for start_time: {e}")

        with self._get_connection() as conn:
            try:
                conn.execute(
                    "INSERT INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                    (counselor_id, start_time)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                # Slot already exists for this counselor at this time
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
            # Use a transaction to ensure atomicity
            conn.execute("BEGIN TRANSACTION")
            try:
                # Find the slot and check if it's available
                cursor = conn.execute(
                    "SELECT slot_id FROM slots WHERE counselor_id = ? AND start_time = ? AND is_booked = 0",
                    (counselor_id, start_time)
                )
                row = cursor.fetchone()
                
                if not row:
                    # Check if it exists but is booked, or doesn't exist at all
                    cursor = conn.execute(
                        "SELECT is_booked FROM slots WHERE counselor_id = ? AND start_time = ?",
                        (counselor_id, start_time)
                    )
                    row_exists = cursor.fetchone()
                    if not row_exists:
                        raise SlotNotFoundError(f"Slot not found for counselor {counselor_id} at {start_time}")
                    else:
                        raise SlotAlreadyBookedError(f"Slot for counselor {counselor_id} at {start_time} is already booked")

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
        Looks up a booking by ID and verifies the email.
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT b.*, s.counselor_id, s.start_time FROM bookings b JOIN slots s ON b.slot_id = s.slot_id WHERE b.booking_id = ?",
                (booking_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                raise BookingNotFoundError(f"Booking with ID {booking_id} not found")
            
            if row['client_email'] != client_email:
                raise BookingVerificationError("Email verification failed for this booking")
            
            return dict(row)

    def cancel_booking(self, booking_id: str, client_email: str):
        """
        Cancels a booking and re-opens the slot.
        """
        with self._get_connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                cursor = conn.execute(
                    "SELECT b.slot_id, b.status FROM bookings b WHERE b.booking_id = ?",
                    (booking_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    raise BookingNotFoundError(f"Booking with ID {booking_id} not found")
                
                # Verify email (need to fetch email from bookings table)
                cursor = conn.execute("SELECT client_email FROM bookings WHERE booking_id = ?", (booking_id,))
                email_row = cursor.fetchone()
                if email_row['client_email'] != client_email:
                    raise BookingVerificationError("Email verification failed for this booking")
                
                if row['status'] == "CANCELLED":
                    # Already cancelled, we can just return or raise an error. 
                    # The brief says "Attempting to cancel a booking that is already in CANCELLED state" is an edge case.
                    # Let's raise an error to be explicit.
                    raise CounselingError("Booking is already cancelled")

                slot_id = row['slot_id']
                
                # Update booking status
                conn.execute(
                    "UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?",
                    (booking_id,)
                )
                
                # Re-open the slot
                conn.execute(
                    "UPDATE slots SET is_booked = 0 WHERE slot_id = ?",
                    (slot_id,)
                )
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
