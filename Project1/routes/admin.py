import os
import csv
import io
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, send_file, make_response, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, limiter
from models import Admin, AuditLog, Product, Category, Order, OrderItem, Review, Coupon, Notification, User, Offer, Banner, DeliverySetting, DeliveryPartner, SystemSetting, InventoryLog, OrderTimeline
from utils.decorators import admin_required, check_permission
from utils.helpers import save_and_optimize_image

# Create Blueprint
admin_bp = Blueprint('admin', __name__)

# Log audit logs helper
def log_audit(action):
    try:
        log = AuditLog(
            admin_id=session.get('admin_user_id'),
            action=action,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string[:255]
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print("Audit logging failed:", e)

# --- Gateway Auth ---

@admin_bp.route('/admin/login', methods=['GET', 'POST'])
def legacy_admin_login_redirect():
    return redirect(url_for('admin.admin_login'), code=307)

@admin_bp.route('/admin-gate', methods=['GET', 'POST'], endpoint='admin_login')
@limiter.limit("10 per minute")
def admin_login_gate():
    if session.get('is_admin', False):
        return redirect(url_for('admin.admin_dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('admin_id')
        password = request.form.get('admin_password')
        remember = request.form.get('remember') == 'true'
        
        admin = Admin.query.filter_by(username=username).first()
        
        if admin:
            # Check lockout status
            if admin.locked_until and admin.locked_until > datetime.utcnow():
                diff = admin.locked_until - datetime.utcnow()
                flash(f'Account locked due to failed logins. Try again in {int(diff.seconds / 60) + 1} minutes.', 'danger')
                return render_template('admin_login.html')
                
            if check_password_hash(admin.password_hash, password):
                # Reset failed attempts
                admin.failed_login_attempts = 0
                admin.locked_until = None
                db.session.commit()
                
                session['is_admin'] = True
                session['admin_user_id'] = admin.id
                session['admin_role'] = admin.role
                session['admin_name'] = admin.name
                
                if remember:
                    session.permanent = True
                    current_app.permanent_session_lifetime = timedelta(days=7)
                
                # Clear standard user session
                session.pop('user_id', None)
                
                log_audit("Logged in successfully")
                flash(f'Welcome back, {admin.name} ({admin.role})!', 'success')
                return redirect(url_for('admin.admin_dashboard'))
            else:
                # Increment failed count
                admin.failed_login_attempts += 1
                if admin.failed_login_attempts >= 5:
                    admin.locked_until = datetime.utcnow() + timedelta(minutes=10)
                    flash('Account locked for 10 minutes due to 5 failed login attempts.', 'danger')
                else:
                    flash(f'Invalid credentials. {5 - admin.failed_login_attempts} attempts remaining.', 'danger')
                db.session.commit()
                
                # Log failed attempt anonymously (no admin_id set)
                try:
                    log = AuditLog(
                        action=f"Failed login attempt for username: {username}",
                        ip_address=request.remote_addr,
                        user_agent=request.user_agent.string[:255]
                    )
                    db.session.add(log)
                    db.session.commit()
                except:
                    pass
        else:
            flash('Invalid Admin Credentials.', 'danger')
            
    return render_template('admin_login.html')

@admin_bp.route('/admin/logout')
def admin_logout():
    if session.get('is_admin'):
        log_audit("Logged out")
    session.clear()
    flash('Logged out from admin panel.', 'info')
    return redirect(url_for('admin.admin_login'))

# --- Dashboard ---

@admin_bp.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    # Calculate revenue figures
    total_rev = db.session.query(db.func.sum(Order.total_amount)).scalar() or 0.0
    paid_rev = db.session.query(db.func.sum(Order.total_amount)).filter_by(payment_status='Paid').scalar() or 0.0
    
    # Orders counters
    total_orders = Order.query.count()
    pending_orders = Order.query.filter(Order.order_status.in_(['Placed', 'Packed', 'Out for Delivery'])).count()
    delivered_orders = Order.query.filter_by(order_status='Delivered').count()
    cancelled_orders = Order.query.filter_by(order_status='Cancelled').count()
    
    # Customers
    total_cust = User.query.count()
    active_cust = User.query.filter_by(is_blocked=False).count()
    
    # Products
    total_prod = Product.query.count()
    categories_count = Category.query.count()
    out_of_stock = Product.query.filter(Product.stock_count <= 0).count()
    
    # Compute low stock using safety limit min_stock field
    low_stock = db.session.query(Product).filter(Product.stock_count <= Product.min_stock).count()
    
    coupons_count = Coupon.query.count()
    
    # Recent items
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    
    return render_template(
        'admin_dashboard.html',
        total_revenue=total_rev,
        paid_revenue=paid_rev,
        orders_count=total_orders,
        pending_orders_count=pending_orders,
        delivered_orders=delivered_orders,
        cancelled_orders=cancelled_orders,
        total_customers=total_cust,
        active_customers=active_cust,
        total_products=total_prod,
        categories_count=categories_count,
        out_of_stock=out_of_stock,
        low_stock=low_stock,
        coupons_count=coupons_count,
        recent_orders=recent_orders
    )

# --- Product Management ---

@admin_bp.route('/admin/products', methods=['GET'])
@admin_required
def admin_products():
    # Search and filters
    search_q = request.args.get('q', '').strip()
    cat_id = request.args.get('category_id')
    stock_filter = request.args.get('stock')
    
    query = Product.query
    
    if search_q:
        query = query.filter(Product.name.like(f"%{search_q}%"))
    if cat_id:
        query = query.filter_by(category_id=int(cat_id))
    if stock_filter == 'out':
        query = query.filter(Product.stock_count <= 0)
    elif stock_filter == 'low':
        query = query.filter(Product.stock_count <= Product.min_stock)
        
    products = query.order_by(Product.name).all()
    categories = Category.query.all()
    
    return render_template('admin_products.html', products=products, categories=categories, search_q=search_q, cat_id=cat_id, stock_filter=stock_filter)

@admin_bp.route('/admin/products/add', methods=['POST'])
@admin_required
@check_permission(['Super Admin', 'Manager', 'Inventory Manager'])
def admin_product_add():
    name = request.form.get('name')
    category_id = request.form.get('category_id')
    description = request.form.get('description')
    price = request.form.get('price')
    mrp = request.form.get('mrp')
    unit = request.form.get('unit')
    stock_count = request.form.get('stock_count')
    
    image_url = request.form.get('image_url')
    image_file = request.files.get('image_file')
    if image_file and image_file.filename != '':
        uploaded_path = save_and_optimize_image(image_file, os.path.join(current_app.root_path, 'static', 'uploads'))
        if uploaded_path:
            image_url = uploaded_path
    
    # Extra columns
    subcategory = request.form.get('subcategory')
    brand = request.form.get('brand')
    sku = request.form.get('sku')
    barcode = request.form.get('barcode')
    weight = request.form.get('weight')
    min_stock = request.form.get('min_stock', 5)
    max_stock = request.form.get('max_stock', 100)
    specifications = request.form.get('specifications')
    ingredients = request.form.get('ingredients')
    
    is_featured = request.form.get('is_featured') == 'true'
    is_trending = request.form.get('is_trending') == 'true'
    is_flash_sale = request.form.get('is_flash_sale') == 'true'
    is_best_seller = request.form.get('is_best_seller') == 'true'
    is_recommended = request.form.get('is_recommended') == 'true'
    image_urls = request.form.get('image_urls')
    
    if not name or not category_id or not price or not mrp or not unit or not stock_count:
        flash('Please fill out all required fields.', 'danger')
        return redirect(url_for('admin.admin_products'))
        
    p = Product(
        name=name,
        category_id=int(category_id),
        description=description,
        price=float(price),
        mrp=float(mrp),
        unit=unit,
        stock_count=int(stock_count),
        image_url=image_url if image_url else '/static/images/placeholder.svg',
        subcategory=subcategory,
        brand=brand,
        sku=sku,
        barcode=barcode,
        weight=weight,
        min_stock=int(min_stock),
        max_stock=int(max_stock),
        specifications=specifications,
        ingredients=ingredients,
        is_featured=is_featured,
        is_trending=is_trending,
        is_flash_sale=is_flash_sale,
        is_best_seller=is_best_seller,
        is_recommended=is_recommended,
        image_urls=image_urls
    )
    
    db.session.add(p)
    db.session.flush()
    
    # Log initial inventory
    inv_log = InventoryLog(
        product_id=p.id,
        change_qty=p.stock_count,
        previous_stock=0,
        new_stock=p.stock_count,
        reason='Restock',
        admin_id=session.get('admin_user_id')
    )
    db.session.add(inv_log)
    db.session.commit()
    
    log_audit(f"Added product: {name} (ID: {p.id})")
    flash(f'Product {name} added successfully.', 'success')
    return redirect(url_for('admin.admin_products'))

@admin_bp.route('/admin/products/edit/<int:product_id>', methods=['POST'])
@admin_required
@check_permission(['Super Admin', 'Manager', 'Inventory Manager'])
def admin_product_edit(product_id):
    product = Product.query.get_or_404(product_id)
    prev_stock = product.stock_count
    
    product.name = request.form.get('name')
    product.category_id = int(request.form.get('category_id'))
    product.description = request.form.get('description')
    product.price = float(request.form.get('price'))
    product.mrp = float(request.form.get('mrp'))
    product.unit = request.form.get('unit')
    
    new_stock = int(request.form.get('stock_count'))
    product.stock_count = new_stock
    
    image_url = request.form.get('image_url')
    image_file = request.files.get('image_file')
    if image_file and image_file.filename != '':
        uploaded_path = save_and_optimize_image(image_file, os.path.join(current_app.root_path, 'static', 'uploads'))
        if uploaded_path:
            image_url = uploaded_path
    product.image_url = image_url
    product.is_active = request.form.get('is_active') == 'True'
    
    # Extra columns
    product.subcategory = request.form.get('subcategory')
    product.brand = request.form.get('brand')
    product.sku = request.form.get('sku')
    product.barcode = request.form.get('barcode')
    product.weight = request.form.get('weight')
    product.min_stock = int(request.form.get('min_stock', 5))
    product.max_stock = int(request.form.get('max_stock', 100))
    product.specifications = request.form.get('specifications')
    product.ingredients = request.form.get('ingredients')
    
    product.is_featured = request.form.get('is_featured') == 'true'
    product.is_trending = request.form.get('is_trending') == 'true'
    product.is_flash_sale = request.form.get('is_flash_sale') == 'true'
    product.is_best_seller = request.form.get('is_best_seller') == 'true'
    product.is_recommended = request.form.get('is_recommended') == 'true'
    product.image_urls = request.form.get('image_urls')
    
    # Add inventory log if stock changed
    if prev_stock != new_stock:
        inv_log = InventoryLog(
            product_id=product.id,
            change_qty=new_stock - prev_stock,
            previous_stock=prev_stock,
            new_stock=new_stock,
            reason='Manual Adjustment',
            admin_id=session.get('admin_user_id')
        )
        db.session.add(inv_log)
        
    db.session.commit()
    
    log_audit(f"Edited product: {product.name} (ID: {product.id})")
    flash(f'Product {product.name} updated successfully.', 'success')
    return redirect(url_for('admin.admin_products'))

@admin_bp.route('/admin/products/duplicate/<int:product_id>', methods=['POST'])
@admin_required
@check_permission(['Super Admin', 'Manager', 'Inventory Manager'])
def admin_product_duplicate(product_id):
    p = Product.query.get_or_404(product_id)
    
    new_p = Product(
        name=f"Copy of {p.name}",
        category_id=p.category_id,
        description=p.description,
        price=p.price,
        mrp=p.mrp,
        unit=p.unit,
        stock_count=0,
        image_url=p.image_url,
        subcategory=p.subcategory,
        brand=p.brand,
        sku=f"copy-{p.sku}" if p.sku else None,
        barcode=p.barcode,
        weight=p.weight,
        min_stock=p.min_stock,
        max_stock=p.max_stock,
        specifications=p.specifications,
        ingredients=p.ingredients,
        is_featured=p.is_featured,
        is_trending=p.is_trending,
        is_flash_sale=p.is_flash_sale,
        is_best_seller=p.is_best_seller,
        is_recommended=p.is_recommended,
        image_urls=p.image_urls
    )
    db.session.add(new_p)
    db.session.commit()
    
    log_audit(f"Duplicated product ID: {p.id} to new ID: {new_p.id}")
    flash(f"Duplicated {p.name} as copy successfully.", "success")
    return redirect(url_for('admin.admin_products'))

@admin_bp.route('/admin/products/delete/<int:product_id>', methods=['POST'])
@admin_required
@check_permission(['Super Admin', 'Manager'])
def admin_product_delete(product_id):
    product = Product.query.get_or_404(product_id)
    name = product.name
    
    db.session.delete(product)
    db.session.commit()
    
    log_audit(f"Deleted product: {name} (ID: {product_id})")
    flash('Product deleted successfully.', 'success')
    return redirect(url_for('admin.admin_products'))

@admin_bp.route('/admin/products/toggle/<int:product_id>', methods=['POST'])
@admin_required
def admin_product_toggle(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_active = not product.is_active
    db.session.commit()
    
    status_str = "visible" if product.is_active else "hidden"
    log_audit(f"Toggled product {product.name} (ID: {product_id}) visibility to {status_str}")
    return jsonify({'success': True, 'is_active': product.is_active})

# --- Category Management ---

@admin_bp.route('/admin/categories')
@admin_required
def admin_categories():
    categories = Category.query.order_by(Category.sort_order).all()
    return render_template('admin_categories.html', categories=categories)

@admin_bp.route('/admin/categories/add', methods=['POST'])
@admin_required
@check_permission(['Super Admin', 'Manager'])
def admin_category_add():
    name = request.form.get('name')
    slug = request.form.get('slug')
    
    image_url = request.form.get('image_url')
    image_file = request.files.get('image_file')
    if image_file and image_file.filename != '':
        uploaded_path = save_and_optimize_image(image_file, os.path.join(current_app.root_path, 'static', 'uploads'))
        if uploaded_path:
            image_url = uploaded_path
    sort_order = request.form.get('sort_order', 0)
    
    if not name or not slug:
        flash("Name and slug are required fields.", "danger")
        return redirect(url_for('admin.admin_categories'))
        
    cat = Category(
        name=name,
        slug=slug,
        image_url=image_url if image_url else '/static/images/placeholder.svg',
        sort_order=int(sort_order),
        is_active=True
    )
    db.session.add(cat)
    db.session.commit()
    
    log_audit(f"Created category: {name}")
    flash(f"Category {name} created successfully.", "success")
    return redirect(url_for('admin.admin_categories'))

@admin_bp.route('/admin/categories/edit/<int:category_id>', methods=['POST'])
@admin_required
@check_permission(['Super Admin', 'Manager'])
def admin_category_edit(category_id):
    cat = Category.query.get_or_404(category_id)
    
    cat.name = request.form.get('name')
    cat.slug = request.form.get('slug')
    
    image_url = request.form.get('image_url')
    image_file = request.files.get('image_file')
    if image_file and image_file.filename != '':
        uploaded_path = save_and_optimize_image(image_file, os.path.join(current_app.root_path, 'static', 'uploads'))
        if uploaded_path:
            image_url = uploaded_path
    cat.image_url = image_url
    cat.sort_order = int(request.form.get('sort_order', 0))
    cat.is_active = request.form.get('is_active') == 'True'
    
    db.session.commit()
    
    log_audit(f"Edited category: {cat.name}")
    flash("Category updated successfully.", "success")
    return redirect(url_for('admin.admin_categories'))

@admin_bp.route('/admin/categories/delete/<int:category_id>', methods=['POST'])
@admin_required
@check_permission(['Super Admin'])
def admin_category_delete(category_id):
    cat = Category.query.get_or_404(category_id)
    
    if cat.products.count() > 0:
        flash("Cannot delete category because it contains products. Reassign them first.", "danger")
        return redirect(url_for('admin.admin_categories'))
        
    name = cat.name
    db.session.delete(cat)
    db.session.commit()
    
    log_audit(f"Deleted category: {name}")
    flash("Category deleted successfully.", "success")
    return redirect(url_for('admin.admin_categories'))

# --- Inventory Logs ---

@admin_bp.route('/admin/inventory')
@admin_required
def admin_inventory():
    inventory_logs = InventoryLog.query.order_by(InventoryLog.created_at.desc()).all()
    products = Product.query.order_by(Product.name).all()
    return render_template('admin_inventory.html', logs=inventory_logs, products=products)

@admin_bp.route('/admin/inventory/adjust/<int:product_id>', methods=['POST'])
@admin_required
@check_permission(['Super Admin', 'Manager', 'Inventory Manager'])
def admin_inventory_adjust(product_id):
    p = Product.query.get_or_404(product_id)
    
    change = int(request.form.get('change_qty', 0))
    reason = request.form.get('reason', 'Manual Adjustment')
    
    prev = p.stock_count
    p.stock_count = max(0, p.stock_count + change)
    
    inv_log = InventoryLog(
        product_id=p.id,
        change_qty=change,
        previous_stock=prev,
        new_stock=p.stock_count,
        reason=reason,
        admin_id=session.get('admin_user_id')
    )
    db.session.add(inv_log)
    db.session.commit()
    
    log_audit(f"Adjusted inventory of {p.name} by {change} (Reason: {reason})")
    flash(f"Inventory of {p.name} updated.", "success")
    return redirect(url_for('admin.admin_inventory'))

# --- Order Logistics ---

@admin_bp.route('/admin/orders', methods=['GET'])
@admin_required
def admin_orders():
    status_filter = request.args.get('status')
    
    query = Order.query
    if status_filter:
        query = query.filter_by(order_status=status_filter)
        
    orders = query.order_by(Order.created_at.desc()).all()
    drivers = DeliveryPartner.query.all()  # Pass all drivers (both Active and On Trip)
    return render_template('admin_orders.html', orders=orders, drivers=drivers, current_filter=status_filter)

@admin_bp.route('/admin/orders/<int:order_id>/status', methods=['POST'])
@admin_required
def admin_order_status(order_id):
    order = Order.query.get_or_404(order_id)
    
    new_status = request.form.get('order_status')
    new_payment = request.form.get('payment_status')
    timeline_msg = request.form.get('timeline_message', '')
    driver_id = request.form.get('delivery_partner_id')
    
    # 1. Driver Assignment
    if driver_id:
        order.delivery_partner_id = int(driver_id)
        driver = DeliveryPartner.query.get(driver_id)
        if driver:
            driver.status = 'On Trip'
            
    # 2. Status Updates
    if new_status and new_status != order.order_status:
        prev_status = order.order_status
        
        # Security OTP Checks for Delivered Status transition
        if new_status == 'Delivered':
            otp_input = request.form.get('delivery_otp')
            if order.delivery_otp and otp_input != order.delivery_otp:
                flash(f"Invalid delivery verification OTP for Order #{order.id}.", "danger")
                return redirect(url_for('admin.admin_orders'))
            # Mark driver active again
            if order.driver:
                order.driver.status = 'Active'
                
        # Generate OTP when order goes Out for Delivery
        if new_status == 'Out for Delivery':
            import random
            otp = f"{random.randint(1000, 9999)}"
            order.delivery_otp = otp
            # Send simulated Twilio ready SMS
            msg_text = f"Your GramKart order #{order.id} is out for delivery. Provide OTP {otp} to the delivery agent to collect your items."
            try:
                from services.sms_service import send_sms_notification
                send_sms_notification(order.recipient_phone, msg_text)
            except Exception as e:
                current_app.logger.warning(f"Failed to send Twilio OTP SMS: {e}")
            
            # Setup dummy coordinates for simulation route pathing
            order.driver_latitude = 25.5941
            order.driver_longitude = 85.1376
            
            timeline_msg = timeline_msg if timeline_msg else f"Order is out for delivery. Security verification OTP {otp} sent."
            
        order.order_status = new_status
        
        timeline_entry = OrderTimeline(
            order_id=order.id,
            status=new_status,
            message=timeline_msg if timeline_msg else f"Order status shifted from {prev_status} to {new_status}."
        )
        db.session.add(timeline_entry)
        
        # Real-time WebSocket update to client & admin room
        try:
            from extensions import socketio
            socketio.emit('order_status_update', {'order_id': order.id, 'status': new_status}, room=f'user_{order.user_id}')
            socketio.emit('admin_order_update', {'order_id': order.id, 'status': new_status}, to='admin_room')
        except Exception as ws_ex:
            current_app.logger.warning(f"SocketIO status emission failure: {ws_ex}")
            
        if new_status == 'Delivered':
            notif = Notification(
                user_id=order.user_id,
                title="Order Delivered!",
                message=f"Your order #{order.id} has been delivered successfully by the store driver."
            )
            db.session.add(notif)
            
    if new_payment:
        order.payment_status = new_payment
        
    db.session.commit()
    
    log_audit(f"Updated status of Order #{order.id} to {new_status} (Payment: {new_payment})")
    flash(f"Order #{order.id} status updated successfully.", "success")
    return redirect(url_for('admin.admin_orders'))


@admin_bp.route('/admin/orders/<int:order_id>/refund', methods=['POST'])
@admin_required
def admin_order_refund(order_id):
    import razorpay
    order = Order.query.get_or_404(order_id)
    if order.payment_status != 'Paid' and order.payment_method != 'Razorpay':
        flash("Refunds can only be processed for paid online orders.", "danger")
        return redirect(url_for('admin.admin_orders'))
        
    try:
        key_id = current_app.config['RAZORPAY_KEY_ID']
        key_secret = current_app.config['RAZORPAY_KEY_SECRET']
        client = razorpay.Client(auth=(key_id, key_secret))
        
        refund_payload = {
            'amount': int(order.total_amount * 100),
            'speed': 'normal'
        }
        
        # Only invoke actual refund endpoint if not mock keys
        if not key_id.startswith('rzp_test_mock'):
            client.payment.refund(order.razorpay_payment_id, refund_payload)
            
        order.payment_status = 'Refunded'
        order.refund_status = 'Processed'
        order.order_status = 'Cancelled'
        
        db.session.add(OrderTimeline(
            order_id=order.id,
            status='Cancelled',
            message=f"Order cancelled and refund of INR {order.total_amount} processed successfully."
        ))
        db.session.commit()
        
        try:
            from extensions import socketio
            socketio.emit('order_status_update', {'order_id': order.id, 'status': 'Cancelled'}, room=f'user_{order.user_id}')
        except:
            pass
            
        log_audit(f"Processed refund for Order #{order.id} of amount {order.total_amount}")
        flash(f"Refund of INR {order.total_amount} for Order #{order.id} processed successfully.", "success")
    except Exception as ex:
        db.session.rollback()
        current_app.logger.error(f"Refund failed for Order #{order.id}: {ex}")
        order.refund_status = 'Failed'
        db.session.commit()
        flash(f"Refund failed: {ex}", "danger")
        
    return redirect(url_for('admin.admin_orders'))

# --- Customer Directory ---

@admin_bp.route('/admin/customers')
@admin_required
def admin_customers():
    search_q = request.args.get('q', '').strip()
    
    query = User.query
    if search_q:
        query = query.filter(User.name.like(f"%{search_q}%") | User.phone.like(f"%{search_q}%"))
        
    customers = query.all()
    
    customer_data = []
    for c in customers:
        spend = db.session.query(db.func.sum(Order.total_amount)).filter_by(user_id=c.id, payment_status='Paid').scalar() or 0.0
        orders_count = Order.query.filter_by(user_id=c.id).count()
        customer_data.append({
            'profile': c,
            'spending': spend,
            'orders_count': orders_count
        })
        
    return render_template('admin_customers.html', customers=customer_data, search_q=search_q)

@admin_bp.route('/admin/customers/<int:user_id>/block', methods=['POST'])
@admin_required
@check_permission(['Super Admin', 'Manager', 'Support Staff'])
def admin_customer_block(user_id):
    user = User.query.get_or_404(user_id)
    user.is_blocked = not user.is_blocked
    db.session.commit()
    
    action_str = "blocked" if user.is_blocked else "unblocked"
    log_audit(f"Toggled customer blocking: {user.name} to {action_str}")
    flash(f"Customer {user.name} has been {action_str}.", "info")
    return redirect(url_for('admin.admin_customers'))

@admin_bp.route('/admin/customers/<int:user_id>/reset-password', methods=['POST'])
@admin_required
@check_permission(['Super Admin', 'Manager'])
def admin_customer_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    
    new_pw = request.form.get('new_password')
    if not new_pw or len(new_pw) < 4:
        flash("Password must be at least 4 characters long.", "warning")
        return redirect(url_for('admin.admin_customers'))
        
    user.password_hash = generate_password_hash(new_pw)
    db.session.commit()
    
    log_audit(f"Reset password of customer: {user.name}")
    flash(f"Password of customer {user.name} reset successfully.", "success")
    return redirect(url_for('admin.admin_customers'))

@admin_bp.route('/admin/customers/<int:user_id>/delete', methods=['POST'])
@admin_required
@check_permission(['Super Admin'])
def admin_customer_delete(user_id):
    user = User.query.get_or_404(user_id)
    name = user.name
    
    db.session.delete(user)
    db.session.commit()
    
    log_audit(f"Deleted user account: {name} (ID: {user_id})")
    flash(f"Customer {name} deleted successfully.", "success")
    return redirect(url_for('admin.admin_customers'))

# --- Reviews Moderation ---

@admin_bp.route('/admin/reviews')
@admin_required
def admin_reviews():
    reviews = Review.query.order_by(Review.created_at.desc()).all()
    return render_template('admin_reviews.html', reviews=reviews)

@admin_bp.route('/admin/reviews/<int:review_id>/update', methods=['POST'])
@admin_required
def admin_review_update(review_id):
    review = Review.query.get_or_404(review_id)
    
    status = request.form.get('status')
    if status in ['Approved', 'Pending', 'Rejected']:
        review.status = status
    
    review.is_featured = request.form.get('is_featured') == 'true'
    review.is_reported = request.form.get('is_reported') == 'true'
    
    db.session.commit()
    log_audit(f"Moderated review ID {review_id} to status: {status}")
    flash("Review updated successfully.", "success")
    return redirect(url_for('admin.admin_reviews'))

@admin_bp.route('/admin/reviews/<int:review_id>/reply', methods=['POST'])
@admin_required
def admin_review_reply(review_id):
    review = Review.query.get_or_404(review_id)
    
    reply = request.form.get('admin_reply', '').strip()
    review.admin_reply = reply if reply else None
    
    db.session.commit()
    log_audit(f"Submitted owner reply to review ID {review_id}")
    flash("Reply saved successfully.", "success")
    return redirect(url_for('admin.admin_reviews'))

@admin_bp.route('/admin/reviews/<int:review_id>/delete', methods=['POST'])
@admin_required
def admin_review_delete(review_id):
    review = Review.query.get_or_404(review_id)
    
    db.session.delete(review)
    db.session.commit()
    
    log_audit(f"Deleted review ID: {review_id}")
    flash("Review deleted successfully.", "success")
    return redirect(url_for('admin.admin_reviews'))

# --- Coupon Management ---

@admin_bp.route('/admin/coupons', methods=['GET', 'POST'])
@admin_required
def admin_coupons():
    if request.method == 'POST':
        code = request.form.get('code').strip().upper()
        discount_amount = float(request.form.get('discount_amount', 0))
        min_order_amount = float(request.form.get('min_order_amount', 0))
        usage_limit = int(request.form.get('usage_limit', 1))
        customer_limit = int(request.form.get('customer_limit', 1))
        discount_type = request.form.get('discount_type', 'Flat')
        max_discount_amount = float(request.form.get('max_discount_amount', 0))
        
        expiry_date_str = request.form.get('expiry_date')
        expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d')
        
        if not code or not discount_amount:
            flash("Coupon code and discount amount are required.", "warning")
        elif Coupon.query.filter_by(code=code).first():
            flash("Coupon code already exists.", "warning")
        else:
            coupon = Coupon(
                code=code,
                discount_amount=discount_amount,
                min_order_amount=min_order_amount,
                usage_limit=usage_limit,
                customer_limit=customer_limit,
                discount_type=discount_type,
                max_discount_amount=max_discount_amount,
                expiry_date=expiry_date,
                is_active=True
            )
            db.session.add(coupon)
            db.session.commit()
            log_audit(f"Created coupon: {code}")
            flash(f"Coupon {code} created.", "success")
            
    coupons = Coupon.query.order_by(Coupon.expiry_date.desc()).all()
    return render_template('admin_coupons.html', coupons=coupons)

@admin_bp.route('/admin/coupons/toggle/<int:coupon_id>', methods=['POST'])
@admin_required
def admin_coupon_toggle(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    coupon.is_active = not coupon.is_active
    db.session.commit()
    
    log_audit(f"Toggled coupon {coupon.code} active state to {coupon.is_active}")
    flash(f"Coupon {coupon.code} status toggled.", "success")
    return redirect(url_for('admin.admin_coupons'))

@admin_bp.route('/admin/coupons/delete/<int:coupon_id>', methods=['POST'])
@admin_required
def admin_coupon_delete(coupon_id):
    coupon = Coupon.query.get_or_404(coupon_id)
    code = coupon.code
    
    db.session.delete(coupon)
    db.session.commit()
    
    log_audit(f"Deleted coupon: {code}")
    flash(f"Coupon {code} deleted.", "success")
    return redirect(url_for('admin.admin_coupons'))

# --- Marketing Offers ---

@admin_bp.route('/admin/offers', methods=['GET', 'POST'])
@admin_required
def admin_offers():
    if request.method == 'POST':
        name = request.form.get('name')
        offer_type = request.form.get('offer_type')
        discount_percent = float(request.form.get('discount_percent', 0))
        brand = request.form.get('brand')
        
        product_id = request.form.get('product_id')
        category_id = request.form.get('category_id')
        
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
        
        offer = Offer(
            name=name,
            offer_type=offer_type,
            discount_percent=discount_percent,
            brand=brand if brand else None,
            product_id=int(product_id) if product_id else None,
            category_id=int(category_id) if category_id else None,
            start_date=start_date,
            end_date=end_date,
            is_active=True
        )
        db.session.add(offer)
        db.session.commit()
        
        log_audit(f"Created offer campaign: {name}")
        flash(f"Offer campaign '{name}' scheduled.", "success")
        
    offers = Offer.query.all()
    products = Product.query.filter_by(is_active=True).all()
    categories = Category.query.filter_by(is_active=True).all()
    
    return render_template('admin_offers.html', offers=offers, products=products, categories=categories)

@admin_bp.route('/admin/offers/toggle/<int:offer_id>', methods=['POST'])
@admin_required
def admin_offer_toggle(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    offer.is_active = not offer.is_active
    db.session.commit()
    
    log_audit(f"Toggled campaign offer {offer.name} active state to {offer.is_active}")
    flash(f"Campaign {offer.name} active status toggled.", "success")
    return redirect(url_for('admin.admin_offers'))

@admin_bp.route('/admin/offers/delete/<int:offer_id>', methods=['POST'])
@admin_required
def admin_offer_delete(offer_id):
    offer = Offer.query.get_or_404(offer_id)
    name = offer.name
    
    db.session.delete(offer)
    db.session.commit()
    
    log_audit(f"Deleted campaign offer: {name}")
    flash(f"Campaign {name} deleted.", "success")
    return redirect(url_for('admin.admin_offers'))

# --- Scheduled Banners ---

@admin_bp.route('/admin/banners', methods=['GET', 'POST'])
@admin_required
def admin_banners():
    if request.method == 'POST':
        title = request.form.get('title')
        image_url = request.form.get('image_url')
        link_url = request.form.get('link_url')
        priority = int(request.form.get('priority', 0))
        
        banner = Banner(
            title=title,
            image_url=image_url,
            link_url=link_url,
            priority=priority,
            is_active=True
        )
        db.session.add(banner)
        db.session.commit()
        
        log_audit(f"Uploaded scheduled banner: {title}")
        flash(f"Banner '{title}' created.", "success")
        
    banners = Banner.query.order_by(Banner.priority.desc()).all()
    return render_template('admin_banners.html', banners=banners)

@admin_bp.route('/admin/banners/toggle/<int:banner_id>', methods=['POST'])
@admin_required
def admin_banner_toggle(banner_id):
    banner = Banner.query.get_or_404(banner_id)
    banner.is_active = not banner.is_active
    db.session.commit()
    
    log_audit(f"Toggled banner {banner.title} status to {banner.is_active}")
    flash(f"Banner status toggled.", "success")
    return redirect(url_for('admin.admin_banners'))

@admin_bp.route('/admin/banners/delete/<int:banner_id>', methods=['POST'])
@admin_required
def admin_banner_delete(banner_id):
    banner = Banner.query.get_or_404(banner_id)
    title = banner.title
    
    db.session.delete(banner)
    db.session.commit()
    
    log_audit(f"Deleted scheduled banner: {title}")
    flash("Banner deleted.", "success")
    return redirect(url_for('admin.admin_banners'))

# --- Push Notifications Announcements ---

@admin_bp.route('/admin/notifications/send', methods=['POST'])
@admin_required
def admin_notifications_send():
    title = request.form.get('title')
    message = request.form.get('message')
    target = request.form.get('target', 'all')
    
    if not title or not message:
        flash("Title and message body are required.", "warning")
        return redirect(url_for('admin.admin_dashboard'))
        
    if target == 'all':
        users = User.query.all()
        for u in users:
            notif = Notification(
                user_id=u.id,
                title=title,
                message=message
            )
            db.session.add(notif)
        db.session.commit()
        log_audit(f"Broadcasted notification '{title}' to all customers.")
        flash(f"Broadcasted notification to {len(users)} users.", "success")
    else:
        user = User.query.filter_by(phone=target).first()
        if user:
            notif = Notification(
                user_id=user.id,
                title=title,
                message=message
            )
            db.session.add(notif)
            db.session.commit()
            log_audit(f"Sent notification to specific customer: {target}")
            flash(f"Notification sent to {user.name}.", "success")
        else:
            flash(f"Customer phone {target} not found.", "danger")
            
    return redirect(url_for('admin.admin_dashboard'))

# --- Business Reports (CSV downloads) ---

@admin_bp.route('/admin/reports/download')
@admin_required
def admin_reports_download():
    report_type = request.args.get('type', 'sales')
    
    si = io.StringIO()
    cw = csv.writer(si)
    
    if report_type == 'sales':
        cw.writerow(['Order ID', 'Recipient Name', 'Payment Method', 'Payment Status', 'Delivery Fee', 'Total Amount', 'Created At'])
        orders = Order.query.all()
        for o in orders:
            cw.writerow([o.id, o.recipient_name, o.payment_method, o.payment_status, o.delivery_fee, o.total_amount, o.created_at])
        filename = f"sales_report_{datetime.now().strftime('%Y%m%d')}.csv"
        
    elif report_type == 'inventory':
        cw.writerow(['Product ID', 'Product Name', 'Category', 'Price', 'Stock Count', 'Minimum Stock Alert', 'Is Active'])
        products = Product.query.all()
        for p in products:
            cw.writerow([p.id, p.name, p.category.name, p.price, p.stock_count, p.min_stock, p.is_active])
        filename = f"inventory_report_{datetime.now().strftime('%Y%m%d')}.csv"
        
    else: # customers
        cw.writerow(['Customer ID', 'Name', 'Phone', 'Village', 'Pincode', 'Is Blocked', 'Joined Date'])
        users = User.query.all()
        for u in users:
            cw.writerow([u.id, u.name, u.phone, u.village, u.pincode, u.is_blocked, u.created_at])
        filename = f"customers_report_{datetime.now().strftime('%Y%m%d')}.csv"
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv"
    return output

# --- Delivery Management ---

@admin_bp.route('/admin/delivery', methods=['GET', 'POST'])
@admin_required
def admin_delivery():
    if request.method == 'POST':
        driver_name = request.form.get('driver_name')
        driver_phone = request.form.get('driver_phone')
        driver_vehicle = request.form.get('driver_vehicle')
        
        if driver_name and driver_phone and driver_vehicle:
            partner = DeliveryPartner(
                name=driver_name,
                phone=driver_phone,
                vehicle_number=driver_vehicle,
                status='Active'
            )
            db.session.add(partner)
            db.session.commit()
            log_audit(f"Registered delivery driver: {driver_name}")
            flash(f"Registered driver {driver_name} successfully.", "success")
            
    partners = DeliveryPartner.query.all()
    zones = DeliverySetting.query.all()
    return render_template('admin_delivery.html', partners=partners, zones=zones)

@admin_bp.route('/admin/delivery/zone/add', methods=['POST'])
@admin_required
def admin_delivery_zone_add():
    pincode = request.form.get('pincode')
    zone_name = request.form.get('zone_name')
    delivery_charge = float(request.form.get('delivery_charge', 30.0))
    min_free = float(request.form.get('min_free_delivery_amount', 499.0))
    est_time = request.form.get('estimated_time', '15-30 Mins')
    
    if pincode and zone_name:
        existing = DeliverySetting.query.filter_by(pincode=pincode).first()
        if existing:
            existing.zone_name = zone_name
            existing.delivery_charge = delivery_charge
            existing.min_free_delivery_amount = min_free
            existing.estimated_time = est_time
            flash("Zone updated.", "success")
        else:
            zone = DeliverySetting(
                pincode=pincode,
                zone_name=zone_name,
                delivery_charge=delivery_charge,
                min_free_delivery_amount=min_free,
                estimated_time=est_time
            )
            db.session.add(zone)
            flash("Zone created.", "success")
            
        db.session.commit()
        log_audit(f"Configured delivery zone for pincode: {pincode}")
        
    return redirect(url_for('admin.admin_delivery'))

# --- System settings ---

@admin_bp.route('/admin/settings', methods=['GET', 'POST'])
@admin_required
def admin_settings():
    if request.method == 'POST':
        for k in ['site_name', 'contact_email', 'contact_phone', 'maintenance_mode', 'currency']:
            v = request.form.get(k)
            if v is not None:
                s = SystemSetting.query.filter_by(key=k).first()
                if s:
                    s.value = v
                else:
                    db.session.add(SystemSetting(key=k, value=v))
        db.session.commit()
        log_audit("Updated core website system settings parameters.")
        flash("System settings saved successfully.", "success")
        
    settings = {s.key: s.value for s in SystemSetting.query.all()}
    logs = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(100).all()
    
    return render_template('admin_settings.html', settings=settings, logs=logs)

# --- Database Backup & Restores ---

@admin_bp.route('/admin/backup/download')
@admin_required
@check_permission(['Super Admin'])
def admin_backup_download():
    db_file_path = os.path.join(current_app.root_path, 'instance', 'gramkart.db')
    if not os.path.exists(db_file_path):
        db_file_path = os.path.join(current_app.root_path, 'gramkart.db')
        
    if os.path.exists(db_file_path):
        log_audit("Downloaded database backup snapshot.")
        return send_file(db_file_path, as_attachment=True, download_name=f"gramkart_db_{datetime.now().strftime('%Y%m%d')}.db")
    else:
        flash("SQLite database file not found on disk.", "danger")
        return redirect(url_for('admin.admin_settings'))

@admin_bp.route('/admin/backup/restore', methods=['POST'])
@admin_required
@check_permission(['Super Admin'])
def admin_backup_restore():
    file = request.files.get('backup_file')
    if not file or not file.filename.endswith('.db'):
        flash("Invalid file format. Upload a valid SQLite .db file.", "danger")
        return redirect(url_for('admin.admin_settings'))
        
    db_file_path = os.path.join(current_app.root_path, 'instance', 'gramkart.db')
    if not os.path.exists(db_file_path):
        db_file_path = os.path.join(current_app.root_path, 'gramkart.db')
        
    try:
        db.session.remove()
        db.engine.dispose()
        
        file.save(db_file_path)
        log_audit("Restored database backup snapshot successfully.")
        flash("Database restored successfully.", "success")
    except Exception as e:
        flash(f"Error restoring database: {e}", "danger")
        
    return redirect(url_for('admin.admin_settings'))
