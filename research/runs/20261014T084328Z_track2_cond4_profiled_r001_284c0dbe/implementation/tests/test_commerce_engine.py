import pytest
from commerce_engine import CommerceEngine

def test_product_inventory_lifecycle():
    ce = CommerceEngine()
    ce.register_product("SKU1", "Product 1", 1000, 10)
    
    # Checkout to reserve
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 2}], idempotency_key="id1")
    # Need wallet for checkout to succeed or fail payment
    # Since we didn't create wallet, it should fail payment or raise error.
    # Let's setup wallet first.
    ce.create_wallet("C1", 5000)
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 2}], idempotency_key="id2")
    
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

def test_coupon_validation():
    ce = CommerceEngine()
    ce.create_coupon("SAVE10", 10, 1, 500)
    ce.create_wallet("C1", 10000)
    ce.register_product("SKU1", "P1", 1000, 10)
    
    # Below min spend
    with pytest.raises(ValueError):
        ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 0}], coupon_code="SAVE10") # quantity 0 handled by validation
    
    # Valid
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="SAVE10")
    assert order['discount_cents'] == 100
    
    # Max uses
    with pytest.raises(ValueError):
        ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="SAVE10")

def test_compensating_saga_insufficient_funds():
    ce = CommerceEngine()
    ce.create_wallet("C1", 100) # Not enough for 1000
    ce.register_product("SKU1", "P1", 1000, 10)
    ce.create_coupon("SAVE10", 10, 10, 0)
    
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="SAVE10")
    assert order['status'] == "FAILED_PAYMENT"
    
    p = ce.get_product("SKU1")
    assert p['available_stock'] == 10
    assert p['reserved_stock'] == 0
    
    # Coupon usage restored (should be 0)
    # We need a way to check coupon usage or just try to use it again
    # If it was 1 and not restored, and max_uses was 1, it would fail.
    # Here max_uses is 10, but we can check if it's 0 by creating a 1-use coupon.
    ce.create_coupon("ONE", 10, 1, 0)
    ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="ONE")
    # Should be able to use it again because first one failed payment
    order2 = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="ONE")
    assert order2['status'] == "FAILED_PAYMENT"

def test_paid_order_cancellation():
    ce = CommerceEngine()
    ce.create_wallet("C1", 5000)
    ce.register_product("SKU1", "P1", 1000, 10)
    ce.create_coupon("SAVE10", 10, 10, 0)
    
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="SAVE10")
    assert order['status'] == "PAID"
    
    ce.cancel_order(order['order_id'])
    assert ce.get_wallet_balance("C1") == 5000 - 900 + 900
    p = ce.get_product("SKU1")
    assert p['available_stock'] == 10

def test_state_machine_guards():
    ce = CommerceEngine()
    ce.create_wallet("C1", 5000)
    ce.register_product("SKU1", "P1", 1000, 10)
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    
    ce.ship_order(order['order_id'])
    with pytest.raises(ValueError):
        ce.cancel_order(order['order_id'])

def test_audit_trail():
    ce = CommerceEngine()
    ce.create_wallet("C1", 5000)
    ce.register_product("SKU1", "P1", 1000, 10)
    order = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    ce.ship_order(order['order_id'])
    
    logs = ce.get_order_audit_log(order['order_id'])
    assert len(logs) >= 2
    assert logs[0]['to_state'] == "PAID"
    assert logs[-1]['to_state'] == "SHIPPED"

def test_global_reconciliation():
    ce = CommerceEngine()
    ce.create_wallet("C1", 10000)
    ce.register_product("SKU1", "P1", 1000, 10)
    
    # 1. Paid and Shipped
    o1 = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    ce.ship_order(o1['order_id'])
    
    # 2. Paid and Cancelled
    o2 = ce.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    ce.cancel_order(o2['order_id'])
    
    # 3. Failed Payment
    ce.create_wallet("C2", 0)
    o3 = ce.checkout_order("C2", [{"sku": "SKU1", "quantity": 1}])
    
    recon = ce.get_system_reconciliation()
    assert recon['is_balanced'] is True
    assert recon['net_captured_cents'] == 1000
    assert recon['active_orders_total_cents'] == 1000
