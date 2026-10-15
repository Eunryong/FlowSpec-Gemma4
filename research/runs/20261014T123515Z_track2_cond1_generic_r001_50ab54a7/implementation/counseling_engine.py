import sqlite3
import uuid
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Optional

class CounselingBookingEngine:
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("CREATE TABLE IF NOT EXISTS counselors (counselor_id TEXT PRIMARY KEY, name TEXT, specialty TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS slots (slot_id TEXT PRIMARY KEY, counselor_id TEXT, start_time TEXT, status TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS session_passes (client_email TEXT PRIMARY KEY, remaining_sessions INTEGER, used_sessions INTEGER)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS pass_ledger (entry_id TEXT PRIMARY KEY, client_email TEXT, booking_id TEXT, entry_type TEXT, delta_sessions INTEGER, idempotency_key TEXT UNIQUE)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS bookings (booking_id TEXT PRIMARY KEY, counselor_id TEXT, start_time TEXT, client_name TEXT, client_email TEXT, status TEXT, idempotency_key TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS waitlist (waitlist_id TEXT PRIMARY KEY, counselor_id TEXT, start_time TEXT, client_name TEXT, client_email TEXT, status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS audit_logs (log_id TEXT PRIMARY KEY, booking_id TEXT, event_type TEXT, from_status TEXT, to_status TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")

    def register_counselor(self, counselor_id: str, name: str, specialty: str):
        if not counselor_id or not name: raise ValueError("ID and name required")
        try:
            with self.conn:
                self.conn.execute("INSERT INTO counselors VALUES (?, ?, ?)", (counselor_id, name, specialty))
        except sqlite3.IntegrityError:
            raise ValueError("Counselor ID already exists")

    def add_slot(self, counselor_id: str, start_time: str):
        res = self.conn.execute("SELECT 1 FROM counselors WHERE counselor_id=?", (counselor_id,)).fetchone()
        if not res: raise ValueError("Counselor not found")
        slot_id = str(uuid.uuid4())
        try:
            with self.conn:
                self.conn.execute("INSERT INTO slots VALUES (?, ?, ?, ?)", (slot_id, counselor_id, start_time, "AVAILABLE"))
        except sqlite3.IntegrityError:
            raise ValueError("Slot already exists")
        return {"slot_id": slot_id, "counselor_id": counselor_id, "start_time": start_time, "status": "AVAILABLE"}

    def block_slot(self, counselor_id: str, start_time: str):
        slot = self.conn.execute("SELECT * FROM slots WHERE counselor_id=? AND start_time=?", (counselor_id, start_time)).fetchone()
        if not slot or slot["status"] != "AVAILABLE": raise ValueError("Slot not available for blocking")
        with self.conn:
            self.conn.execute("UPDATE slots SET status='BLOCKED' WHERE slot_id=?", (slot["slot_id"],))

    def query_available_slots(self, counselor_id: Optional[str] = None, date_prefix: Optional[str] = None):
        query = "SELECT * FROM slots WHERE status='AVAILABLE'"
        params = []
        if counselor_id:
            query += " AND counselor_id=?"
            params.append(counselor_id)
        if date_prefix:
            query += " AND start_time LIKE ?"
            params.append(f"{date_prefix}%")
        query += " ORDER BY start_time ASC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def issue_session_pass(self, client_email: str, sessions_to_add: int, idempotency_key: str):
        if not client_email or sessions_to_add <= 0: raise ValueError("Invalid input")
        with self.conn:
            existing = self.conn.execute("SELECT 1 FROM pass_ledger WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing:
                row = self.conn.execute("SELECT * FROM session_passes WHERE client_email=?", (client_email,)).fetchone()
                return dict(row) if row else {"client_email": client_email, "remaining_sessions": 0, "used_sessions": 0}
            
            self.conn.execute("INSERT INTO pass_ledger VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), client_email, None, "ISSUE", sessions_to_add, idempotency_key))
            self.conn.execute("INSERT INTO session_passes (client_email, remaining_sessions, used_sessions) VALUES (?, ?, ?) ON CONFLICT(client_email) DO UPDATE SET remaining_sessions=remaining_sessions+?", (client_email, sessions_to_add, 0, sessions_to_add))
            row = self.conn.execute("SELECT * FROM session_passes WHERE client_email=?", (client_email,)).fetchone()
            return dict(row)

    def get_session_pass(self, client_email: str):
        row = self.conn.execute("SELECT * FROM session_passes WHERE client_email=?", (client_email,)).fetchone()
        if not row: return {"client_email": client_email, "remaining_sessions": 0, "used_sessions": 0}
        return dict(row)

    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str, idempotency_key: Optional[str] = None):
        if idempotency_key:
            existing = self.conn.execute("SELECT * FROM bookings WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing: return dict(existing)

        slot = self.conn.execute("SELECT * FROM slots WHERE counselor_id=? AND start_time=?", (counselor_id, start_time)).fetchone()
        if not slot or slot["status"] != "AVAILABLE": raise ValueError("Slot unavailable")
        
        pass_info = self.get_session_pass(client_email)
        if pass_info["remaining_sessions"] < 1: raise ValueError("Insufficient sessions")

        booking_id = str(uuid.uuid4())
        with self.conn:
            self.conn.execute("UPDATE slots SET status='BOOKED' WHERE slot_id=?", (slot["slot_id"],))
            self.conn.execute("UPDATE session_passes SET remaining_sessions=remaining_sessions-1, used_sessions=used_sessions+1 WHERE client_email=?", (client_email,))
            self.conn.execute("INSERT INTO pass_ledger VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), client_email, booking_id, "USE", -1, str(uuid.uuid4())))
            self.conn.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?)", (booking_id, counselor_id, start_time, client_name, client_email, "CONFIRMED", idempotency_key))
            self.conn.execute("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), booking_id, "BOOKING_CREATED", None, "CONFIRMED", datetime.now().isoformat()))
        
        return self.lookup_booking(booking_id, client_email)

    def lookup_booking(self, booking_id: str, client_email: str):
        row = self.conn.execute("SELECT * FROM bookings WHERE booking_id=?", (booking_id,)).fetchone()
        if not row or row["client_email"] != client_email: raise ValueError("Booking not found or access denied")
        return dict(row)

    def reschedule_booking(self, booking_id: str, client_email: str, new_counselor_id: str, new_start_time: str):
        booking = self.lookup_booking(booking_id, client_email)
        if booking["status"] != "CONFIRMED": raise ValueError("Only confirmed bookings can be rescheduled")
        
        new_slot = self.conn.execute("SELECT * FROM slots WHERE counselor_id=? AND start_time=?", (new_counselor_id, new_start_time)).fetchone()
        if not new_slot or new_slot["status"] != "AVAILABLE": raise ValueError("Target slot unavailable")

        old_slot_id = self.conn.execute("SELECT slot_id FROM slots WHERE counselor_id=? AND start_time=?", (booking["counselor_id"], booking["start_time"])).fetchone()["slot_id"]

        with self.conn:
            self.conn.execute("UPDATE slots SET status='BOOKED' WHERE slot_id=?", (new_slot["slot_id"],))
            self.conn.execute("UPDATE bookings SET counselor_id=?, start_time=? WHERE booking_id=?", (new_counselor_id, new_start_time, booking_id))
            self.conn.execute("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), booking_id, "BOOKING_RESCHEDULED", "CONFIRMED", "CONFIRMED", datetime.now().isoformat()))
            
            # Release old slot and check waitlist
            self.conn.execute("UPDATE slots SET status='AVAILABLE' WHERE slot_id=?", (old_slot_id,))
            self._process_waitlist(booking["counselor_id"], booking["start_time"])
            
        return self.lookup_booking(booking_id, client_email)

    def join_waitlist(self, counselor_id: str, start_time: str, client_name: str, client_email: str):
        slot = self.conn.execute("SELECT * FROM slots WHERE counselor_id=? AND start_time=?", (counselor_id, start_time)).fetchone()
        if not slot or slot["status"] != "BOOKED": raise ValueError("Slot must be BOOKED to join waitlist")
        if self.get_session_pass(client_email)["remaining_sessions"] < 1: raise ValueError("Insufficient sessions")
        
        with self.conn:
            self.conn.execute("INSERT INTO waitlist (waitlist_id, counselor_id, start_time, client_name, client_email, status) VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), counselor_id, start_time, client_name, client_email, "WAITING"))

    def cancel_booking(self, booking_id: str, client_email: str):
        row = self.conn.execute("SELECT * FROM bookings WHERE booking_id=? AND client_email=?", (booking_id, client_email)).fetchone()
        if not row or row["status"] != "CONFIRMED": raise ValueError("Booking not found or already cancelled")
        
        booking = dict(row)
        with self.conn:
            self.conn.execute("UPDATE bookings SET status='CANCELLED' WHERE booking_id=?", (booking_id,))
            self.conn.execute("UPDATE session_passes SET remaining_sessions=remaining_sessions+1, used_sessions=used_sessions-1 WHERE client_email=?", (client_email,))
            self.conn.execute("INSERT INTO pass_ledger VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), client_email, booking_id, "RESTORE", 1, str(uuid.uuid4())))
            self.conn.execute("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), booking_id, "BOOKING_CANCELLED", "CONFIRMED", "CANCELLED", datetime.now().isoformat()))
            
            self._process_waitlist(booking["counselor_id"], booking["start_time"])
            
        return self.lookup_booking(booking_id, client_email) if booking["status"] != "CANCELLED" else booking

    def _process_waitlist(self, counselor_id: str, start_time: str):
        # This must be called within a transaction
        waitlist_entry = self.conn.execute("SELECT * FROM waitlist WHERE counselor_id=? AND start_time=? AND status='WAITING' ORDER BY created_at ASC LIMIT 1", (counselor_id, start_time)).fetchone()
        while waitlist_entry:
            client_email = waitlist_entry["client_email"]
            pass_info = self.conn.execute("SELECT * FROM session_passes WHERE client_email=?", (client_email,)).fetchone()
            remaining = pass_info["remaining_sessions"] if pass_info else 0
            
            if remaining >= 1:
                self.conn.execute("UPDATE waitlist SET status='PROMOTED' WHERE waitlist_id=?", (waitlist_entry["waitlist_id"],))
                self.conn.execute("UPDATE session_passes SET remaining_sessions=remaining_sessions-1, used_sessions=used_sessions+1 WHERE client_email=?", (client_email,))
                booking_id = str(uuid.uuid4())
                self.conn.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?)", (booking_id, counselor_id, start_time, waitlist_entry["client_name"], client_email, "CONFIRMED", None))
                self.conn.execute("INSERT INTO pass_ledger VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), client_email, booking_id, "USE", -1, str(uuid.uuid4())))
                self.conn.execute("INSERT INTO audit_logs VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), booking_id, "WAITLIST_PROMOTED", None, "CONFIRMED", datetime.now().isoformat()))
                self.conn.execute("UPDATE slots SET status='BOOKED' WHERE counselor_id=? AND start_time=?", (counselor_id, start_time))
                break
            else:
                self.conn.execute("UPDATE waitlist SET status='EXPIRED' WHERE waitlist_id=?", (waitlist_entry["waitlist_id"],))
                waitlist_entry = self.conn.execute("SELECT * FROM waitlist WHERE counselor_id=? AND start_time=? AND status='WAITING' ORDER BY created_at ASC LIMIT 1", (counselor_id, start_time)).fetchone()

    def get_booking_audit_log(self, booking_id: str):
        rows = self.conn.execute("SELECT * FROM audit_logs WHERE booking_id=? ORDER BY timestamp ASC", (booking_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_system_reconciliation(self):
        total_issued = self.conn.execute("SELECT SUM(delta_sessions) FROM pass_ledger WHERE entry_type='ISSUE'").fetchone()[0] or 0
        total_remaining = self.conn.execute("SELECT SUM(remaining_sessions) FROM session_passes").fetchone()[0] or 0
        total_used = self.conn.execute("SELECT SUM(used_sessions) FROM session_passes").fetchone()[0] or 0
        active_bookings = self.conn.execute("SELECT COUNT(*) FROM bookings WHERE status='CONFIRMED'").fetchone()[0] or 0
        booked_slots = self.conn.execute("SELECT COUNT(*) FROM slots WHERE status='BOOKED'").fetchone()[0] or 0
        
        is_balanced = (total_issued == total_remaining + total_used) and (total_used == active_bookings) and (active_bookings == booked_slots)
        return {
            "total_issued_sessions": total_issued,
            "total_remaining_sessions": total_remaining,
            "total_used_sessions": total_used,
            "active_confirmed_bookings": active_bookings,
            "booked_slots_count": booked_slots,
            "is_balanced": is_balanced
        }
