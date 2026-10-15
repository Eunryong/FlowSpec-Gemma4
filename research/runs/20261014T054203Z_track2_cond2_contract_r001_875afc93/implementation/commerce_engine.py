import sqlite3
import uuid
from datetime import datetime
from typing import List, Dict, Optional

class CommerceEngine:
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS products (sku TEXT PRIMARY KEY, name TEXT, price_cents INTEGER, available_stock INTEGER, reserved_stock INTEGER);
            CREATE TABLE IF NOT EXISTS wallets (customer_id TEXT PRIMARY KEY, balance_cents INTEGER);
            CREATE TABLE IF NOT EXISTS ledger_entries (entry_id TEXT PRIMARY KEY, customer_id TEXT, order_id TEXT, entry_type TEXT, amount_cents INTEGER, idempotency_key TEXT UNIQUE);
            CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, discount_percent INTEGER, max_uses INTEGER, current_uses INTEGER, min_order_cents INTEGER);
            CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, customer_id TEXT, subtotal_cents INTEGER, discount_cents INTEGER, final_total_cents INTEGER, status TEXT, coupon_code TEXT);
            CREATE TABLE IF NOT EXISTS order_items (order_id TEXT, sku TEXT, quantity INTEGER, PRIMARY KEY(order_id, sku));
            CREATE TABLE IF NOT EXISTS audit_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, event_type TEXT, from_state TEXT, to_state TEXT, timestamp DATETIME);
        """)
        self.conn.commit()

    def register_product(self, sku: str, name: str, price_cents: int, initial_stock: int):
        if price_cents <= 0 or initial_stock < 0:
            raise ValueError("Invalid price or stock")
        try:
            self.conn.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?)", (sku, name, price_cents, initial_stock, 0))
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError("Duplicate SKU")

    def get_product(self, sku: str) -> dict:
        row = self.conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        if not row: raise ValueError("Product not found")
        return dict(row)

    def create_wallet(self, customer_id: str, initial_balance_cents: int = 0):
        if initial_balance_cents < 0: raise ValueError("Negative balance")
        try:
            self.conn.execute("INSERT INTO wallets VALUES (?, ?)", (customer_id, initial_balance_cents))
            if initial_balance_cents > 0:
                self.conn.execute("INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)", 
                                   (str(uuid.uuid4()), customer_id, None, "CREDIT", initial_balance_cents, f"init_{customer_id}"))
            self.conn.commit()
        except sqlite3.IntegrityError:
            raise ValueError("Duplicate customer ID")

    def deposit_funds(self, customer_id: str, amount_cents: int, idempotency_key: str):
        if amount_cents <= 0: raise ValueError("Amount must be positive")
        existing = self.conn.execute("SELECT * FROM ledger_entries WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        if existing: return
        
        self.conn.execute("UPDATE wallets SET balance_cents = balance_cents + ? WHERE customer_id = ?", (amount_cents, customer_id))
        self.conn.execute("INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)", 
                           (str(uuid.uuid4()), customer_id, None, "CREDIT", amount_cents, idempotency_key))
        self.conn.commit()

    def get_wallet_balance(self, customer_id: str) -> int:
        row = self.conn.execute("SELECT balance_cents FROM wallets WHERE customer_id = ?", (customer_id,)).fetchone()
        if not row: raise ValueError("Wallet not found")
        return row['balance_cents']

    def create_coupon(self, code: str, discount_percent: int, max_uses: int, min_order_cents: int = 0):
        if not (1 <= discount_percent <= 90) or max_uses < 1 or min_order_cents < 0:
            raise ValueError("Invalid coupon parameters")
        self.conn.execute("INSERT INTO coupons VALUES (?, ?, ?, ?, ?)", (code, discount_percent, max_uses, 0, min_order_cents))
        self.conn.commit()

    def checkout_order(self, customer_id: str, items: List[Dict], coupon_code: Optional[str] = None, idempotency_key: Optional[str] = None) -> dict:
        if not items: raise ValueError("Items cannot be empty")
        for item in items:
            if item['quantity'] <= 0: raise ValueError("Quantity must be positive")

        # Idempotency check
        if idempotency_key:
            existing = self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (idempotency_key,)).fetchone()
            if existing: return dict(existing)

        # 1. Validation
        subtotal = 0
        aggregated_items = {}
        for item in items:
            sku = item['sku']
            qty = item['quantity']
            aggregated_items[sku] = aggregated_items.get(sku, 0) + qty
            prod = self.get_product(sku)
            subtotal += prod['price_cents'] * qty

        # 2. Coupon
        discount = 0
        if coupon_code:
            cpn = self.conn.execute("SELECT * FROM coupons WHERE code = ?", (coupon_code,)).fetchone()
            if not cpn or cpn['current_uses'] >= cpn['max_uses'] or subtotal < cpn['min_order_cents']:
                raise ValueError("Invalid or exhausted coupon")
            discount = (subtotal * cpn['discount_percent']) // 100
        
        final_total = subtotal - discount
        order_id = idempotency_key if idempotency_key else str(uuid.uuid4())

        try:
            # 3. Reserve Stock & Coupon
            for sku, qty in aggregated_items.items():
                prod = self.get_product(sku)
                if prod['available_stock'] < qty: raise ValueError("Insufficient stock")
                self.conn.execute("UPDATE products SET available_stock = available_stock - ?, reserved_stock = reserved_stock + ? WHERE sku = ?", (qty, qty, sku))
            
            if coupon_code:
                self.conn.execute("UPDATE coupons SET current_uses = current_uses + 1 WHERE code = ?", (coupon_code,))
            
            self.conn.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", (order_id, customer_id, subtotal, discount, final_total, "RESERVED", coupon_code))
            for sku, qty in aggregated_items.items():
                self.conn.execute("INSERT INTO order_items VALUES (?, ?, ?)", (order_id, sku, qty))
            
            self._log_audit(order_id, "CHECKOUT_START", None, "RESERVED")

            # 4. Payment
            balance = self.get_wallet_balance(customer_id)
            if balance >= final_total:
                self.conn.execute("UPDATE wallets SET balance_cents = balance_cents - ? WHERE customer_id = ?", (final_total, customer_id))
                self.conn.execute("INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), customer_id, order_id, "DEBIT", final_total, f"pay_{order_id}"))
                self.conn.execute("UPDATE orders SET status = 'PAID' WHERE order_id = ?", (order_id,))
                self._log_audit(order_id, "PAYMENT_SUCCESS", "RESERVED", "PAID")
                self.conn.commit()
                return self._get_order(order_id)
            else:
                # Compensating Rollback
                for sku, qty in aggregated_items.items():
                    self.conn.execute("UPDATE products SET available_stock = available_stock + ?, reserved_stock = reserved_stock - ? WHERE sku = ?", (qty, qty, sku))
                if coupon_code:
                    self.conn.execute("UPDATE coupons SET current_uses = current_uses - 1 WHERE code = ?", (coupon_code,))
                self.conn.execute("UPDATE orders SET status = 'FAILED_PAYMENT' WHERE order_id = ?", (order_id,))
                self._log_audit(order_id, "PAYMENT_FAILED", "RESERVED", "FAILED_PAYMENT")
                self.conn.commit()
                return self._get_order(order_id)
        except Exception as e:
            self.conn.rollback()
            raise e

    def ship_order(self, order_id: str):
        order = self._get_order(order_id)
        if order['status'] != 'PAID': raise ValueError("Order must be PAID to ship")
        
        items = self.conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in items:
            self.conn.execute("UPDATE products SET reserved_stock = reserved_stock - ? WHERE sku = ?", (item['quantity'], item['sku']))
        
        self.conn.execute("UPDATE orders SET status = 'SHIPPED' WHERE order_id = ?", (order_id,))
        self._log_audit(order_id, "SHIPMENT", "PAID", "SHIPPED")
        self.conn.commit()

    def cancel_order(self, order_id: str):
        order = self._get_order(order_id)
        if order['status'] not in ('PAID', 'RESERVED'): raise ValueError("Cannot cancel order in current state")
        
        items = self.conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in items:
            self.conn.execute("UPDATE products SET available_stock = available_stock + ?, reserved_stock = reserved_stock - ? WHERE sku = ?", (item['quantity'], item['quantity'], item['sku']))
        
        if order['coupon_code']:
            self.conn.execute("UPDATE coupons SET current_uses = current_uses - 1 WHERE code = ?", (order['coupon_code'],))
        
        if order['status'] == 'PAID':
            self.conn.execute("UPDATE wallets SET balance_cents = balance_cents + ? WHERE customer_id = ?", (order['final_total_cents'], order['customer_id']))
            self.conn.execute("INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), order['customer_id'], order_id, "CREDIT", order['final_total_cents'], f"refund_{order_id}"))
        
        self.conn.execute("UPDATE orders SET status = 'CANCELLED' WHERE order_id = ?", (order_id,))
        self._log_audit(order_id, "CANCELLATION", order['status'], "CANCELLED")
        self.conn.commit()

    def get_order_audit_log(self, order_id: str) -> List[Dict]:
        logs = self.conn.execute("SELECT * FROM audit_logs WHERE order_id = ? ORDER BY log_id", (order_id,)).fetchall()
        return [dict(log) for log in logs]

    def get_system_reconciliation(self) -> Dict:
        debits = self.conn.execute("SELECT SUM(amount_cents) as total FROM ledger_entries WHERE entry_type = 'DEBIT' AND order_id IS NOT NULL").fetchone()['total'] or 0
        refunds = self.conn.execute("SELECT SUM(amount_cents) as total FROM ledger_entries WHERE entry_type = 'CREDIT' AND order_id IS NOT NULL").fetchone()['total'] or 0
        net_captured = debits - refunds
        
        active_total = self.conn.execute("SELECT SUM(final_total_cents) as total FROM orders WHERE status IN ('PAID', 'SHIPPED')").fetchone()['total'] or 0
        
        status_counts = {}
        for row in self.conn.execute("SELECT status, COUNT(*) as count FROM orders GROUP BY status"):
            status_counts[row['status']] = row['count']
            
        return {
            "total_order_debits_cents": debits,
            "total_order_refunds_cents": refunds,
            "net_captured_cents": net_captured,
            "active_orders_total_cents": active_total,
            "is_balanced": net_captured == active_total,
            "orders_by_status": status_counts
        }

    def _get_order(self, order_id: str) -> dict:
        row = self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not row: raise ValueError("Order not found")
        return dict(row)

    def _log_audit(self, order_id: str, event: str, from_s: Optional[str], to_s: str):
        self.conn.execute("INSERT INTO audit_logs (order_id, event_type, from_state, to_state, timestamp) VALUES (?, ?, ?, ?, ?)",
                           (order_id, event, from_s, to_s, datetime.now().isoformat()))
