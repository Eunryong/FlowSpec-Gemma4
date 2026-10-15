import sqlite3
import uuid
from typing import List, Optional, NamedTuple
from datetime import datetime

class SlotNotFoundError(Exception):
    """Raised when the requested slot does not exist."""
    pass

class SlotAlreadyBookedError(Exception):
    """Raised when the slot is already marked as booked."""
    pass

class BookingNotFoundError(Exception):
    """Raised when the booking_id is not found."""
    pass

class AuthenticationError(Exception):
    """Raised when the client_email does not match the booking record."""
    pass

class Slot(NamedTuple):
    id: int
    counselor_id: str
    start_time: str
    is_booked: bool

class Booking(NamedTuple):
    booking_id: str
    slot_id: int
    client_name: str
    client_email: str
    status: str

class CounselingService:
    def __init__(self, db_path: str = 'counseling.sqlite3'):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    counselor_id TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    is_booked INTEGER DEFAULT 0,
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
                    FOREIGN KEY(slot_id) REFERENCES slots(id)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_slots_counselor ON slots(counselor_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_slots_time ON slots(start_time)")
            conn.commit()

    def add_available_slot(self, counselor_id: str, start_time: str) -> None:
        try:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                    (counselor_id, start_time)
                )
                conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError(f"Slot already exists for counselor {counselor_id} at {start_time}")

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Slot]:
        query = "SELECT id, counselor_id, start_time, is_booked FROM slots WHERE is_booked = 0"
        params = []
        filters = []

        if counselor_id:
            filters.append("counselor_id = ?")
            params.append(counselor_id)
        
        if date:
            filters.append("start_time LIKE ?")
            params.append(f"{date}%")

        if filters:
            query += " AND " + " AND ".join(filters)

        with self._get_connection() as conn:
            cursor = conn.execute(query, params)
            return [Slot(row['id'], row['counselor_id'], row['start_time'], bool(row['is_booked'])) for row in cursor]

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        booking_id = str(uuid.uuid4())
        
        with self._get_connection() as conn:
            # Use a transaction to ensure atomicity
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
                
                slot_id = row['id']
                if row['is_booked']:
                    raise SlotAlreadyBookedError(f"Slot at {start_time} is already booked")

                # Mark slot as booked
                conn.execute("UPDATE slots SET is_booked = 1 WHERE id = ?", (slot_id,))
                
                # Create booking record
                conn.execute(
                    "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                    (booking_id, slot_id, client_name, client_email, "CONFIRMED")
                )
                
                conn.commit()
                return booking_id
            except Exception:
                conn.rollback()
                raise

    def lookup_booking(self, booking_id: str, client_email: str) -> Booking:
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT booking_id, slot_id, client_name, client_email, status FROM bookings WHERE booking_id = ?",
                (booking_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                raise BookingNotFoundError(f"Booking with ID {booking_id} not found")
            
            if row['client_email'] != client_email:
                raise AuthenticationError("Client email does not match the booking record")
            
            return Booking(row['booking_id'], row['slot_id'], row['client_name'], row['client_email'], row['status'])

    def cancel_booking(self, booking_id: str, client_email: str) -> None:
        with self._get_connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                cursor = conn.execute(
                    "SELECT booking_id, slot_id, client_email FROM bookings WHERE booking_id = ?",
                    (booking_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    raise BookingNotFoundError(f"Booking with ID {booking_id} not found")
                
                if row['client_email'] != client_email:
                    raise AuthenticationError("Client email does not match the booking record")
                
                slot_id = row['slot_id']
                
                # Update booking status
                conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
                
                # Reopen the slot
                conn.execute("UPDATE slots SET is_booked = 0 WHERE id = ?", (slot_id,))
                
                conn.commit()
            except Exception:
                conn.rollback()
                raise
