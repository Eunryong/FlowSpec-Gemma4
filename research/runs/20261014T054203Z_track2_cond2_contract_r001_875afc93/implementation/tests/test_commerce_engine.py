import pytest
from commerce_engine import CommerceEngine

@pytest.fixture
def engine():
    return CommerceEngine(":memory:")

def test_product_inventory_lifecycle(engine):
    engine.register_product("SKU1", "Product 1", 1000, 10)
    prod = engine.get_product("SKU1")
    assert prod['available_stock'] == 10
    assert prod['reserved_stock'] == 0

    engine.create_wallet("C1", 2000)
    order = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 2}])
    
    prod = engine.get_product("SKU1")
    assert prod['available_stock'] == 8
    assert prod['reserved_stock'] == 2
    
    engine.ship_order(order['order_id'])
    prod = engine.get_product("SKU1")
    assert prod['available_stock'] == 8
    assert prod['reserved_stock'] == 0

def test_wallet_idempotency(engine):
    engine.create_wallet("C1", 0)
    engine.deposit_funds("C1", 1000, "key1")
    assert engine.get_wallet_balance("C1") == 1000
    
    # Duplicate idempotency key
    engine.deposit_funds("C1", 1000, "key1")
    assert engine.get_wallet_balance("C1") == 1000

def test_coupon_validation_and_math(engine):
    engine.register_product("SKU1", "P1", 1000, 10)
    engine.create_wallet("C1", 5000)
    engine.create_coupon("SAVE10", 10, 5, 1000) # 10% off, min 1000
    
    # Valid coupon
    order = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 2}], coupon_code="SAVE10")
    assert order['subtotal_cents'] == 2000
    assert order['discount_cents'] == 200
    assert order['final_total_cents'] == 1800
    
    # Test min_order_cents
    engine.register_product("SKU2", "P2", 100, 10)
    with pytest.raises(ValueError, match="minimum order amount"):
        engine.checkout_order("C1", [{"sku": "SKU2", "quantity": 1}], coupon_code="SAVE10")

def test_compensating_saga_insufficient_funds(engine):
    engine.register_product("SKU1", "P1", 1000, 10)
    engine.create_wallet("C1", 500) # Not enough for 1000
    engine.create_coupon("SAVE10", 10, 5, 0)
    
    order = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="SAVE10")
    
    assert order['status'] == "FAILED_PAYMENT"
    prod = engine.get_product("SKU1")
    assert prod['available_stock'] == 10
    assert prod['reserved_stock'] == 0
    
    # Check coupon quota restored
    # We can't check current_uses directly via public API easily, 
    # but we can try to use it again.
    # If it wasn't restored, and max_uses was 1, it would fail.
    # Let's create a coupon with max_uses=1.
    engine.create_coupon("ONCE", 10, 1, 0)
    engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="ONCE")
    # Should be restored now.
    order2 = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="ONCE")
    # If it failed payment again, it's still restored.
    # To verify it's usable, we need a wallet with money.
    engine.deposit_funds("C1", 2000, "dep1")
    order3 = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="ONCE")
    assert order3['status'] == "PAID"

def test_paid_order_cancellation(engine):
    engine.register_product("SKU1", "P1", 1000, 10)
    engine.create_wallet("C1", 2000)
    engine.create_coupon("SAVE10", 10, 5, 0)
    
    order = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}], coupon_code="SAVE10")
    assert order['status'] == "PAID"
    assert engine.get_wallet_balance("C1") == 1000 - 100 # 900
    
    engine.cancel_order(order['order_id'])
    assert engine.get_wallet_balance("C1") == 1800 # 900 + 900
    prod = engine.get_product("SKU1")
    assert prod['available_stock'] == 10
    assert prod['reserved_stock'] == 0

def test_state_machine_guards(engine):
    engine.register_product("SKU1", "P1", 1000, 10)
    engine.create_wallet("C1", 2000)
    order = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    
    # Ship it
    engine.ship_order(order['order_id'])
    
    # Cannot cancel shipped order
    with pytest.raises(ValueError, match="cannot cancel"):
        engine.cancel_order(order['order_id'])
        
    # Cannot ship again
    with pytest.raises(ValueError, match="already SHIPPED"):
        engine.ship_order(order['order_id'])

def test_audit_trail(engine):
    engine.register_product("SKU1", "P1", 1000, 10)
    engine.create_wallet("C1", 2000)
    order = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    engine.ship_order(order['order_id'])
    
    logs = engine.get_order_audit_log(order['order_id'])
    assert len(logs) >= 2
    assert logs[0]['to_state'] == "PAID"
    assert logs[-1]['to_state'] == "SHIPPED"

def test_global_reconciliation(engine):
    engine.register_product("SKU1", "P1", 1000, 10)
    engine.create_wallet("C1", 10000)
    
    # 1. Successful and Shipped
    o1 = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    engine.ship_order(o1['order_id'])
    
    # 2. Paid and Cancelled
    o2 = engine.checkout_order("C1", [{"sku": "SKU1", "quantity": 1}])
    engine.cancel_order(o2['order_id'])
    
    # 3. Failed Payment
    engine.create_wallet("C2", 0)
    o3 = engine.checkout_order("C2", [{"sku": "SKU1", "quantity": 1}])
    
    recon = engine.get_system_reconciliation()
    assert recon['is_balanced'] is True
    assert recon['orders_by_status']['SHIPPED'] == 1
    assert recon['orders_by_status']['CANCELLED'] == 1
    assert recon['orders_by_status']['FAILED_PAYMENT'] == 1
