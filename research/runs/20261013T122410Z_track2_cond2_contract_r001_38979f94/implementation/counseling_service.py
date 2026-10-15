import sqlite3
import uuid
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Slot:
    slot_id: int
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

class SlotNotFoundError(Exception):
    pass

class SlotAlreadyBookedError(Exception):
    pass

class BookingNotFoundError(Exception):
    pass

class AuthenticationError(Exception):
    pass

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
        self.db_path = db_path
        # Maintain a single connection to support :memory: databases
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS slots (
                    slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    counselor_id TEXT NOT NULL,
                    start_time TEXT NOT NULL,
                    is_booked INTEGER DEFAULT 0,
                    UNIQUE(counselor_id, start_time)
                )
            """)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS bookings (
                    booking_id TEXT PRIMARY KEY,
                    slot_id INTEGER NOT NULL,
                    client_name TEXT NOT NULL,
                    client_email TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY(slot_id) REFERENCES slots(slot_id)
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_slots_counselor ON slots(counselor_id)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_slots_time ON slots(start_time)")

    def add_available_slot(self, counselor_id: str, start_time: str) -> None:
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                    (counselor_id, start_time)
                )
        except sqlite3.IntegrityError:
            raise ValueError("Slot already exists for this counselor at this time.")

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Slot]:
        query = "SELECT * FROM slots WHERE is_booked = 0"
        params = []
        
        if counselor_id:
            query += " AND counselor_id = ?"
            params.append(counselor_id)
        
        if date:
            query += " AND start_time LIKE ?"
            params.append(f"{date}%")
            
        cursor = self.conn.execute(query, params)
        return [Slot(**dict(row)) for row in cursor.fetchall()]

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        booking_id = str(uuid.uuid4())
        
        with self.conn:
            # Find the slot
            cursor = self.conn.execute(
                "SELECT slot_id, is_booked FROM slots WHERE counselor_id = ? AND start_time = ?",
                (counselor_id, start_time)
            )
            row = cursor.fetchone()
            
            if not row:
                raise SlotNotFoundError(f"Slot not found for {counselor_id} at {start_time}")
            
            slot_id = row['slot_id']
            if row['is_booked']:
                raise SlotAlreadyBookedError(f"Slot {slot_id} is already booked")
            
            # Mark as booked
            self.conn.execute("UPDATE slots SET is_booked = 1 WHERE slot_id = ?", (slot_id,))
            
            # Create booking record
            self.conn.execute(
                "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                (booking_id, slot_id, client_name, client_email, "CONFIRMED")
            )
            
            return booking_id

    def lookup_booking(self, booking_id: str, client_email: str) -> Booking:
        cursor = self.conn.execute(
            "SELECT * FROM bookings WHERE booking_id = ?",
            (booking_id,)
        )
        row = cursor.fetchone()
        
        if not row:
            raise BookingNotFoundError(f"Booking {booking_id} not found")
        
        if row['client_email'] != client_email:
            raise AuthenticationError("Email mismatch for this booking")
        
        return Booking(**dict(row))

    def cancel_booking(self, booking_id: str, client_email: str) -> None:
        with self.conn:
            cursor = self.conn.execute(
                "SELECT slot_id, client_email FROM bookings WHERE booking_id = ?",
                (booking_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                raise BookingNotFoundError(f"Booking {booking_id} not found")
            
            if row['client_email'] != client_email:
                raise AuthenticationError("Email mismatch for this booking")
            
            slot_id = row['slot_id']
            
            # Update booking status
            self.conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
            
            # Re-open slot
            self.conn.execute("UPDATE slots SET is_booked = 0 WHERE slot_id = ?", (slot_id,))

    def close(self):
        self.conn.close()
