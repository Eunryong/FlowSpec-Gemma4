import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any

class CounselingError(Exception):
    """Base exception for counseling service."""
    pass

class SlotUnavailableError(CounselingError):
    """Raised when a slot is already booked or does not exist."""
    pass

class BookingNotFoundError(CounselingError):
    """Raised when a booking cannot be found."""
    pass

class PermissionError(CounselingError):
    """Raised when email verification fails."""
    pass

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
        self.db_path = db_path
        # Use a single connection for the service instance.
        # For :memory: databases, this is required to keep the schema.
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS slots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    counselor_id TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    is_booked BOOLEAN NOT NULL DEFAULT 0,
                    UNIQUE(counselor_id, start_time)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id TEXT PRIMARY KEY,
                    slot_id INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    client_email TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (status IN ('CONFIRMED', 'CANCELLED')),
                    FOREIGN KEY(slot_id) REFERENCES slots(id)
                )
            """)

    def add_available_slot(self, counselor_id: str, start_time: str):
        """
        Adds a new available slot.
        start_time should be ISO 8601 format.
        """
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                    (counselor_id, start_time)
                )
        except sqlite3.IntegrityError:
            raise ValueError(f"Slot already exists for counselor {counselor_id} at {start_time}")

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Queries available slots.
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
        
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        """
        Atomically creates a booking for a slot.
        """
        booking_id = str(uuid.uuid4())
        
        # Use a transaction to ensure atomicity
        try:
            with self.conn:
                # 1. Find the slot and lock it (SQLite doesn't have SELECT FOR UPDATE, 
                # but 'with self.conn' starts a transaction)
                cursor = self.conn.execute(
                    "SELECT id FROM slots WHERE counselor_id = ? AND start_time = ? AND is_booked = 0",
                    (counselor_id, start_time)
                )
                row = cursor.fetchone()
                
                if not row:
                    raise SlotUnavailableError(f"Slot {start_time} for {counselor_id} is not available.")
                
                slot_id = row['id']
                
                # 2. Mark slot as booked
                self.conn.execute(
                    "UPDATE slots SET is_booked = 1 WHERE id = ?",
                    (slot_id,)
                )
                
                # 3. Create booking record
                self.conn.execute(
                    "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                    (booking_id, slot_id, client_name, client_email, 'CONFIRMED')
                )
                
                return booking_id
        except sqlite3.Error as e:
            raise CounselingError(f"Database error: {e}")

    def lookup_booking(self, booking_id: str, client_email: str) -> Dict[str, Any]:
        """
        Looks up a booking by ID and email.
        """
        cursor = self.conn.execute(
            "SELECT b.booking_id, b.client_name, b.client_email, b.status, s.counselor_id, s.start_time "
            "FROM bookings b JOIN slots s ON b.slot_id = s.id "
            "WHERE b.booking_id = ? AND b.client_email = ?",
            (booking_id, client_email)
        )
        row = cursor.fetchone()
        if not row:
            # We don't distinguish between 'not found' and 'email mismatch' for security,
            # but the brief asks for verification.
            raise PermissionError("Invalid booking ID or email.")
        
        return dict(row)

    def cancel_booking(self, booking_id: str, client_email: str):
        """
        Cancels a booking and re-opens the slot.
        """
        try:
            with self.conn:
                # 1. Verify booking ownership
                cursor = self.conn.execute(
                    "SELECT slot_id, status FROM bookings WHERE booking_id = ? AND client_email = ?",
                    (booking_id, client_email)
                )
                row = cursor.fetchone()
                
                if not row:
                    raise PermissionError("Invalid booking ID or email.")
                
                if row['status'] == 'CANCELLED':
                    return # Idempotent
                
                slot_id = row['slot_id']
                
                # 2. Update booking status
                self.conn.execute(
                    "UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?",
                    (booking_id,)
                )
                
                # 3. Re-open the slot
                self.conn.execute(
                    "UPDATE slots SET is_booked = 0 WHERE id = ?",
                    (slot_id,)
                )
        except sqlite3.Error as e:
            raise CounselingError(f"Database error: {e}")
