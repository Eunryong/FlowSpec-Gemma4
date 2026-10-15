import pytest
from commerce_engine import CommerceEngine

def test_product_inventory_lifecycle():
    ce = CommerceEngine()
    ce.register_product("SKU1", "Item 1", 1000, 10)
    
    # Checkout to reserve
    ce.create_wallet("C1", 2000)
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 2}])
    
    p = ce.get_product("SKU1")
    assert p['available_stock'] == 8
    assert p['reserved_stock'] == 2
    
    ce.ship_order(order['order_id'])
    p = ce.get_product("SKU1")
    assert p['available_stock'] == 8
    assert p['reserved_stock'] == 0

def test_wallet_idempotency():
    ce = CommerceEngine()
    ce.create_wallet("C1", 0)
    ce.deposit_funds("C1", 1000, "key1")
    ce.deposit_funds("C1", 1000, "key1")
    assert ce.get_wallet_balance("C1") == 1000

def test_coupon_logic():
    ce = CommerceEngine()
    ce.create_coupon("SAVE10", 10, 1, 500)
    ce.create_wallet("C1", 1000)
    ce.register_product("SKU1", "Item 1", 1000, 10)
    
    # Valid coupon
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], "SAVE10")
    assert order['discount_cents'] == 100
    assert order['final_total_cents'] == 900
    
    # Coupon exhausted
    ce.create_wallet("C2", 1000)
    with pytest.raises(ValueError):
        ce.checkout_order("C2", [{"sku": "SKU1", "quantity": 1}], "SAVE10")

def test_payment_failure_rollback():
    ce = CommerceEngine()
    ce.register_product("SKU1", "Item 1", 1000, 10)
    ce.create_wallet("C1", 500) # Not enough for 1000
    ce.create_coupon("SAVE10", 10, 5, 0)
    
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], "SAVE10")
    assert order['status'] == "FAILED_PAYMENT"
    
    p = ce.get_product("SKU1")
    assert p['available_stock'] == 10
    assert p['reserved_stock'] == 0
    
    # Check coupon restored (current_uses should be 0)
    cursor = ce.conn.execute("SELECT current_uses FROM coupons WHERE code='SAVE10'")
    assert cursor.fetchone()[0] == 0

def test_paid_order_cancellation():
    ce = CommerceEngine()
    ce.register_product("SKU1", "Item 1", 1000, 10)
    ce.create_wallet("C1", 2000)
    ce.create_coupon("SAVE10", 10, 5, 0)
    
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], "SAVE10")
    order_id = order['order_id']
    
    ce.cancel_order(order_id)
    
    assert ce.get_wallet_balance("C1") == 2000 # Refunded
    p = ce.get_product("SKU1")
    assert p['available_stock'] == 10
    
    cursor = ce.conn.execute("SELECT current_uses FROM coupons WHERE code='SAVE10'")
    assert cursor.fetchone()[0] == 0

def test_state_machine_guards():
    ce = CommerceEngine()
    ce.register_product("SKU1", "Item 1", 1000, 10)
    ce.create_wallet("C1", 2000)
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    order_id = order['order_id']
    
    ce.ship_order(order_id)
    with pytest.raises(ValueError):
        ce.cancel_order(order_id)

def test_audit_trail():
    ce = CommerceEngine()
    ce.register_product("SKU1", "Item 1", 1000, 10)
    ce.create_wallet("C1", 2000)
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    order_id = order['order_id']
    ce.ship_order(order_id)
    
    logs = ce.get_order_audit_log(order_id)
    assert len(logs) >= 2
    assert logs[0]['to_state'] == "PAID"
    assert logs[-1]['to_state'] == "SHIPPED"

def test_global_reconciliation():
    ce = CommerceEngine()
    ce.register_product("SKU1", "Item 1", 1000, 100)
    ce.create_wallet("C1", 10000)
    ce.create_wallet("C2", 10000)
    
    # 1. Successful & Shipped
    o1 = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    ce.ship_order(o1['order_id'])
    
    # 2. Paid but Cancelled
    o2 = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    ce.cancel_order(o2['order_id'])
    
    # 3. Failed Payment
    ce.create_wallet("C3", 0)
    ce.checkout_order("C3", [{"sku": "SKU1", "quantity": 1}])
    
    recon = ce.get_system_reconciliation()
    assert recon['is_balanced'] is True
    assert recon['net_captured_cents'] == 1000
    assert recon['active_orders_total_cents'] == 1000
