from extensions import db
from models import Product, InventoryLog

def check_and_deduct_stock(product_id, quantity, reason='Order', admin_id=None):
    """Safely verifies and deducts stock under a database transaction with logs."""
    try:
        # Fetch product with locking to prevent race conditions (select for update)
        product = db.session.query(Product).filter_by(id=product_id).with_for_update().first()
        
        if not product:
            return False, "Product not found."
            
        if not product.is_active:
            return False, "Product is currently inactive."
            
        if product.stock_count < quantity:
            return False, f"Insufficient stock. Available: {product.stock_count} units."
            
        prev_stock = product.stock_count
        product.stock_count -= quantity
        
        # Log inventory transaction
        log = InventoryLog(
            product_id=product_id,
            change_qty=-quantity,
            previous_stock=prev_stock,
            new_stock=product.stock_count,
            reason=reason,
            admin_id=admin_id
        )
        db.session.add(log)
        
        return True, "Stock deducted successfully."
    except Exception as e:
        db.session.rollback()
        return False, f"Database transaction failed: {e}"

def restock_product(product_id, quantity, reason='Manual Adjustment', admin_id=None):
    """Safely increments stock level under transactional checks."""
    try:
        product = db.session.query(Product).filter_by(id=product_id).with_for_update().first()
        
        if not product:
            return False, "Product not found."
            
        prev_stock = product.stock_count
        product.stock_count += quantity
        
        # Log inventory transaction
        log = InventoryLog(
            product_id=product_id,
            change_qty=quantity,
            previous_stock=prev_stock,
            new_stock=product.stock_count,
            reason=reason,
            admin_id=admin_id
        )
        db.session.add(log)
        
        return True, "Stock restocked successfully."
    except Exception as e:
        db.session.rollback()
        return False, f"Database transaction failed: {e}"
