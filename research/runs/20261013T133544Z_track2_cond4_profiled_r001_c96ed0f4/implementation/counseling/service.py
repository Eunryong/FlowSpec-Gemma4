import uuid
from datetime import datetime
from typing import List, Optional
from .database import DatabaseManager
from .exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    BookingAlreadyCancelledError,
    InvalidTimeFormatError
)

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
        self.db = DatabaseManager(db_path)

    def _validate_iso8601(self, time_str: str):
        try:
            # This handles most ISO 8601 formats including offsets
            datetime.fromisoformat(time_str)
        except ValueError:
            raise InvalidTimeFormatError(f"Invalid ISO 8601 format: {time_str}")

    def add_available_slot(self, counselor_id: str, start_time: str) -> int:
        self._validate_iso8601(start_time)
        return self.db.add_slot(counselor_id, start_time)

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[dict]:
        return self.db.get_available_slots(counselor_id, date)

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        # First, find the slot_id for the given counselor and start_time
        # We need to do this inside the transaction to ensure consistency
        
        def transaction_logic(conn):
            # Find the slot
            cursor = conn.execute(
                "SELECT slot_id FROM slots WHERE counselor_id = ? AND start_time = ? AND is_booked = 0",
                (counselor_id, start_time)
            )
            row = cursor.fetchone()
            if not row:
                # Check if it exists but is booked
                cursor = conn.execute(
                    "SELECT slot_id FROM slots WHERE counselor_id = ? AND start_time = ?",
                    (counselor_id, start_time)
                )
                row_exists = cursor.fetchone()
                if not row_exists:
                    raise SlotNotFoundError(f"Slot for counselor {counselor_id} at {start_time} not found.")
                else:
                    raise SlotAlreadyBookedError(f"Slot for counselor {counselor_id} at {start_time} is already booked.")

            slot_id = row['slot_id']
            booking_id = str(uuid.uuid4())
            
            # Mark slot as booked
            conn.execute("UPDATE slots SET is_booked = 1 WHERE slot_id = ?", (slot_id,))
            
            # Create booking record
            conn.execute(
                "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                (booking_id, slot_id, client_name, client_email, "CONFIRMED")
            )
            
            return booking_id

        return self.db.execute_transaction(transaction_logic)

    def lookup_booking(self, booking_id: str, client_email: str) -> dict:
        booking = self.db.get_booking(booking_id)
        if not booking:
            raise BookingNotFoundError(f"Booking {booking_id} not found.")
        
        if booking['client_email'] != client_email:
            raise BookingNotFoundError(f"Booking {booking_id} not found for email {client_email}.")
        
        return booking

    def cancel_booking(self, booking_id: str, client_email: str):
        def transaction_logic(conn):
            # Get booking
            cursor = conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,))
            row = cursor.fetchone()
            
            if not row:
                raise BookingNotFoundError(f"Booking {booking_id} not found.")
            
            booking = dict(row)
            if booking['client_email'] != client_email:
                raise BookingNotFoundError(f"Booking {booking_id} not found for email {client_email}.")
            
            if booking['status'] == "CANCELLED":
                raise BookingAlreadyCancelledError(f"Booking {booking_id} is already cancelled.")
            
            slot_id = booking['slot_id']
            
            # Update booking status
            conn.execute("UPDATE bookings SET status = ? WHERE booking_id = ?", ("CANCELLED", booking_id))
            
            # Reopen slot
            conn.execute("UPDATE slots SET is_booked = 0 WHERE slot_id = ?", (slot_id,))
            
            return True

        return self.db.execute_transaction(transaction_logic)
