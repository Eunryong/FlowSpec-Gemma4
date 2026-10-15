import sqlite3
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from .exceptions import (
    SlotNotFoundError,
    SlotAlreadyBookedError,
    BookingNotFoundError,
    AuthenticationError,
    InvalidTimeFormatError,
    DatabaseError
)

class CounselingService:
    def __init__(self, db_path: str = "counseling.sqlite3"):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        try:
            conn = self._get_connection()
            conn.execute("PRAGMA foreign_keys = ON")
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
                    FOREIGN KEY(slot_id) REFERENCES slots(slot_id)
                )
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            raise DatabaseError(f"Failed to initialize database: {e}")

    def _validate_iso8601(self, time_str: str):
        try:
            datetime.fromisoformat(time_str)
        except ValueError:
            raise InvalidTimeFormatError(f"Invalid ISO 8601 format: {time_str}")

    def add_available_slot(self, counselor_id: str, start_time: str):
        self._validate_iso8601(start_time)
        try:
            conn = self._get_connection()
            conn.execute(
                "INSERT OR IGNORE INTO slots (counselor_id, start_time, is_booked) VALUES (?, ?, 0)",
                (counselor_id, start_time)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            raise DatabaseError(f"Error adding slot: {e}")

    def query_available_slots(self, counselor_id: Optional[str] = None, date: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            conn = self._get_connection()
            query = "SELECT counselor_id, start_time FROM slots WHERE is_booked = 0"
            params = []
            if counselor_id:
                query += " AND counselor_id = ?"
                params.append(counselor_id)
            if date:
                query += " AND start_time LIKE ?"
                params.append(f"{date}%")
            
            cursor = conn.execute(query, params)
            results = [dict(row) for row in cursor.fetchall()]
            conn.close()
            return results
        except Exception as e:
            raise DatabaseError(f"Error querying slots: {e}")

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str) -> str:
        self._validate_iso8601(start_time)
        booking_id = str(uuid.uuid4())
        
        try:
            conn = self._get_connection()
            conn.execute("BEGIN")
            
            cursor = conn.execute(
                "SELECT slot_id FROM slots WHERE counselor_id = ? AND start_time = ? AND is_booked = 0",
                (counselor_id, start_time)
            )
            row = cursor.fetchone()
            
            if not row:
                cursor = conn.execute(
                    "SELECT is_booked FROM slots WHERE counselor_id = ? AND start_time = ?",
                    (counselor_id, start_time)
                )
                row_status = cursor.fetchone()
                if not row_status:
                    conn.rollback()
                    conn.close()
                    raise SlotNotFoundError(f"Slot not found for counselor {counselor_id} at {start_time}")
                else:
                    conn.rollback()
                    conn.close()
                    raise SlotAlreadyBookedError(f"Slot already booked for counselor {counselor_id} at {start_time}")
            
            slot_id = row['slot_id']
            conn.execute("UPDATE slots SET is_booked = 1 WHERE slot_id = ?", (slot_id,))
            conn.execute(
                "INSERT INTO bookings (booking_id, slot_id, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)",
                (booking_id, slot_id, client_name, client_email, "CONFIRMED")
            )
            conn.commit()
            conn.close()
            return booking_id
        except (SlotNotFoundError, SlotAlreadyBookedError, InvalidTimeFormatError):
            raise
        except Exception as e:
            raise DatabaseError(f"Database error during booking: {e}")

    def lookup_booking(self, booking_id: str, client_email: str) -> Dict[str, Any]:
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT b.booking_id, b.client_name, b.client_email, b.status, s.counselor_id, s.start_time "
                "FROM bookings b JOIN slots s ON b.slot_id = s.slot_id "
                "WHERE b.booking_id = ?",
                (booking_id,)
            )
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                raise BookingNotFoundError(f"Booking {booking_id} not found")
            
            if row['client_email'] != client_email:
                raise AuthenticationError(f"Email mismatch for booking {booking_id}")
            
            return dict(row)
        except (BookingNotFoundError, AuthenticationError):
            raise
        except Exception as e:
            raise DatabaseError(f"Database error during lookup: {e}")

    def cancel_booking(self, booking_id: str, client_email: str):
        try:
            conn = self._get_connection()
            cursor = conn.execute(
                "SELECT b.slot_id, b.client_email FROM bookings b WHERE b.booking_id = ?",
                (booking_id,)
            )
            row = cursor.fetchone()
            
            if not row:
                conn.close()
                raise BookingNotFoundError(f"Booking {booking_id} not found")
            
            if row['client_email'] != client_email:
                conn.close()
                raise AuthenticationError(f"Email mismatch for booking {booking_id}")
            
            slot_id = row['slot_id']
            
            conn.execute("BEGIN")
            conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
            conn.execute("UPDATE slots SET is_booked = 0 WHERE slot_id = ?", (slot_id,))
            conn.commit()
            conn.close()
            return True
        except (BookingNotFoundError, AuthenticationError):
            raise
        except Exception as e:
            raise DatabaseError(f"Database error during cancellation: {e}")
