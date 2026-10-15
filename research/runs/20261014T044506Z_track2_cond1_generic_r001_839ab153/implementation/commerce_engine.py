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
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    sku TEXT PRIMARY KEY,
                    name TEXT,
                    price_cents INTEGER,
                    available_stock INTEGER,
                    reserved_stock INTEGER
                )""")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS wallets (
                    customer_id TEXT PRIMARY KEY,
                    balance_cents INTEGER
                )""")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS ledger_entries (
                    entry_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    order_id TEXT,
                    entry_type TEXT,
                    amount_cents INTEGER,
                    idempotency_key TEXT UNIQUE
                )""")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS coupons (
                    code TEXT PRIMARY KEY,
                    discount_percent INTEGER,
                    max_uses INTEGER,
                    min_order_cents INTEGER,
                    current_uses INTEGER
                )""")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    subtotal_cents INTEGER,
                    discount_cents INTEGER,
                    final_total_cents INTEGER,
                    status TEXT,
                    coupon_code TEXT
                )""")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS order_items (
                    order_id TEXT,
                    sku TEXT,
                    quantity INTEGER,
                    PRIMARY KEY (order_id, sku)
                )""")
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id TEXT,
                    event_type TEXT,
                    from_state TEXT,
                    to_state TEXT,
                    timestamp DATETIME
                )""")

    # --- Warehouse Subsystem ---
    def register_product(self, sku: str, name: str, price_cents: int, initial_stock: int):
        if price_cents <= 0 or initial_stock < 0:
            raise ValueError("Invalid price or stock")
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO products VALUES (?, ?, ?, ?, ?)",
                    (sku, name, price_cents, initial_stock, 0)
                )
        except sqlite3.IntegrityError:
            raise ValueError("Duplicate SKU")

    def get_product(self, sku: str):
        row = self.conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
        if not row:
            raise KeyError("Product not found")
        return dict(row)

    # --- Wallet Subsystem ---
    def create_wallet(self, customer_id: str, initial_balance_cents: int = 0):
        if initial_balance_cents < 0:
            raise ValueError("Initial balance cannot be negative")
        try:
            with self.conn:
                self.conn.execute("INSERT INTO wallets VALUES (?, ?)", (customer_id, initial_balance_cents))
                if initial_balance_cents > 0:
                    self.conn.execute(
                        "INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), customer_id, None, "CREDIT", initial_balance_cents, f"init_{customer_id}")
                    )
        except sqlite3.IntegrityError:
            raise ValueError("Customer already exists")

    def deposit_funds(self, customer_id: str, amount_cents: int, idempotency_key: str):
        if amount_cents <= 0:
            raise ValueError("Deposit amount must be positive")
        
        existing = self.conn.execute("SELECT * FROM ledger_entries WHERE idempotency_key = ?", (idempotency_key,)).fetchone()
        if existing:
            return True

        with self.conn:
            self.conn.execute("UPDATE wallets SET balance_cents = balance_cents + ? WHERE customer_id = ?", (amount_cents, customer_id))
            self.conn.execute(
                "INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), customer_id, None, "CREDIT", amount_cents, idempotency_key)
            )
        return True

    def get_wallet_balance(self, customer_id: str) -> int:
        row = self.conn.execute("SELECT balance_cents FROM wallets WHERE customer_id = ?", (customer_id,)).fetchone()
        if not row:
            raise KeyError("Wallet not found")
        return row['balance_cents']

    # --- Coupon Subsystem ---
    def create_coupon(self, code: str, discount_percent: int, max_uses: int, min_order_cents: int = 0):
        if not (1 <= discount_percent <= 90) or max_uses < 1 or min_order_cents < 0:
            raise ValueError("Invalid coupon parameters")
        with self.conn:
            self.conn.execute(
                "INSERT INTO coupons VALUES (?, ?, ?, ?, ?)",
                (code, discount_percent, max_uses, min_order_cents, 0)
            )

    # --- Order Saga ---
    def checkout_order(self, customer_id: str, items: List[Dict], coupon_code: Optional[str] = None, idempotency_key: Optional[str] = None):
        if not items:
            raise ValueError("Items cannot be empty")
        for item in items:
            if item['quantity'] <= 0:
                raise ValueError("Quantity must be positive")

        # Aggregate quantities
        aggregated_items = {}
        for item in items:
            aggregated_items[item['sku']] = aggregated_items.get(item['sku'], 0) + item['quantity']

        # 1. Validate Customer & Products & Stock
        wallet = self.conn.execute("SELECT * FROM wallets WHERE customer_id = ?", (customer_id,)).fetchone()
        if not wallet:
            raise ValueError("Customer not found")

        subtotal = 0
        for sku, qty in aggregated_items.items():
            prod = self.conn.execute("SELECT * FROM products WHERE sku = ?", (sku,)).fetchone()
            if not prod:
                raise ValueError(f"Product {sku} not found")
            if prod['available_stock'] < qty:
                raise ValueError(f"Insufficient stock for {sku}")
            subtotal += prod['price_cents'] * qty

        # 2. Coupon Validation
        discount = 0
        if coupon_code:
            coupon = self.conn.execute("SELECT * FROM coupons WHERE code = ?", (coupon_code,)).fetchone()
            if not coupon or coupon['current_uses'] >= coupon['max_uses'] or subtotal < coupon['min_order_cents']:
                raise ValueError("Invalid or exhausted coupon")
            discount = (subtotal * coupon['discount_percent']) // 100

        final_total = subtotal - discount
        order_id = str(uuid.uuid4())

        # 3. Reserve Stock & Coupon
        try:
            with self.conn:
                for sku, qty in aggregated_items.items():
                    self.conn.execute(
                        "UPDATE products SET available_stock = available_stock - ?, reserved_stock = reserved_stock + ? WHERE sku = ?",
                        (qty, qty, sku)
                    )
                if coupon_code:
                    self.conn.execute("UPDATE coupons SET current_uses = current_uses + 1 WHERE code = ?", (coupon_code,))
                
                self.conn.execute(
                    "INSERT INTO orders VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (order_id, customer_id, subtotal, discount, final_total, "RESERVED", coupon_code)
                )
                for sku, qty in aggregated_items.items():
                    self.conn.execute("INSERT INTO order_items VALUES (?, ?, ?)", (order_id, sku, qty))
                
                self._log_audit(order_id, "ORDER_CREATED", None, "RESERVED")

                # 4. Payment
                balance = self.get_wallet_balance(customer_id)
                if balance >= final_total:
                    # Use idempotency key for payment if provided, otherwise generate one
                    pay_key = idempotency_key or f"pay_{order_id}"
                    
                    # Check if payment already happened (idempotency)
                    existing_pay = self.conn.execute("SELECT * FROM ledger_entries WHERE idempotency_key = ?", (pay_key,)).fetchone()
                    if existing_pay:
                        # This case is unlikely in a single checkout call but good for robustness
                        pass 
                    else:
                        self.conn.execute("UPDATE wallets SET balance_cents = balance_cents - ? WHERE customer_id = ?", (final_total, customer_id))
                        self.conn.execute(
                            "INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), customer_id, order_id, "DEBIT", final_total, pay_key)
                        )
                    
                    self.conn.execute("UPDATE orders SET status = 'PAID' WHERE order_id = ?", (order_id,))
                    self._log_audit(order_id, "PAYMENT_SUCCESS", "RESERVED", "PAID")
                    return self.get_order(order_id)
                else:
                    # Compensating Rollback
                    for sku, qty in aggregated_items.items():
                        self.conn.execute(
                            "UPDATE products SET available_stock = available_stock + ?, reserved_stock = reserved_stock - ? WHERE sku = ?",
                            (qty, qty, sku)
                        )
                    if coupon_code:
                        self.conn.execute("UPDATE coupons SET current_uses = current_uses - 1 WHERE code = ?", (coupon_code,))
                    
                    self.conn.execute("UPDATE orders SET status = 'FAILED_PAYMENT' WHERE order_id = ?", (order_id,))
                    self._log_audit(order_id, "PAYMENT_FAILED", "RESERVED", "FAILED_PAYMENT")
                    return self.get_order(order_id)
        except Exception as e:
            # In a real system, we'd handle DB errors more carefully
            raise e

    def ship_order(self, order_id: str):
        order = self.get_order(order_id)
        if order['status'] != 'PAID':
            raise ValueError(f"Order cannot be shipped from status {order['status']}")
        
        items = self.conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        with self.conn:
            for item in items:
                self.conn.execute(
                    "UPDATE products SET reserved_stock = reserved_stock - ? WHERE sku = ?",
                    (item['quantity'], item['sku'])
                )
            self.conn.execute("UPDATE orders SET status = 'SHIPPED' WHERE order_id = ?", (order_id,))
            self._log_audit(order_id, "SHIPMENT_COMPLETED", "PAID", "SHIPPED")

    def cancel_order(self, order_id: str):
        order = self.get_order(order_id)
        if order['status'] not in ('RESERVED', 'PAID'):
            raise ValueError(f"Order cannot be cancelled from status {order['status']}")
        
        items = self.conn.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,)).fetchall()
        with self.conn:
            for item in items:
                self.conn.execute(
                    "UPDATE products SET available_stock = available_stock + ?, reserved_stock = reserved_stock - ? WHERE sku = ?",
                    (item['quantity'], item['quantity'], item['sku'])
                )
            if order['coupon_code']:
                self.conn.execute("UPDATE coupons SET current_uses = current_uses - 1 WHERE code = ?", (order['coupon_code'],))
            
            if order['status'] == 'PAID':
                refund_key = f"refund_{order_id}"
                self.conn.execute("UPDATE wallets SET balance_cents = balance_cents + ? WHERE customer_id = ?", (order['final_total_cents'], order['customer_id']))
                self.conn.execute(
                    "INSERT INTO ledger_entries VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), order['customer_id'], order_id, "CREDIT", order['final_total_cents'], refund_key)
                )
            
            self.conn.execute("UPDATE orders SET status = 'CANCELLED' WHERE order_id = ?", (order_id,))
            self._log_audit(order_id, "ORDER_CANCELLED", order['status'], "CANCELLED")

    def get_order(self, order_id: str):
        row = self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
        if not row:
            raise KeyError("Order not found")
        return dict(row)

    def _log_audit(self, order_id: str, event_type: str, from_state: Optional[str], to_state: Optional[str]):
        self.conn.execute(
            "INSERT INTO audit_logs (order_id, event_type, from_state, to_state, timestamp) VALUES (?, ?, ?, ?, ?)",
            (order_id, event_type, from_state, to_state, datetime.now().isoformat())
        )

    def get_order_audit_log(self, order_id: str):
        rows = self.conn.execute("SELECT * FROM audit_logs WHERE order_id = ? ORDER BY log_id", (order_id,)).fetchall()
        return [dict(row) for row in rows]

    def get_system_reconciliation(self):
        debits = self.conn.execute("SELECT SUM(amount_cents) as total FROM ledger_entries WHERE entry_type = 'DEBIT' AND order_id IS NOT NULL").fetchone()['total'] or 0
        credits = self.conn.execute("SELECT SUM(amount_cents) as total FROM ledger_entries WHERE entry_type = 'CREDIT' AND order_id IS NOT NULL").fetchone()['total'] or 0
        
        net_captured = debits - credits
        
        active_orders_total = self.conn.execute(
            "SELECT SUM(final_total_cents) as total FROM orders WHERE status IN ('PAID', 'SHIPPED')"
        ).fetchone()['total'] or 0
        
        status_counts = self.conn.execute("SELECT status, COUNT(*) as count FROM orders GROUP BY status").fetchall()
        orders_by_status = {row['status']: row['count'] for row in status_counts}
        
        return {
            "total_order_debits_cents": debits,
            "total_order_refunds_cents": credits,
            "net_captured_cents": net_captured,
            "active_orders_total_cents": active_orders_total,
            "is_balanced": net_captured == active_orders_total,
            "orders_by_status": orders_by_status
        }
