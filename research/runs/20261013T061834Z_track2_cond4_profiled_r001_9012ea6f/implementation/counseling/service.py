import uuid
from datetime import datetime
from typing import List, Optional
from .repository import CounselingRepository, Slot, Booking
from .exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    BookingVerificationError,
)

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
        self.repository = CounselingRepository(db_path)

    def add_available_slot(self, counselor_id: str, start_time: str):
        """
        Adds an available counseling slot.
        Validates that start_time is ISO 8601.
        """
        try:
            datetime.fromisoformat(start_time)
        except ValueError:
            raise ValueError("start_time must be in ISO 8601 format")
        
        self.repository.add_slot(counselor_id, start_time)

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Slot]:
        """
        Queries available (unbooked) slots.
        """
        return self.repository.get_available_slots(counselor_id, date)

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        """
        Creates a booking for a specific slot.
        Ensures atomicity to prevent double-booking.
        """
        import sqlite3
        
        # We use a connection directly to manage the transaction for atomicity
        conn = self.repository._get_connection()
        try:
            # BEGIN IMMEDIATE starts a write transaction immediately, preventing other writes
            conn.execute("BEGIN IMMEDIATE")
            
            slot = self.repository.get_slot_by_counselor_and_time(counselor_id, start_time)
            
            if not slot:
                raise SlotNotFoundError(f"Slot for counselor {counselor_id} at {start_time} not found.")
            
            if slot.is_booked:
                raise SlotAlreadyBookedError(f"Slot for counselor {counselor_id} at {start_time} is already booked.")
            
            booking_id = str(uuid.uuid4())
            booking = Booking(
                booking_id=booking_id,
                slot_id=slot.slot_id,
                client_name=client_name,
                client_email=client_email,
                status="CONFIRMED"
            )
            
            self.repository.update_slot_status(slot.slot_id, True, conn=conn)
            self.repository.create_booking(booking, conn=conn)
            
            conn.commit()
            return booking_id
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def lookup_booking(self, booking_id: str, client_email: str) -> Booking:
        """
        Looks up a booking and verifies the client email.
        """
        booking = self.repository.get_booking(booking_id)
        if not booking:
            raise BookingNotFoundError(f"Booking with ID {booking_id} not found.")
        
        if booking.client_email != client_email:
            raise BookingVerificationError("Provided email does not match the booking record.")
        
        return booking

    def cancel_booking(self, booking_id: str, client_email: str):
        """
        Cancels a booking and re-opens the associated slot.
        """
        import sqlite3
        
        conn = self.repository._get_connection()
        try:
            conn.execute("BEGIN IMMEDIATE")
            
            booking = self.repository.get_booking(booking_id)
            if not booking:
                raise BookingNotFoundError(f"Booking with ID {booking_id} not found.")
            
            if booking.client_email != client_email:
                raise BookingVerificationError("Provided email does not match the booking record.")
            
            # Mark booking as CANCELLED
            self.repository.update_booking_status(booking_id, "CANCELLED", conn=conn)
            
            # Mark slot as available
            self.repository.update_slot_status(booking.slot_id, False, conn=conn)
            
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
