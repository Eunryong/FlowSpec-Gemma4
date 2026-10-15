import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional

class CommerceEngine:
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("CREATE TABLE IF NOT EXISTS products (sku TEXT PRIMARY KEY, name TEXT, price_cents INTEGER, available_stock INTEGER, reserved_stock INTEGER)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS wallets (customer_id TEXT PRIMARY KEY, balance_cents INTEGER)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS ledger_entries (entry_id TEXT PRIMARY KEY, customer_id TEXT, order_id TEXT, entry_type TEXT, amount_cents INTEGER, idempotency_key TEXT UNIQUE)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS coupons (code TEXT PRIMARY KEY, discount_percent INTEGER, max_uses INTEGER, current_uses INTEGER, min_order_cents INTEGER)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS orders (order_id TEXT PRIMARY KEY, customer_id TEXT, coupon_code TEXT, subtotal_cents INTEGER, discount_cents INTEGER, final_total_cents INTEGER, status TEXT)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS order_items (order_id TEXT, sku TEXT, quantity INTEGER)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS audit_logs (log_id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT, event_type TEXT, from_state TEXT, to_state TEXT, timestamp TEXT)")

    def register_product(self, sku: str, name: str, price_cents: int, initial_stock: int):
        if price_cents <= 0 or initial_stock < 0: raise ValueError("Invalid price or stock")
        try:
            with self.conn:
                self.conn.execute("INSERT INTO products VALUES (?, ?, ?, ?, ?)", (sku, name, price_cents, initial_stock, 0))
        except sqlite3.IntegrityError: raise ValueError("Duplicate SKU")

    def get_product(self, sku: str):
        row = self.conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        if not row: raise ValueError("Product not found")
        return dict(row)

    def create_wallet(self, customer_id: str, initial_balance_cents: int = 0):
        if initial_balance_cents < 0: raise ValueError("Balance cannot be negative")
        try:
            with self.conn:
                self.conn.execute("INSERT INTO wallets VALUES (?, ?)", (customer_id, initial_balance_cents))
                if initial_balance_cents > 0:
                    self.conn.execute("INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)", 
                                     (str(uuid.uuid4()), customer_id, None, "CREDIT", initial_balance_cents, f"init_{customer_id}"))
        except sqlite3.IntegrityError: raise ValueError("Duplicate customer ID")

    def deposit_funds(self, customer_id: str, amount_cents: int, idempotency_key: str):
        if amount_cents <= 0: raise ValueError("Amount must be positive")
        try:
            with self.conn:
                self.conn.execute("INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)", 
                                 (str(uuid.uuid4()), customer_id, None, "CREDIT", amount_cents, idempotency_key))
                self.conn.execute("UPDATE wallets SET balance_cents = balance_cents + ? WHERE customer_id = ?", (amount_cents, customer_id))
        except sqlite3.IntegrityError: pass
        return self.get_wallet_balance(customer_id)

    def get_wallet_balance(self, customer_id: str) -> int:
        row = self.conn.execute("SELECT balance_cents FROM wallets WHERE customer_id = ?", (customer_id,)).fetchone()
        if not row: raise ValueError("Wallet not found")
        return row['balance_cents']

    def create_coupon(self, code: str, discount_percent: int, max_uses: int, min_order_cents: int = 0):
        if not (1 <= discount_percent <= 90) or max_uses < 1 or min_order_cents < 0: raise ValueError("Invalid coupon params")
        with self.conn:
            self.conn.execute("INSERT INTO coupons VALUES (?, ?, ?, ?, ?)", (code, discount_percent, max_uses, 0, min_order_cents))

    def checkout_order(self, customer_id: str, items: List[Dict], coupon_code: Optional[str] = None, idempotency_key: Optional[str] = None):
        if not items: raise ValueError("Items cannot be empty")
        
        # Aggregate items
        aggregated = {}
        for item in items:
            sku = item['sku']
            qty = item['quantity']
            if qty <= 0: raise ValueError("Quantity must be > 0")
            aggregated[sku] = aggregated.get(sku, 0) + qty

        # Validate customer
        if not self.conn.execute("SELECT 1 FROM wallets WHERE customer_id = ?", (customer_id,)).fetchone():
            raise ValueError("Customer not found")

        # Calculate subtotal and validate stock
        subtotal = 0
        for sku, qty in aggregated.items():
            prod = self.get_product(sku)
            if prod['available_stock'] < qty: raise ValueError(f"Insufficient stock for {sku}")
            subtotal += prod['price_cents'] * qty

        # Coupon logic
        discount = 0
        if coupon_code:
            cpn = self.conn.execute("SELECT * FROM coupons WHERE code = ?", (coupon_code,)).fetchone()
            if not cpn or cpn['current_uses'] >= cpn['max_uses'] or subtotal < cpn['min_order_cents']:
                raise ValueError("Invalid or exhausted coupon")
            discount = (subtotal * cpn['discount_percent']) // 100
        
        final_total = subtotal - discount
        order_id = str(uuid.uuid4())

        try:
            with self.conn:
                # Reserve stock
                for sku, qty in aggregated.items():
                    self.conn.execute("UPDATE products SET available_stock = available_stock - ?, reserved_stock = reserved_stock + ? WHERE sku = ?", (qty, qty, sku))
                
                # Use coupon
                if coupon_code:
                    self.conn.execute("UPDATE coupons SET current_uses = current_uses + 1 WHERE code = ?", (coupon_code,))
                
                # Create order
                self.conn.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)", (order_id, customer_id, coupon_code, subtotal, discount, final_total, "RESERVED"))
                for sku, qty in aggregated.items():
                    self.conn.execute("INSERT INTO order_items VALUES (?, ?, ?)", (order_id, sku, qty))
                
                self.conn.execute("INSERT INTO audit_logs (order_id, event_type, from_state, to_state, timestamp) VALUES (?, ?, ?, ?, ?)", 
                                 (order_id, "ORDER_CREATED", None, "RESERVED", datetime.utcnow().isoformat()))

                # Payment
                balance = self.get_wallet_balance(customer_id)
                if balance >= final_total:
                    # Idempotency check for payment
                    pay_key = idempotency_key or f"pay_{order_id}"
                    if not self.conn.execute("SELECT 1 FROM ledger_entries WHERE idempotency_key = ?", (pay_key,)).fetchone():
                        self.conn.execute("INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), customer_id, order_id, "DEBIT", final_total, pay_key))
                        self.conn.execute("UPDATE wallets SET balance_cents = balance_cents - ? WHERE customer_id = ?", (final_total, customer_id))
                    
                    self.conn.execute("UPDATE orders SET status = 'PAID' WHERE order_id = ?", (order_id,))
                    self.conn.execute("INSERT INTO audit_logs (order_id, event_type, from_state, to_state, timestamp) VALUES (?, ?, ?, ?, ?)", 
                                     (order_id, "PAYMENT_SUCCESS", "RESERVED", "PAID", datetime.utcnow().isoformat()))
                    return self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
                else:
                    # Compensating Rollback
                    for sku, qty in aggregated.items():
                        self.conn.execute("UPDATE products SET available_stock = available_stock + ?, reserved_stock = reserved_stock - ? WHERE sku = ?", (qty, qty, sku))
                    if coupon_code:
                        self.conn.execute("UPDATE coupons SET current_uses = current_uses - 1 WHERE code = ?", (coupon_code,))
                    self.conn.execute("UPDATE orders SET status = 'FAILED_PAYMENT' WHERE order_id = ?", (order_id,))
                    self.conn.execute("INSERT INTO audit_logs (order_id, event_type, from_state, to_state, timestamp) VALUES (?, ?, ?, ?, ?)", 
                                     (order_id, "PAYMENT_FAILED", "RESERVED", "FAILED_PAYMENT", datetime.utcnow().isoformat()))
                    return self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        except Exception as e:
            raise e

    def ship_order(self, order_id: str):
        row = self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not row or row['status'] != 'PAID': raise ValueError("Order must be PAID to ship")
        
        with self.conn:
            items = self.conn.execute("SELECT sku, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
            for item in items:
                self.conn.execute("UPDATE products SET reserved_stock = reserved_stock - ? WHERE sku = ?", (item['quantity'], item['sku']))
            self.conn.execute("UPDATE orders SET status = 'SHIPPED' WHERE order_id = ?", (order_id,))
            self.conn.execute("INSERT INTO audit_logs (order_id, event_type, from_state, to_state, timestamp) VALUES (?, ?, ?, ?, ?)", 
                             (order_id, "SHIPMENT_COMPLETED", "PAID", "SHIPPED", datetime.utcnow().isoformat()))

    def cancel_order(self, order_id: str):
        row = self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not row or row['status'] not in ('PAID', 'RESERVED'): raise ValueError("Cannot cancel")
        
        with self.conn:
            items = self.conn.execute("SELECT sku, quantity FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
            for item in items:
                self.conn.execute("UPDATE products SET available_stock = available_stock + ?, reserved_stock = reserved_stock - ? WHERE sku = ?", (item['quantity'], item['quantity'], item['sku']))
            
            if row['coupon_code']:
                self.conn.execute("UPDATE coupons SET current_uses = current_uses - 1 WHERE code = ?", (row['coupon_code'],))
            
            if row['status'] == 'PAID':
                refund_key = f"refund_{order_id}"
                if not self.conn.execute("SELECT 1 FROM ledger_entries WHERE idempotency_key = ?", (refund_key,)).fetchone():
                    self.conn.execute("INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), row['customer_id'], order_id, "CREDIT", row['final_total_cents'], refund_key))
                    self.conn.execute("UPDATE wallets SET balance_cents = balance_cents + ? WHERE customer_id = ?", (row['final_total_cents'], row['customer_id']))
            
            self.conn.execute("UPDATE orders SET status = 'CANCELLED' WHERE order_id = ?", (order_id,))
            self.conn.execute("INSERT INTO audit_logs (order_id, event_type, from_state, to_state, timestamp) VALUES (?, ?, ?, ?, ?)", 
                             (order_id, "ORDER_CANCELLED", row['status'], "CANCELLED", datetime.utcnow().isoformat()))

    def get_order_audit_log(self, order_id: str):
        rows = self.conn.execute("SELECT * FROM audit_logs WHERE order_id = ? ORDER BY log_id ASC", (order_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_system_reconciliation(self):
        debits = self.conn.execute("SELECT SUM(amount_cents) FROM ledger_entries WHERE entry_type = 'DEBIT' AND order_id IS NOT NULL").fetchone()[0] or 0
        refunds = self.conn.execute("SELECT SUM(amount_cents) FROM ledger_entries WHERE entry_type = 'CREDIT' AND order_id IS NOT NULL").fetchone()[0] or 0
        net_captured = debits - refunds
        active_total = self.conn.execute("SELECT SUM(final_total_cents) FROM orders WHERE status IN ('PAID', 'SHIPPED')").fetchone()[0] or 0
        
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
