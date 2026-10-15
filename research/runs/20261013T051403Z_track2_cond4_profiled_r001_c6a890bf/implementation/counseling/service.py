import uuid
from datetime import datetime
from typing import List, Optional
import sqlite3

from .repository import CounselingRepository
from .exceptions import SlotUnavailableError, BookingNotFoundError, UnauthorizedBookingError

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
        self.repository = CounselingRepository(db_path)

    def add_available_slot(self, counselor_id: str, start_time: str):
        """
        Adds an available slot. start_time must be ISO 8601.
        """
        try:
            # Basic ISO 8601 validation
            datetime.fromisoformat(start_time)
        except ValueError:
            raise ValueError("Invalid ISO 8601 format for start_time")

        try:
            self.repository.add_slot(counselor_id, start_time)
        except Exception as e:
            # Handle unique constraint violation (counselor_id, start_time)
            if "UNIQUE constraint failed" in str(e):
                raise ValueError(f"Slot already exists for counselor {counselor_id} at {start_time}")
            raise e

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[dict]:
        """
        Queries open slots.
        """
        return self.repository.get_available_slots(counselor_id, date)

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        """
        Atomically books a slot.
        """
        # Find the slot
        slots = self.repository.get_available_slots(counselor_id=counselor_id, date=None)
        target_slot = next((s for s in slots if s['start_time'] == start_time), None)
        
        if not target_slot:
            raise SlotUnavailableError(f"No available slot found for counselor {counselor_id} at {start_time}")

        slot_id = target_slot['slot_id']
        booking_id = str(uuid.uuid4())

        # Use BEGIN IMMEDIATE to prevent race conditions and ensure atomicity
        conn = sqlite3.connect(self.repository.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            # Re-verify availability inside transaction
            row = conn.execute("SELECT is_booked FROM slots WHERE slot_id = ?", (slot_id,)).fetchone()
            if not row or row['is_booked']:
                raise SlotUnavailableError("Slot was booked by another user")

            # Mark slot as booked
            conn.execute("UPDATE slots SET is_booked = 1 WHERE slot_id = ?", (slot_id,))
            
            # Create booking record
            conn.execute(
                "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                (booking_id, slot_id, client_name, client_email, "CONFIRMED")
            )
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            if isinstance(e, SlotUnavailableError):
                raise e
            raise e
        finally:
            conn.close()

        return booking_id

    def lookup_booking(self, booking_id: str, client_email: str) -> dict:
        """
        Looks up a booking by ID and email.
        """
        booking = self.repository.get_booking(booking_id)
        if not booking:
            raise BookingNotFoundError(f"Booking {booking_id} not found")
        
        if booking['client_email'] != client_email:
            raise UnauthorizedBookingError("Email mismatch for booking lookup")
            
        return booking

    def cancel_booking(self, booking_id: str, client_email: str):
        """
        Cancels a booking and reopens the slot.
        """
        booking = self.lookup_booking(booking_id, client_email)
        
        conn = sqlite3.connect(self.repository.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            # Update booking status
            conn.execute("UPDATE bookings SET status = ? WHERE booking_id = ?", ("CANCELLED", booking_id))
            
            # Reopen slot
            conn.execute("UPDATE slots SET is_booked = 0 WHERE slot_id = ?", (booking['slot_id'],))
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
