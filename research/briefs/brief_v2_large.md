# Multi-Module E-Commerce Order Saga, Inventory Reservation & Payment Ledger Engine (V2 Large Brief)

## 1. Overview
Build a standalone Python package/module and SQLite-backed transactional commerce engine (`CommerceEngine`) that coordinates four coupled domain subsystems:
1. **Warehouse Inventory & Stock Reservation Subsystem** (`available_stock` vs `reserved_stock` lifecycle)
2. **Customer Wallet & Idempotent Double-Entry Ledger Subsystem** (`DEBIT` / `CREDIT` ledger with idempotency keys)
3. **Promotional Coupon & Quota Management Subsystem** (percentage discounts, minimum spend thresholds, and usage quota tracking/restoration)
4. **Order Fulfillment Saga, State Machine & Audit Trail Subsystem** (multi-item order checkout, automatic compensating rollback on payment failure, order cancellation with refund + stock/coupon restoration, shipment fulfillment, and global accounting reconciliation)

All logic must be self-contained within this workspace using Python's standard library (`sqlite3`, `uuid`, `dataclasses`, `datetime`, etc.) and verified with an automated `pytest` suite in `tests/`.

---

## 2. Core Functional & Architectural Requirements

### 2.1 Subsystem A: Warehouse Inventory & Two-Phase Stock Lifecycle
- **Register Product (`register_product`)**:
  - Inputs: `sku: str`, `name: str`, `price_cents: int`, `initial_stock: int`.
  - Validation: `price_cents > 0` and `initial_stock >= 0` (raise `ValueError` otherwise; duplicate `sku` must also raise `ValueError`).
  - Initializes `available_stock = initial_stock` and `reserved_stock = 0`.
- **Get Product (`get_product`)**:
  - Input: `sku: str`.
  - Returns product details including `sku`, `name`, `price_cents`, `available_stock`, and `reserved_stock` (raises `ValueError` or `KeyError` if not found).
- **Two-Phase Stock Invariants**:
  - **Reservation (Order Created/Reserved)**: Decrements `available_stock` by `quantity` and increments `reserved_stock` by `quantity`. If `available_stock < quantity` for any item in an order, no stock may be deducted for any item in that order, and `ValueError` must be raised.
  - **Release (Payment Failed or Order Cancelled before shipment)**: Decrements `reserved_stock` by `quantity` and increments `available_stock` by `quantity`.
  - **Commit (Order Shipped)**: Decrements `reserved_stock` by `quantity` (`available_stock` remains unchanged, as goods have left the warehouse).
  - At all times, `available_stock >= 0` and `reserved_stock >= 0`.

### 2.2 Subsystem B: Customer Wallet & Idempotent Payment Ledger
- **Create / Top-up Customer Wallet (`create_wallet`, `deposit_funds`)**:
  - `create_wallet(customer_id: str, initial_balance_cents: int = 0)`: Initializes a customer wallet (`initial_balance_cents >= 0`, raises `ValueError` if negative or duplicate `customer_id`). If `initial_balance_cents > 0`, records an initial `"CREDIT"` ledger entry.
  - `deposit_funds(customer_id: str, amount_cents: int, idempotency_key: str)`: Adds `amount_cents > 0` to the customer wallet and records a `"CREDIT"` ledger entry.
  - `get_wallet_balance(customer_id: str) -> int`: Returns current balance in cents.
- **Append-Only Ledger & Idempotency**:
  - Every balance change (`DEBIT` for order payment, `CREDIT` for deposit or order refund) must be recorded in a `ledger_entries` table with:
    `entry_id`, `customer_id`, `order_id` (nullable for deposits), `entry_type` (`"DEBIT"` or `"CREDIT"`), `amount_cents`, and `idempotency_key` (unique).
  - **Idempotency Requirement**: If `deposit_funds` or an order payment/refund operation is invoked with an `idempotency_key` that already exists in `ledger_entries`, it must NOT mutate the wallet balance a second time; it must safely return the existing result.
  - **Non-Negative Balance Invariant**: A wallet's `balance_cents` must never drop below `0`.

### 2.3 Subsystem C: Promotional Coupons & Quota Compensation
- **Create Coupon (`create_coupon`)**:
  - Inputs: `code: str`, `discount_percent: int`, `max_uses: int`, `min_order_cents: int = 0`.
  - Validation: `1 <= discount_percent <= 90`, `max_uses >= 1`, `min_order_cents >= 0`.
  - Tracks `current_uses` (initialized to `0`).
- **Discount Calculation & Quota Lifecycle**:
  - Given `subtotal_cents = sum(item_price_cents * quantity)`:
  - If `coupon_code` is provided on an order:
    - Verify the coupon exists, `current_uses < max_uses`, and `subtotal_cents >= min_order_cents` (raise `ValueError` if invalid, exhausted, or below minimum subtotal).
    - Compute integer floor discount: `discount_cents = (subtotal_cents * discount_percent) // 100`.
    - Compute `final_total_cents = subtotal_cents - discount_cents`.
    - Increment `current_uses` by `1` when reserved.
    - **Quota Compensation**: If the order subsequently fails payment or is cancelled (`CANCELLED`), `current_uses` MUST be decremented by `1` so the coupon quota is restored for future orders.

### 2.4 Subsystem D: Order Checkout Saga, State Machine & Audit Log
- **Place & Process Order (`checkout_order`)**:
  - Inputs: `customer_id: str`, `items: list[dict]` (each dict containing `{"sku": str, "quantity": int}`), `coupon_code: str | None = None`, `idempotency_key: str | None = None`.
  - Validation: `items` must be non-empty and all quantities `> 0`.
  - **Saga Execution Steps**:
    1. Validate customer exists, all SKUs exist, and sufficient `available_stock` exists for all requested items (handling duplicate SKUs in `items` or aggregating quantities accurately).
    2. Validate and apply `coupon_code` (if provided) to compute `subtotal_cents`, `discount_cents`, and `final_total_cents`.
    3. Reserve stock (`available_stock -= qty`, `reserved_stock += qty`) and increment coupon `current_uses` (status: `"RESERVED"`).
    4. Attempt wallet payment (`DEBIT` of `final_total_cents` from customer's wallet):
       - **If wallet balance is sufficient (`balance_cents >= final_total_cents`)**:
         - Deduct `final_total_cents` from wallet, insert `"DEBIT"` ledger entry, transition order status to `"PAID"`, and record audit log entry.
       - **If wallet balance is insufficient (`balance_cents < final_total_cents`)**:
         - **Compensating Rollback**: Automatically release all reserved stock back to `available_stock` (`reserved_stock -= qty`, `available_stock += qty`), decrement coupon `current_uses` (if a coupon was used), transition the order status to `"FAILED_PAYMENT"`, record the `"FAILED_PAYMENT"` transition in `audit_logs`, and return the order record (with `status == "FAILED_PAYMENT"`).
- **Ship Order (`ship_order`)**:
  - Input: `order_id: str`.
  - Behavior:
    - Allowed **only** when order status is `"PAID"` (raise `ValueError` for `"RESERVED"`, `"FAILED_PAYMENT"`, `"CANCELLED"`, or already `"SHIPPED"` orders).
    - Commits reserved inventory for all order items (`reserved_stock -= qty`).
    - Transitions order status to `"SHIPPED"` and appends an audit log entry.
- **Cancel Order (`cancel_order`)**:
  - Input: `order_id: str`.
  - Behavior:
    - Allowed **only** when order status is `"PAID"` or `"RESERVED"` (raise `ValueError` if already `"SHIPPED"`, `"CANCELLED"`, or `"FAILED_PAYMENT"`).
    - Releases reserved inventory back to available stock (`reserved_stock -= qty`, `available_stock += qty`).
    - If a coupon was applied to the order, decrements its `current_uses` by `1`.
    - If order was `"PAID"`, credits `final_total_cents` back to the customer's wallet and records a `"CREDIT"` refund entry in `ledger_entries`.
    - Transitions order status to `"CANCELLED"` and appends an audit log entry.
- **Audit Log (`get_order_audit_log`)**:
  - Input: `order_id: str`.
  - Returns chronological list of audit events (`order_id`, `event_type`, `from_state`, `to_state`, `timestamp` / `id`) for that order.
- **System Reconciliation (`get_system_reconciliation`)**:
  - Returns a dictionary summarizing system-wide accounting integrity:
    - `total_order_debits_cents`: sum of `"DEBIT"` ledger entries linked to orders.
    - `total_order_refunds_cents`: sum of `"CREDIT"` ledger entries linked to order refunds.
    - `net_captured_cents`: `total_order_debits_cents - total_order_refunds_cents`.
    - `active_orders_total_cents`: sum of `final_total_cents` for all orders currently in `"PAID"` or `"SHIPPED"` status.
    - `is_balanced`: boolean (`net_captured_cents == active_orders_total_cents`).
    - `orders_by_status`: dict mapping status strings to counts.

---

## 3. Storage & Persistence Requirements
- Implement SQLite persistence using Python's `sqlite3` module.
- `CommerceEngine(db_path: str = ":memory:")` must maintain a persistent connection when `:memory:` is used so all tables persist across calls within the instance lifecycle.
- Tables must be initialized automatically on instantiation.

## 4. Test Suite Requirements (`tests/`)
Write a comprehensive `pytest` test suite (e.g., `tests/test_commerce_engine.py`) verifying at least the following 8 scenarios:
1. **Product & Inventory Lifecycle**: Product registration, stock reservation during checkout (`available_stock` vs `reserved_stock`), and stock commitment on `ship_order`.
2. **Wallet & Idempotency**: Wallet creation, `deposit_funds` idempotency with duplicate `idempotency_key`, and ledger entry verification.
3. **Coupon Validation & Discount Math**: Applying valid percentage coupons, enforcing `min_order_cents` and `max_uses` limits.
4. **Compensating Saga on Insufficient Funds**: When `checkout_order` fails payment due to low wallet balance, order transitions to `"FAILED_PAYMENT"`, all reserved stock is restored to `available_stock` (`reserved_stock == 0`), coupon `current_uses` is restored, and wallet balance is unchanged.
5. **Paid Order Cancellation & Full Compensation**: Cancelling a `"PAID"` order refunds the exact `final_total_cents` via a `"CREDIT"` ledger entry, restores `available_stock`, decrements coupon `current_uses`, and transitions to `"CANCELLED"`.
6. **Strict State Machine Guards**: Attempting to cancel a `"SHIPPED"`, `"CANCELLED"`, or `"FAILED_PAYMENT"` order raises `ValueError`; attempting to ship a non-`"PAID"` order raises `ValueError`.
7. **Audit Trail Completeness**: `get_order_audit_log(order_id)` accurately reflects the chronological state transitions of both successful and compensated orders.
8. **Global Accounting Reconciliation**: After a mix of successful, shipped, failed-payment, and cancelled orders, `get_system_reconciliation()` reports `is_balanced == True` and `net_captured_cents == active_orders_total_cents`.
