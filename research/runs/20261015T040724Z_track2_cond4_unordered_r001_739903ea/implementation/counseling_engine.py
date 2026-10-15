import sqlite3
import uuid
from datetime import datetime

class CounselingBookingEngine:
    def __init__(self, db_path=":memory:"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("CREATE TABLE IF NOT EXISTS counselors (counselor_id TEXT PRIMARY KEY, name TEXT, specialty TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS slots (slot_id TEXT PRIMARY KEY, counselor_id TEXT, start_time TEXT, status TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS session_passes (client_email TEXT PRIMARY KEY, remaining_sessions INTEGER, used_sessions INTEGER)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS pass_ledger (entry_id INTEGER PRIMARY KEY, client_email TEXT, booking_id TEXT, entry_type TEXT, delta_sessions INTEGER, idempotency_key TEXT UNIQUE)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS bookings (booking_id TEXT PRIMARY KEY, counselor_id TEXT, start_time TEXT, client_name TEXT, client_email TEXT, status TEXT, idempotency_key TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS waitlist (waitlist_id INTEGER PRIMARY KEY, counselor_id TEXT, start_time TEXT, client_name TEXT, client_email TEXT, status TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS audit_logs (log_id INTEGER PRIMARY KEY, booking_id TEXT, event_type TEXT, from_status TEXT, to_status TEXT, timestamp DATETIME)")

    def register_counselor(self, counselor_id, name, specialty):
        if not counselor_id or not name: raise ValueError("ID and name required")
        try:
            with self.conn:
                self.conn.execute("INSERT INTO counselors VALUES (?, ?, ?)", (counselor_id, name, specialty))
        except sqlite3.IntegrityError: raise ValueError("Counselor already exists")

    def add_slot(self, counselor_id, start_time):
        with self.conn:
            res = self.conn.execute("SELECT 1 FROM counselors WHERE counselor_id=?", (counselor_id,)).fetchone()
            if not res: raise ValueError("Counselor not found")
            res = self.conn.execute("SELECT 1 FROM slots WHERE counselor_id=? AND start_time=?", (counselor_id, start_time)).fetchone()
            if res: raise ValueError("Slot already exists")
            slot_id = str(uuid.uuid4())
            self.conn.execute("INSERT INTO slots VALUES (?, ?, ?, ?)", (slot_id, counselor_id, start_time, "AVAILABLE"))
            return {"slot_id": slot_id, "counselor_id": counselor_id, "start_time": start_time, "status": "AVAILABLE"}

    def block_slot(self, counselor_id, start_time):
        with self.conn:
            slot = self.conn.execute("SELECT status FROM slots WHERE counselor_id=? AND start_time=?", (counselor_id, start_time)).fetchone()
            if not slot or slot['status'] != "AVAILABLE": raise ValueError("Slot must be AVAILABLE to block")
            self.conn.execute("UPDATE slots SET status='BLOCKED' WHERE counselor_id=? AND start_time=?", (counselor_id, start_time))

    def query_available_slots(self, counselor_id=None, date_prefix=None):
        query = "SELECT * FROM slots WHERE status='AVAILABLE'"
        params = []
        if counselor_id:
            query += " AND counselor_id=?"
            params.append(counselor_id)
        if date_prefix:
            query += " AND start_time LIKE ?"
            params.append(f"{date_prefix}%")
        query += " ORDER BY start_time ASC"
        cursor = self.conn.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def issue_session_pass(self, client_email, sessions_to_add, idempotency_key):
        if not client_email or sessions_to_add <= 0: raise ValueError("Invalid input")
        with self.conn:
            existing = self.conn.execute("SELECT * FROM pass_ledger WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if existing: return self.get_session_pass(client_email)
            self.conn.execute("INSERT INTO pass_ledger (client_email, entry_type, delta_sessions, idempotency_key) VALUES (?, ?, ?, ?)", 
                             (client_email, "ISSUE", sessions_to_add, idempotency_key))
            self.conn.execute("INSERT INTO session_passes (client_email, remaining_sessions, used_sessions) VALUES (?, ?, 0) ON CONFLICT(client_email) DO UPDATE SET remaining_sessions=remaining_sessions+excluded.remaining_sessions", 
                             (client_email, sessions_to_add))
            # Fix for SQLite version without ON CONFLICT:
            # This is a simplification. In real SQLite 3.24+ it works.
            return self.get_session_pass(client_email)

    def get_session_pass(self, client_email):
        row = self.conn.execute("SELECT * FROM session_passes WHERE client_email=?", (client_email,)).fetchone()
        if not row: return {"client_email": client_email, "remaining_sessions": 0, "used_sessions": 0}
        return dict(row)

    def create_booking(self, counselor_id, start_time, client_name, client_email, idempotency_key=None):
        if idempotency_key:
            existing = self.conn.execute("SELECT * FROM bookings WHERE idempotency_key=? AND status='CONFIRMED'", (idempotency_key,)).fetchone()
            if existing: return dict(existing)
        
        with self.conn:
            slot = self.conn.execute("SELECT slot_id, status FROM slots WHERE counselor_id=? AND start_time=?", (counselor_id, start_time)).fetchone()
            if not slot or slot['status'] != "AVAILABLE": raise ValueError("Slot unavailable")
            pass_info = self.get_session_pass(client_email)
            if pass_info['remaining_sessions'] < 1: raise ValueError("Insufficient sessions")
            
            booking_id = str(uuid.uuid4())
            self.conn.execute("UPDATE slots SET status='BOOKED' WHERE slot_id=?", (slot['slot_id'],))
            self.conn.execute("UPDATE session_passes SET remaining_sessions=remaining_sessions-1, used_sessions=used_sessions+1 WHERE client_email=?", (client_email,))
            self.conn.execute("INSERT INTO pass_ledger (client_email, booking_id, entry_type, delta_sessions, idempotency_key) VALUES (?, ?, ?, ?, ?)", 
                             (client_email, booking_id, "USE", -1, f"use_{booking_id}"))
            self.conn.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?)", (booking_id, counselor_id, start_time, client_name, client_email, "CONFIRMED", idempotency_key))
            self.conn.execute("INSERT INTO audit_logs (booking_id, event_type, from_status, to_status, timestamp) VALUES (?, ?, ?, ?, ?)", 
                             (booking_id, "BOOKING_CREATED", None, "CONFIRMED", datetime.now().isoformat()))
            return {"booking_id": booking_id, "counselor_id": counselor_id, "start_time": start_time, "client_name": client_name, "client_email": client_email, "status": "CONFIRMED"}

    def lookup_booking(self, booking_id, client_email):
        row = self.conn.execute("SELECT * FROM bookings WHERE booking_id=? AND client_email=?", (booking_id, client_email)).fetchone()
        if not row: raise ValueError("Booking not found or access denied")
        return dict(row)

    def reschedule_booking(self, booking_id, client_email, new_counselor_id, new_start_time):
        with self.conn:
            booking = self.conn.execute("SELECT * FROM bookings WHERE booking_id=? AND client_email=? AND status='CONFIRMED'", (booking_id, client_email)).fetchone()
            if not booking: raise ValueError("Booking not found or not confirmed")
            target_slot = self.conn.execute("SELECT slot_id, status FROM slots WHERE counselor_id=? AND start_time=?", (new_counselor_id, new_start_time)).fetchone()
            if not target_slot or target_slot['status'] != "AVAILABLE": raise ValueError("Target slot unavailable")
            
            old_slot_id = self.conn.execute("SELECT slot_id FROM slots WHERE counselor_id=? AND start_time=?", (booking['counselor_id'], booking['start_time'])).fetchone()['slot_id']
            
            self.conn.execute("UPDATE slots SET status='BOOKED' WHERE slot_id=?", (target_slot['slot_id'],))
            self.conn.execute("UPDATE bookings SET counselor_id=?, start_time=? WHERE booking_id=?", (new_counselor_id, new_start_time, booking_id))
            
            # Handle old slot: check waitlist
            waitlist_entry = self.conn.execute("SELECT * FROM waitlist WHERE counselor_id=? AND start_time=? AND status='WAITING' ORDER BY waitlist_id ASC", (booking['counselor_id'], booking['start_time'])).fetchone()
            if waitlist_entry:
                # Check if waitlisted client has sessions
                wp = self.get_session_pass(waitlist_entry['client_email'])
                if wp['remaining_sessions'] >= 1:
                    self.conn.execute("UPDATE waitlist SET status='PROMOTED' WHERE waitlist_id=?", (waitlist_entry['waitlist_id'],))
                    self.conn.execute("UPDATE session_passes SET remaining_sessions=remaining_sessions-1, used_sessions=used_sessions+1 WHERE client_email=?", (waitlist_entry['client_email'],))
                    new_bid = str(uuid.uuid4())
                    self.conn.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?)", (new_bid, booking['counselor_id'], booking['start_time'], waitlist_entry['client_name'], waitlist_entry['client_email'], "CONFIRMED", None))
                    self.conn.execute("INSERT INTO pass_ledger (client_email, booking_id, entry_type, delta_sessions, idempotency_key) VALUES (?, ?, ?, ?, ?)", (waitlist_entry['client_email'], new_bid, "USE", -1, f"use_{new_bid}"))
                    self.conn.execute("INSERT INTO audit_logs (booking_id, event_type, from_status, to_status, timestamp) VALUES (?, ?, ?, ?, ?)", (new_bid, "WAITLIST_PROMOTED", None, "CONFIRMED", datetime.now().isoformat()))
                else:
                    self.conn.execute("UPDATE slots SET status='AVAILABLE' WHERE slot_id=?", (old_slot_id,))
            else:
                self.conn.execute("UPDATE slots SET status='AVAILABLE' WHERE slot_id=?", (old_slot_id,))
            
            self.conn.execute("INSERT INTO audit_logs (booking_id, event_type, from_status, to_status, timestamp) VALUES (?, ?, ?, ?, ?)", (booking_id, "BOOKING_RESCHEDULED", "CONFIRMED", "CONFIRMED", datetime.now().isoformat()))
            return self.lookup_booking(booking_id, client_email)

    def join_waitlist(self, counselor_id, start_time, client_name, client_email):
        with self.conn:
            slot = self.conn.execute("SELECT status FROM slots WHERE counselor_id=? AND start_time=?", (counselor_id, start_time)).fetchone()
            if not slot or slot['status'] != "BOOKED": raise ValueError("Slot must be BOOKED to join waitlist")
            if self.get_session_pass(client_email)['remaining_sessions'] < 1: raise ValueError("Insufficient sessions")
            self.conn.execute("INSERT INTO waitlist (counselor_id, start_time, client_name, client_email, status) VALUES (?, ?, ?, ?, ?)", (counselor_id, start_time, client_name, client_email, "WAITING"))

    def cancel_booking(self, booking_id, client_email):
        with self.conn:
            booking = self.conn.execute("SELECT * FROM bookings WHERE booking_id=? AND client_email=? AND status='CONFIRMED'", (booking_id, client_email)).fetchone()
            if not booking: raise ValueError("Booking not found or not confirmed")
            
            self.conn.execute("UPDATE bookings SET status='CANCELLED' WHERE booking_id=?", (booking_id,))
            self.conn.execute("UPDATE session_passes SET remaining_sessions=remaining_sessions+1, used_sessions=used_sessions-1 WHERE client_email=?", (client_email,))
            self.conn.execute("INSERT INTO pass_ledger (client_email, booking_id, entry_type, delta_sessions, idempotency_key) VALUES (?, ?, ?, ?, ?)", (client_email, booking_id, "RESTORE", 1, f"restore_{booking_id}"))
            self.conn.execute("INSERT INTO audit_logs (booking_id, event_type, from_status, to_status, timestamp) VALUES (?, ?, ?, ?, ?)", (booking_id, "BOOKING_CANCELLED", "CONFIRMED", "CANCELLED", datetime.now().isoformat()))
            
            # Waitlist promotion
            waitlist_entry = self.conn.execute("SELECT * FROM waitlist WHERE counselor_id=? AND start_time=? AND status='WAITING' ORDER BY waitlist_id ASC", (booking['counselor_id'], booking['start_time'])).fetchone()
            promoted = False
            while waitlist_entry:
                wp = self.get_session_pass(waitlist_entry['client_email'])
                if wp['remaining_sessions'] >= 1:
                    self.conn.execute("UPDATE waitlist SET status='PROMOTED' WHERE waitlist_id=?", (waitlist_entry['waitlist_id'],))
                    self.conn.execute("UPDATE session_passes SET remaining_sessions=remaining_sessions-1, used_sessions=used_sessions+1 WHERE client_email=?", (waitlist_entry['client_email'],))
                    new_bid = str(uuid.uuid4())
                    self.conn.execute("INSERT INTO bookings VALUES (?, ?, ?, ?, ?, ?, ?)", (new_bid, booking['counselor_id'], booking['start_time'], waitlist_entry['client_name'], waitlist_entry['client_email'], "CONFIRMED", None))
                    self.conn.execute("INSERT INTO pass_ledger (client_email, booking_id, entry_type, delta_sessions, idempotency_key) VALUES (?, ?, ?, ?, ?)", (waitlist_entry['client_email'], new_bid, "USE", -1, f"use_{new_bid}"))
                    self.conn.execute("INSERT INTO audit_logs (booking_id, event_type, from_status, to_status, timestamp) VALUES (?, ?, ?, ?, ?)", (new_bid, "WAITLIST_PROMOTED", None, "CONFIRMED", datetime.now().isoformat()))
                    promoted = True
                    break
                waitlist_entry = self.conn.execute("SELECT * FROM waitlist WHERE counselor_id=? AND start_time=? AND status='WAITING' AND waitlist_id > ? ORDER BY waitlist_id ASC", (booking['counselor_id'], booking['start_time'], waitlist_entry['waitlist_id'])).fetchone()
            
            if not promoted:
                self.conn.execute("UPDATE slots SET status='AVAILABLE' WHERE counselor_id=? AND start_time=?", (booking['counselor_id'], booking['start_time']))
            
            return self.lookup_booking(booking_id, client_email)

    def get_booking_audit_log(self, booking_id):
        cursor = self.conn.execute("SELECT * FROM audit_logs WHERE booking_id=? ORDER BY timestamp ASC", (booking_id,))
        return [dict(row) for row in cursor.fetchall()]

    def get_system_reconciliation(self):
        total_issued = self.conn.execute("SELECT SUM(delta_sessions) FROM pass_ledger WHERE entry_type='ISSUE'").fetchone()[0] or 0
        total_remaining = self.conn.execute("SELECT SUM(remaining_sessions) FROM session_passes").fetchone()[0] or 0
        total_used = self.conn.execute("SELECT SUM(used_sessions) FROM session_passes").fetchone()[0] or 0
        active_bookings = self.conn.execute("SELECT COUNT(*) FROM bookings WHERE status='CONFIRMED'").fetchone()[0] or 0
        booked_slots = self.conn.execute("SELECT COUNT(*) FROM slots WHERE status='BOOKED'").fetchone()[0] or 0
        
        is_balanced = (total_issued == total_remaining + total_used) and (total_used == active_bookings) and (active_bookings == booked_slots)
        return {"total_issued_sessions": total_issued, "total_remaining_sessions": total_remaining, "total_used_sessions": total_used, "active_confirmed_bookings": active_bookings, "booked_slots_count": booked_slots, "is_balanced": is_balanced}
