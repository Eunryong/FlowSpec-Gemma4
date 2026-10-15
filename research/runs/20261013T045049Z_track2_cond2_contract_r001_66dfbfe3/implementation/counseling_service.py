from dataclasses import dataclass
from typing import List, Optional
import sqlite3
import uuid
from datetime import datetime

# --- Domain Exceptions ---

class CounselingError(Exception):
    """Base exception for counseling service."""
    pass

class SlotNotFoundError(CounselingError):
    """Raised when a requested slot is not found."""
    pass

class SlotAlreadyBookedError(CounselingError):
    """Raised when a slot is already booked."""
    pass

class BookingNotFoundError(CounselingError):
    """Raised when a booking is not found."""
    pass

class AuthenticationError(CounselingError):
    """Raised when email verification fails."""
    pass

# --- Data Models ---

@dataclass
class Slot:
    id: int
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

# --- Service Implementation ---

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
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    FOREIGN KEY(slot_id) REFERENCES slots(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_slots_counselor_time ON slots(counselor_id, start_time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bookings_email ON bookings(client_email)")
            conn.commit()

    def add_available_slot(self, counselor_id: str, start_time: str) -> None:
        # Validate ISO 8601 format (basic check)
        try:
            # This handles most ISO 8601 formats including offsets
            datetime.fromisoformat(start_time)
        except ValueError as e:
            raise ValueError(f"Invalid ISO 8601 start_time: {e}")

        with self._get_connection() as conn:
            # Check if slot already exists for same counselor and time
            cursor = conn.execute(
                "SELECT id FROM slots WHERE counselor_id = ? AND start_time = ?",
                (counselor_id, start_time)
            )
            if cursor.fetchone():
                # Design says "Counselor adding a slot that already exists... (Edge Case)"
                # We'll treat it as a no-op or just return, but let's be explicit.
                return

            conn.execute(
                "INSERT INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                (counselor_id, start_time)
            )
            conn.commit()

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Slot]:
        query = "SELECT * FROM slots WHERE is_booked = 0"
        params = []

        if counselor_id:
            query += " AND counselor_id = ?"
            params.append(counselor_id)
        
        if date:
            # date is 'YYYY-MM-DD', start_time is ISO 8601 'YYYY-MM-DD...'
            query += " AND start_time LIKE ?"
            params.append(f"{date}%")

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [Slot(id=row['id'], counselor_id=row['counselor_id'], 
                         start_time=row['start_time'], is_booked=bool(row['is_booked'])) 
                    for row in cursor.fetchall()]

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        booking_id = str(uuid.uuid4())
        
        with self._get_connection() as conn:
            # Atomic transaction
            conn.execute("BEGIN TRANSACTION")
            try:
                # Find the slot
                cursor = conn.execute(
                    "SELECT id, is_booked FROM slots WHERE counselor_id = ? AND start_time = ?",
                    (counselor_id, start_time)
                )
                row = cursor.fetchone()
                
                if not row:
                    raise SlotNotFoundError(f"Slot not found for counselor {counselor_id} at {start_time}")
                
                if row['is_booked']:
                    raise SlotAlreadyBookedError(f"Slot at {start_time} is already booked")
                
                slot_id = row['id']
                
                # Mark slot as booked
                conn.execute("UPDATE slots SET is_booked = 1 WHERE id = ?", (slot_id,))
                
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

    def lookup_booking(self, booking_id: str, client_email: str) -> Booking:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM bookings WHERE booking_id = ?",
                (booking_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                raise BookingNotFoundError(f"Booking {booking_id} not found")
            
            if row['client_email'] != client_email:
                raise AuthenticationError("Email mismatch for the provided booking ID")
            
            return Booking(
                booking_id=row['booking_id'],
                slot_id=row['slot_id'],
                client_name=row['client_name'],
                client_email=row['client_email'],
                status=row['status']
            )

    def cancel_booking(self, booking_id: str, client_email: str) -> None:
        with self._get_connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                cursor = conn.execute(
                    "SELECT slot_id, status, client_email FROM bookings WHERE booking_id = ?",
                    (booking_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    raise BookingNotFoundError(f"Booking {booking_id} not found")
                
                if row['client_email'] != client_email:
                    raise AuthenticationError("Email mismatch for the provided booking ID")
                
                if row['status'] == "CANCELLED":
                    # Edge case: already cancelled. We can treat this as success or error.
                    # Design says "Client attempting to cancel a booking that is already cancelled" as edge case.
                    # Let's just return or raise. I'll return to be idempotent, or raise if strict.
                    # Actually, let's just return.
                    conn.commit()
                    return

                slot_id = row['slot_id']
                
                # Update booking status
                conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
                
                # Reopen the slot
                conn.execute("UPDATE slots SET is_booked = 0 WHERE id = ?", (slot_id,))
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise e
