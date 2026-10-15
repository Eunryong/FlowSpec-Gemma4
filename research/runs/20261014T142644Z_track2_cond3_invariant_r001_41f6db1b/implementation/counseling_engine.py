import sqlite3
import uuid
from datetime import datetime
from typing import List, Dict, Optional, Any

class CounselingBookingEngine:
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("CREATE TABLE IF NOT EXISTS counselors (counselor_id TEXT PRIMARY KEY, name TEXT, specialty TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS slots (slot_id TEXT PRIMARY KEY, counselor_id TEXT, start_time TEXT, status TEXT, UNIQUE(counselor_id, start_time))")
            self.conn.execute("CREATE TABLE IF NOT EXISTS session_passes (client_email TEXT PRIMARY KEY, remaining_sessions INTEGER, used_sessions INTEGER)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS pass_ledger (entry_id INTEGER PRIMARY KEY AUTOINCREMENT, client_email TEXT, booking_id TEXT, entry_type TEXT, delta_sessions INTEGER, idempotency_key TEXT UNIQUE)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS bookings (booking_id TEXT PRIMARY KEY, counselor_id TEXT, start_time TEXT, client_name TEXT, client_email TEXT, status TEXT, idempotency_key TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS waitlist (waitlist_id INTEGER PRIMARY KEY AUTOINCREMENT, counselor_id TEXT, start_time TEXT, client_name TEXT, client_email TEXT, status TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS audit_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, booking_id TEXT, event_type TEXT, from_status TEXT, to_status TEXT, timestamp TEXT)")

    # --- Subsystem A: Counselor Schedule ---
    def register_counselor(self, counselor_id: str, name: str, specialty: str):
        if not counselor_id or not name:
            raise ValueError("counselor_id and name must be non-empty")
        try:
            with self.conn:
                self.conn.execute("INSERT INTO counselors VALUES (?, ?, ?)", (counselor_id, name, specialty))
        except sqlite3.IntegrityError:
            raise ValueError(f"Counselor with id {counselor_id} already exists")

    def add_slot(self, counselor_id: str, start_time: str):
        with self.conn:
            c = self.conn.execute("SELECT 1 FROM counselors WHERE counselor_id = ?", (counselor_id,)).fetchone()
            if not c:
                raise ValueError("Counselor does not exist")
            try:
                slot_id = str(uuid.uuid4())
                self.conn.execute("INSERT INTO slots VALUES (?, ?, ?, ?)", (slot_id, counselor_id, start_time, "AVAILABLE"))
                res = self.conn.execute("SELECT * FROM slots WHERE slot_id = ?", (slot_id,)).fetchone()
                return dict(res)
            except sqlite3.IntegrityError:
                raise ValueError("Slot already exists for this counselor at this time")

    def block_slot(self, counselor_id: str, start_time: str):
        with self.conn:
            slot = self.conn.execute("SELECT * FROM slots WHERE counselor_id = ? AND start_time = ?", (counselor_id, start_time)).fetchone()
            if not slot or slot["status"] != "AVAILABLE":
                raise ValueError("Slot must exist and be AVAILABLE to be blocked")
            self.conn.execute("UPDATE slots SET status = 'BLOCKED' WHERE counselor_id = ? AND start_time = ?", (counselor_id, start_time))

    def query_available_slots(self, counselor_id: Optional[str] = None, date_prefix: Optional[str] = None):
        query = "SELECT * FROM slots WHERE status = 'AVAILABLE'"
        params = []
        if counselor_id:
            query += " AND counselor_id = ?"
            params.append(counselor_id)
        if date_prefix:
            query += " AND start_time LIKE ?"
            params.append(f"{date_prefix}%")
        query += " ORDER BY start_time ASC"
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    # --- Subsystem B: Session Pass ---
    def issue_session_pass(self, client_email: str, sessions_to_add: int, idempotency_key: str):
        if not client_email or sessions_to_add <= 0:
            raise ValueError("Invalid email or sessions to add")
        
        with self.conn:
            existing = self.conn.execute("SELECT * FROM pass_ledger WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing:
                res = self.conn.execute("SELECT * FROM session_passes WHERE client_email = ?", (client_email,)).fetchone()
                return dict(res) if res else {"client_email": client_email, "remaining_sessions": 0, "used_sessions": 0}

            self.conn.execute("INSERT INTO pass_ledger (client_email, entry_type, delta_sessions, idempotency_key) VALUES (?, ?, ?, ?)", 
                               (client_email, "ISSUE", sessions_to_add, idempotency_key))
            
            pass_rec = self.conn.execute("SELECT * FROM session_passes WHERE client_email = ?", (client_email,)).fetchone()
            if pass_rec:
                self.conn.execute("UPDATE session_passes SET remaining_sessions = remaining_sessions + ?, used_sessions = used_sessions WHERE client_email = ?", 
                                   (sessions_to_add, client_email))
            else:
                self.conn.execute("INSERT INTO session_passes VALUES (?, ?, ?)", (client_email, sessions_to_add, 0))
            
            res = self.conn.execute("SELECT * FROM session_passes WHERE client_email = ?", (client_email,)).fetchone()
            return dict(res)

    def get_session_pass(self, client_email: str):
        res = self.conn.execute("SELECT * FROM session_passes WHERE client_email = ?", (client_email,)).fetchone()
        if not res:
            return {"client_email": client_email, "remaining_sessions": 0, "used_sessions": 0}
        return dict(res)

    # --- Subsystem C: Booking ---
    def create_booking(self, counselor_id: str, start_time: str, client_name: str, client_email: str, idempotency_key: Optional[str] = None):
        if idempotency_key:
            existing = self.conn.execute("SELECT * FROM bookings WHERE idempotency_key = ? AND status = 'CONFIRMED'", (idempotency_key,)).fetchone()
            if existing:
                return dict(existing)

        with self.conn:
            slot = self.conn.execute("SELECT * FROM slots WHERE counselor_id = ? AND start_time = ?", (counselor_id, start_time)).fetchone()
            if not slot or slot["status"] != "AVAILABLE":
                raise ValueError("Slot is not available")
            
            pass_rec = self.conn.execute("SELECT * FROM session_passes WHERE client_email = ?", (client_email,)).fetchone()
            if not pass_rec or pass_rec["remaining_sessions"] < 1:
                raise ValueError("Insufficient sessions")

            booking_id = str(uuid.uuid4())
            self.conn.execute("UPDATE slots SET status = 'BOOKED' WHERE counselor_id = ? AND start_time = ?", (counselor_id, start_time))
            self.conn.execute("UPDATE session_passes SET remaining_sessions = remaining_sessions - 1, used_sessions = used_sessions + 1 WHERE client_email = ?", (client_email,))
            self.conn.execute("INSERT INTO pass_ledger (client_email, booking_id, entry_type, delta_sessions, idempotency_key) VALUES (?, ?, ?, ?, ?)", 
                               (client_email, booking_id, "USE", -1, f"use_{booking_id}"))
            self.conn.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?)", (booking_id, counselor_id, start_time, client_name, client_email, "CONFIRMED", idempotency_key))
            self.conn.execute("INSERT INTO audit_logs (booking_id, event_type, from_status, to_status, timestamp) VALUES (?, ?, ?, ?, ?)", 
                               (booking_id, "BOOKING_CREATED", None, "CONFIRMED", datetime.now().isoformat()))
            
            res = self.conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
            return dict(res)

    def lookup_booking(self, booking_id: str, client_email: str):
        res = self.conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
        if not res or res["client_email"] != client_email:
            raise ValueError("Booking not found or access denied")
        return dict(res)

    def reschedule_booking(self, booking_id: str, client_email: str, new_counselor_id: str, new_start_time: str):
        with self.conn:
            booking = self.conn.execute("SELECT * FROM bookings WHERE booking_id = ? AND client_email = ? AND status = 'CONFIRMED'", (booking_id, client_email)).fetchone()
            if not booking:
                raise ValueError("Booking not found or cannot be rescheduled")
            
            target_slot = self.conn.execute("SELECT * FROM slots WHERE counselor_id = ? AND start_time = ?", (new_counselor_id, new_start_time)).fetchone()
            if not target_slot or target_slot["status"] != "AVAILABLE":
                raise ValueError("Target slot is not available")

            old_counselor_id = booking["counselor_id"]
            old_start_time = booking["start_time"]

            # Release old slot and check waitlist
            self.conn.execute("UPDATE slots SET status = 'AVAILABLE' WHERE counselor_id = ? AND start_time = ?", (old_counselor_id, old_start_time))
            self._promote_waitlist(old_counselor_id, old_start_time)

            # Occupy new slot
            self.conn.execute("UPDATE slots SET status = 'BOOKED' WHERE counselor_id = ? AND start_time = ?", (new_counselor_id, new_start_time))
            self.conn.execute("UPDATE bookings SET counselor_id = ?, start_time = ? WHERE booking_id = ?", (new_counselor_id, new_start_time, booking_id))
            self.conn.execute("INSERT INTO audit_logs (booking_id, event_type, from_status, to_status, timestamp) VALUES (?, ?, ?, ?, ?)", 
                               (booking_id, "BOOKING_RESCHEDULED", "CONFIRMED", "CONFIRMED", datetime.now().isoformat()))
            
            res = self.conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
            return dict(res)

    # --- Subsystem D: Waitlist & Reconciliation ---
    def join_waitlist(self, counselor_id: str, start_time: str, client_name: str, client_email: str):
        with self.conn:
            slot = self.conn.execute("SELECT * FROM slots WHERE counselor_id = ? AND start_time = ?", (counselor_id, start_time)).fetchone()
            if not slot or slot["status"] != "BOOKED":
                raise ValueError("Slot must be BOOKED to join waitlist")
            
            pass_rec = self.conn.execute("SELECT * FROM session_passes WHERE client_email = ?", (client_email,)).fetchone()
            if not pass_rec or pass_rec["remaining_sessions"] < 1:
                raise ValueError("Insufficient sessions to join waitlist")
            
            self.conn.execute("INSERT INTO waitlist (counselor_id, start_time, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)", 
                               (counselor_id, start_time, client_name, client_email, "WAITING"))

    def cancel_booking(self, booking_id: str, client_email: str):
        with self.conn:
            booking = self.conn.execute("SELECT * FROM bookings WHERE booking_id = ? AND client_email = ? AND status = 'CONFIRMED'", (booking_id, client_email)).fetchone()
            if not booking:
                raise ValueError("Booking not found or already cancelled")
            
            self.conn.execute("UPDATE bookings SET status = 'CANCELLED' WHERE booking_id = ?", (booking_id,))
            self.conn.execute("UPDATE session_passes SET remaining_sessions = remaining_sessions + 1, used_sessions = used_sessions - 1 WHERE client_email = ?", (client_email,))
            self.conn.execute("INSERT INTO pass_ledger (client_email, booking_id, entry_type, delta_sessions, idempotency_key) VALUES (?, ?, ?, ?, ?)", 
                               (client_email, booking_id, "RESTORE", 1, f"restore_{booking_id}"))
            self.conn.execute("INSERT INTO audit_logs (booking_id, event_type, from_status, to_status, timestamp) VALUES (?, ?, ?, ?, ?)", 
                               (booking_id, "BOOKING_CANCELLED", "CONFIRMED", "CANCELLED", datetime.now().isoformat()))
            
            c_id, s_time = booking["counselor_id"], booking["start_time"]
            if not self._promote_waitlist(c_id, s_time):
                self.conn.execute("UPDATE slots SET status = 'AVAILABLE' WHERE counselor_id = ? AND start_time = ?", (c_id, s_time))
            
            res = self.conn.execute("SELECT * FROM bookings WHERE booking_id = ?", (booking_id,)).fetchone()
            return dict(res)

    def _promote_waitlist(self, counselor_id: str, start_time: str) -> bool:
        # FIFO order
        waitlisted = self.conn.execute("SELECT * FROM waitlist WHERE counselor_id = ? AND start_time = ? AND status = 'WAITING' ORDER BY waitlist_id ASC", (counselor_id, start_time)).fetchall()
        for w in waitlisted:
            pass_rec = self.conn.execute("SELECT * FROM session_passes WHERE client_email = ?", (w["client_email"],)).fetchone()
            if pass_rec and pass_rec["remaining_sessions"] >= 1:
                booking_id = str(uuid.uuid4())
                self.conn.execute("UPDATE waitlist SET status = 'PROMOTED' WHERE waitlist_id = ?", (w["waitlist_id"],))
                self.conn.execute("UPDATE session_passes SET remaining_sessions = remaining_sessions - 1, used_sessions = used_sessions + 1 WHERE client_email = ?", (w["client_email"],))
                self.conn.execute("INSERT INTO pass_ledger (client_email, booking_id, entry_type, delta_sessions, idempotency_key) VALUES (?, ?, ?, ?, ?)", 
                                   (w["client_email"], booking_id, "USE", -1, f"promote_{booking_id}"))
                self.conn.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?)", (booking_id, counselor_id, start_time, w["client_name"], w["client_email"], "CONFIRMED", None))
                self.conn.execute("INSERT INTO audit_logs (booking_id, event_type, from_status, to_status, timestamp) VALUES (?, ?, ?, ?, ?)", 
                                   (booking_id, "WAITLIST_PROMOTED", None, "CONFIRMED", datetime.now().isoformat()))
                self.conn.execute("UPDATE slots SET status = 'BOOKED' WHERE counselor_id = ? AND start_time = ?", (counselor_id, start_time))
                return True
        return False

    def get_booking_audit_log(self, booking_id: str):
        cursor = self.conn.execute("SELECT * FROM audit_logs WHERE booking_id = ? ORDER BY log_id ASC", (booking_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_system_reconciliation(self):
        total_issued = self.conn.execute("SELECT SUM(delta_sessions) FROM pass_ledger WHERE entry_type = 'ISSUE'").fetchone()[0] or 0
        total_remaining = self.conn.execute("SELECT SUM(remaining_sessions) FROM session_passes").fetchone()[0] or 0
        total_used = self.conn.execute("SELECT SUM(used_sessions) FROM session_passes").fetchone()[0] or 0
        active_bookings = self.conn.execute("SELECT COUNT(*) FROM bookings WHERE status = 'CONFIRMED'").fetchone()[0] or 0
        booked_slots = self.conn.execute("SELECT COUNT(*) FROM slots WHERE status = 'BOOKED'").fetchone()[0] or 0
        
        is_balanced = (total_issued == total_remaining + total_used) and (total_used == active_bookings) and (active_bookings == booked_slots)
        
        return {
            "total_issued_sessions": total_issued,
            "total_remaining_sessions": total_remaining,
            "total_used_sessions": total_used,
            "active_confirmed_bookings": active_bookings,
            "booked_slots_count": booked_slots,
            "is_balanced": is_balanced
        }
