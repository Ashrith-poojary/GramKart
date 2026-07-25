import re
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, flash, jsonify, current_app, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import joinedload
from extensions import db, limiter, cache
from models import User, Category, Product, Order, OrderItem, Address, Wishlist, Review, Notification, Coupon, RecentlyViewed, DeliverySetting, OrderTimeline
from utils.decorators import login_required
from utils.validators import validate_phone_number, validate_password_complexity, sanitize_string
from services.inventory_service import check_and_deduct_stock
from services.email_service import send_order_confirmation

client_bp = Blueprint('client', __name__)

# Inject cart and settings variables globally
@client_bp.app_context_processor
def inject_globals():
    cart = session.get('cart', {})
    cart_count = sum(cart.values())
    
    # Cache global site settings
    site_name = cache.get('site_name')
    if not site_name:
        from models import SystemSetting
        site_setting = SystemSetting.query.filter_by(key='site_name').first()
        site_name = site_setting.value if site_setting else "GramKart"
        cache.set('site_name', site_name, timeout=3600)
        
    user_id = session.get('user_id')
    current_user = None
    notifications_list = []
    unread_notifications_count = 0
    user_wishlist_ids = []
    if user_id:
        current_user = User.query.get(user_id)
        if current_user:
            notifications_list = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(5).all()
            unread_notifications_count = Notification.query.filter_by(user_id=user_id, is_read=False).count()
            user_wishlist_ids = [w.product_id for w in current_user.wishlist_items]
            
    catalog_list = []
    # Eager load category to prevent N+1 query warnings
    active_prods = Product.query.options(joinedload(Product.category)).filter_by(is_active=True).all()
    for p in active_prods:
        catalog_list.append({
            'id': p.id,
            'name': p.name,
            'price': p.price,
            'unit': p.unit,
            'image_url': p.image_url,
            'category': p.category.name if p.category else ""
        })
        
    return {
        'cart_count': cart_count,
        'site_name': site_name,
        'current_user': current_user,
        'notifications_list': notifications_list,
        'unread_notifications_count': unread_notifications_count,
        'free_delivery_threshold': 499.0,
        'catalog_list': catalog_list,
        'user_wishlist_ids': user_wishlist_ids
    }

# --- Client Views ---

@client_bp.route('/')
def index():
    # Cache active category and banners lists
    categories = cache.get('active_categories')
    if not categories:
        categories = Category.query.options(joinedload(Category.products)).filter_by(is_active=True).order_by(Category.sort_order.asc()).all()
        cache.set('active_categories', categories, timeout=300)
        
    from models import Banner, Offer
    banners = Banner.query.filter_by(is_active=True).order_by(Banner.priority.desc()).all()
    
    # Eager load category products to avoid N+1 query loop in categories templates
    featured_products = Product.query.options(joinedload(Product.category)).filter_by(is_featured=True, is_active=True).limit(8).all()
    trending_products = Product.query.options(joinedload(Product.category)).filter_by(is_trending=True, is_active=True).limit(8).all()
    
    user_id = session.get('user_id')
    current_user = User.query.get(user_id) if user_id else None
    pincode = None
    if current_user:
        default_addr = Address.query.filter_by(user_id=user_id, is_default=True).first()
        if default_addr:
            pincode = default_addr.pincode
            
    recommended_products = get_personalized_recommendations(user_id, limit=8)
    trending_near_you = get_trending_near_you(pincode, limit=8)
    
    # Extract search query
    search_query = request.args.get('q', '').strip()
    if search_query:
        all_products = Product.query.options(joinedload(Product.category)).filter(
            Product.is_active == True,
            Product.name.like(f"%{search_query}%")
        ).all()
        discounted_products = []
    else:
        all_products = Product.query.options(joinedload(Product.category)).filter_by(is_active=True).all()
        discounted_products = Product.query.options(joinedload(Product.category)).filter(
            Product.is_active == True,
            Product.mrp > Product.price
        ).limit(8).all()
    
    return render_template('index.html', 
                           categories=categories, 
                           banners=banners,
                           featured_products=featured_products,
                           trending_products=trending_products,
                           recommended_products=recommended_products,
                           trending_near_you=trending_near_you,
                           all_products=all_products,
                           search_query=search_query,
                           discounted_products=discounted_products)

@client_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute")
def register():
    if 'user_id' in session:
        return redirect(url_for('client.profile'))
        
    if request.method == 'POST':
        name = sanitize_string(request.form.get('name'))
        phone = sanitize_string(request.form.get('phone'))
        password = request.form.get('password')
        village = sanitize_string(request.form.get('village'))
        landmark = sanitize_string(request.form.get('landmark'))
        pincode = sanitize_string(request.form.get('pincode'))
        
        # Validation checks
        if not name or not phone or not password or not village or not landmark or not pincode:
            flash('Please fill out all required fields.', 'danger')
        elif not validate_phone_number(phone):
            flash('Please enter a valid 10-digit Indian phone number.', 'danger')
        elif not validate_password_complexity(password):
            flash('Password must be at least 4 characters long.', 'danger')
        elif User.query.filter_by(phone=phone).first():
            flash('Phone number already registered. Please log in.', 'warning')
        else:
            hashed_pw = generate_password_hash(password)
            user = User(
                name=name,
                phone=phone,
                password_hash=hashed_pw,
                village=village,
                landmark=landmark,
                pincode=pincode
            )
            db.session.add(user)
            db.session.commit()
            
            session['user_id'] = user.id
            session.pop('is_admin', None) # clean admin credentials
            flash('Account created successfully!', 'success')
            return redirect(url_for('client.profile'))
            
    return render_template('login.html', show_register=True)

@client_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    if 'user_id' in session:
        return redirect(url_for('client.profile'))
        
    if request.method == 'POST':
        phone = sanitize_string(request.form.get('phone'))
        password = request.form.get('password')
        
        # 1. Check if login matches admin credentials in the same input field
        from models import Admin
        admin = Admin.query.filter(db.func.lower(Admin.username) == db.func.lower(phone.strip())).first()
        if admin:
            # Check lockout status
            if admin.locked_until and admin.locked_until > datetime.utcnow():
                diff = admin.locked_until - datetime.utcnow()
                flash(f'Account locked due to failed logins. Try again in {int(diff.seconds / 60) + 1} minutes.', 'danger')
                return render_template('login.html', show_register=False)
                
            if check_password_hash(admin.password_hash, password):
                admin.failed_login_attempts = 0
                admin.locked_until = None
                db.session.commit()
                
                session['is_admin'] = True
                session['admin_user_id'] = admin.id
                session['admin_role'] = admin.role
                session['admin_name'] = admin.name
                session.pop('user_id', None) # clear client user session
                
                flash(f'Welcome back, {admin.name} ({admin.role})!', 'success')
                return redirect(url_for('admin.admin_dashboard'))
            else:
                admin.failed_login_attempts += 1
                if admin.failed_login_attempts >= 5:
                    admin.locked_until = datetime.utcnow() + timedelta(minutes=10)
                db.session.commit()
        
        # 2. Otherwise process customer login
        user = User.query.filter_by(phone=phone).first()
        if user:
            if user.is_blocked:
                flash('Your account has been locked or suspended by administrator.', 'danger')
                return render_template('login.html', show_register=False)
                
            if check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session.pop('is_admin', None) # clear admin session
                
                next_page = request.args.get('next')
                flash('Logged in successfully!', 'success')
                return redirect(next_page if next_page else url_for('client.profile'))
                
        flash('Invalid login credentials. Please check your username/phone and password.', 'danger')
        
    return render_template('login.html', show_register=False)

@client_bp.route('/login/google')
def google_login():
    """Mock redirect to Google Accounts sign-in page."""
    return redirect(url_for('client.google_callback', code='mock_google_auth_code_12345'))

@client_bp.route('/login/google/callback')
def google_callback():
    """Google Sign-In OAuth Callback simulator."""
    email = "google_user@gmail.com"
    name = "Google User"
    phone_alias = "9999900000"
    
    user = User.query.filter_by(phone=phone_alias).first()
    if not user:
        user = User(
            name=name,
            phone=phone_alias,
            password_hash=generate_password_hash("google_oauth_secure_password_987"),
            village="Google Land",
            landmark="Oauth Portal",
            pincode="800001"
        )
        db.session.add(user)
        db.session.commit()
        
    session['user_id'] = user.id
    session.pop('is_admin', None)
    flash(f"Welcome back, {name}! Logged in securely via Google.", "success")
    return redirect(url_for('client.profile'))

@client_bp.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out from storefront successfully.', 'info')
    return redirect(url_for('client.index'))

@client_bp.route('/category/<slug>', endpoint='category_detail')
def category_products(slug):
    category = Category.query.filter_by(slug=slug, is_active=True).first_or_404()
    # Eager load products relations
    products = Product.query.options(joinedload(Product.category)).filter_by(category_id=category.id, is_active=True).all()
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('category.html', category=category, products=products, categories=categories)

@client_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.filter_by(id=product_id, is_active=True).first_or_404()
    categories = Category.query.filter_by(is_active=True).all()
    
    # Eager load user profile on reviews list
    reviews = Review.query.options(joinedload(Review.user)).filter_by(product_id=product_id, status='Approved').order_by(Review.created_at.desc()).all()
    
    # Log to recently viewed history
    user_id = session.get('user_id')
    if user_id:
        existing = RecentlyViewed.query.filter_by(user_id=user_id, product_id=product_id).first()
        if existing:
            existing.viewed_at = datetime.utcnow()
        else:
            db.session.add(RecentlyViewed(user_id=user_id, product_id=product_id))
        db.session.commit()
        
    frequently_bought = get_frequently_bought_together(product_id, limit=4)
    return render_template('product.html', product=product, categories=categories, reviews=reviews, frequently_bought=frequently_bought)

@client_bp.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
def submit_review(product_id):
    rating = request.form.get('rating', type=int)
    comment = sanitize_string(request.form.get('comment'))
    image_url = sanitize_string(request.form.get('image_url'))
    
    if not rating or rating < 1 or rating > 5:
        flash('Please select a valid rating between 1 and 5 stars.', 'warning')
        return redirect(url_for('client.product_detail', product_id=product_id))
        
    user_id = session['user_id']
    
    # Verify purchase state before approving "Verified Buyer" badge
    has_purchased = db.session.query(OrderItem).join(Order).filter(
        Order.user_id == user_id,
        OrderItem.product_id == product_id,
        Order.order_status == 'Delivered'
    ).first() is not None
    
    review = Review(
        user_id=user_id,
        product_id=product_id,
        rating=rating,
        comment=comment,
        image_url=image_url if image_url else None,
        status='Approved' if has_purchased else 'Pending' # auto-approve only verified buyers
    )
    db.session.add(review)
    db.session.commit()
    
    if has_purchased:
        flash('Thank you! Your verified purchase review has been published.', 'success')
    else:
        flash('Review submitted! It will appear once approved by moderator.', 'info')
        
    return redirect(url_for('client.product_detail', product_id=product_id))

@client_bp.route('/product/<int:product_id>/review/<int:review_id>/like', methods=['POST'])
@login_required
def like_review(product_id, review_id):
    review = Review.query.get_or_404(review_id)
    review.likes += 1
    db.session.commit()
    return jsonify({'success': True, 'likes': review.likes})

# --- Cart System ---

@client_bp.route('/cart', endpoint='cart')
def cart_summary():
    cart = session.get('cart', {})
    cart_items = []
    subtotal = 0.0
    
    if cart:
        # Load products in a single eager loaded query to avoid N+1 queries
        products = Product.query.options(joinedload(Product.category)).filter(Product.id.in_(cart.keys()), Product.is_active == True).all()
        for p in products:
            qty = cart[str(p.id)]
            total_price = p.price * qty
            subtotal += total_price
            cart_items.append({
                'product': p,
                'quantity': qty,
                'total_price': total_price
            })
            
    # Delivery fee logic
    delivery_fee = 30.0 if subtotal < 499.0 else 0.0
    total_amount = subtotal + delivery_fee
    
    return render_template('cart.html', cart_items=cart_items, subtotal=subtotal, delivery_fee=delivery_fee, total_amount=total_amount)

@client_bp.route('/cart/add/<int:product_id>', methods=['POST'])
def cart_add(product_id):
    p = Product.query.get_or_404(product_id)
    cart = session.get('cart', {})
    
    # Fetch quantity
    qty = request.form.get('quantity', 1, type=int)
    
    # Check catalog stock availability
    current_qty = cart.get(str(product_id), 0)
    target_qty = current_qty + qty
    
    if p.stock_count < target_qty:
        return jsonify({'success': False, 'message': f'Insufficient stock. Only {p.stock_count} units available.'}), 400
        
    cart[str(product_id)] = target_qty
    session['cart'] = cart
    session.modified = True
    
    return jsonify({
        'success': True,
        'cart_count': sum(cart.values()),
        'message': f'{p.name} added to cart.'
    })

@client_bp.route('/cart/update/<int:product_id>', methods=['POST'])
def cart_update(product_id):
    p = Product.query.get_or_404(product_id)
    cart = session.get('cart', {})
    
    data = request.get_json()
    if not data or 'quantity' not in data:
        return jsonify({'success': False, 'message': 'Invalid request parameters.'}), 400
        
    qty = int(data['quantity'])
    if qty <= 0:
        cart.pop(str(product_id), None)
    else:
        if p.stock_count < qty:
            return jsonify({'success': False, 'message': f'Only {p.stock_count} units available.'}), 400
        cart[str(product_id)] = qty
        
    session['cart'] = cart
    session.modified = True
    
    return jsonify({
        'success': True,
        'cart_count': sum(cart.values()),
        'message': 'Cart updated.'
    })

@client_bp.route('/cart/remove/<int:product_id>', methods=['POST'])
def cart_remove(product_id):
    cart = session.get('cart', {})
    cart.pop(str(product_id), None)
    session['cart'] = cart
    session.modified = True
    return jsonify({
        'success': True,
        'cart_count': sum(cart.values())
    })

# --- Checkout & Order placement ---

@client_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart:
        flash('Your cart is empty.', 'warning')
        return redirect(url_for('client.cart_summary'))
        
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    # Calculate cart values
    subtotal = 0.0
    products = Product.query.filter(Product.id.in_(cart.keys()), Product.is_active == True).all()
    for p in products:
        subtotal += p.price * cart[str(p.id)]
        
    # Check coupon deductions
    coupon_code = session.get('discount_coupon')
    discount = 0.0
    if coupon_code:
        coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
        if coupon and coupon.expiry_date >= datetime.utcnow() and subtotal >= coupon.min_order_amount:
            if coupon.discount_type == 'Percentage':
                discount = subtotal * (coupon.discount_amount / 100.0)
                if coupon.max_discount_amount > 0:
                    discount = min(discount, coupon.max_discount_amount)
            else: # Flat
                discount = coupon.discount_amount
                
    delivery_fee = 30.0 if subtotal < 499.0 else 0.0
    total_amount = max(0.0, subtotal - discount + delivery_fee)
    
    addresses = Address.query.filter_by(user_id=user_id).all()
    default_address = Address.query.filter_by(user_id=user_id, is_default=True).first()
    
    if request.method == 'POST':
        # Placed checkout order details
        recipient_name = sanitize_string(request.form.get('recipient_name'))
        recipient_phone = sanitize_string(request.form.get('recipient_phone'))
        village = sanitize_string(request.form.get('village'))
        landmark = sanitize_string(request.form.get('landmark'))
        pincode = sanitize_string(request.form.get('pincode'))
        payment_method = request.form.get('payment_method', 'COD')
        delivery_slot = request.form.get('delivery_slot')
        
        if not recipient_name or not recipient_phone or not village or not landmark or not pincode:
            flash('Please specify delivery address details.', 'danger')
            return redirect(url_for('client.checkout'))
            
        # 1. Begin SQL Transaction atomic checks
        db.session.begin_nested()
        try:
            # 2. Check and deduct inventory levels
            order_items_to_create = []
            for p in products:
                qty = cart[str(p.id)]
                success, msg = check_and_deduct_stock(p.id, qty, reason='Order')
                if not success:
                    db.session.rollback()
                    flash(msg, 'danger')
                    return redirect(url_for('client.cart_summary'))
                    
                order_items_to_create.append(OrderItem(
                    product_id=p.id,
                    quantity=qty,
                    price=p.price
                ))
                
            # 3. Create Order
            order = Order(
                user_id=user_id,
                recipient_name=recipient_name,
                recipient_phone=recipient_phone,
                delivery_village=village,
                delivery_landmark=landmark,
                delivery_pincode=pincode,
                payment_method=payment_method,
                payment_status='Pending',
                order_status='Placed',
                delivery_fee=delivery_fee,
                total_amount=total_amount,
                delivery_slot=delivery_slot
            )
            db.session.add(order)
            db.session.flush() # populate order.id
            
            # Associate items
            for item in order_items_to_create:
                item.order_id = order.id
                db.session.add(item)
                
            # Add initial status to timeline logs
            timeline = OrderTimeline(
                order_id=order.id,
                status='Placed',
                message='Order placed successfully.'
            )
            db.session.add(timeline)
            
            db.session.commit() # commit nested transaction
            db.session.commit() # commit outer transaction
            
            # Clear cart session
            session.pop('cart', None)
            session.pop('discount_coupon', None)
            
            # Send asynchronous order confirmation receipt email
            try:
                send_order_confirmation(user.phone + "@gramkart.com", user.name, order.id, total_amount)
            except:
                pass
                
            flash('Order placed successfully!', 'success')
            return redirect(url_for('client.order_success', order_id=order.id))
        except Exception as e:
            db.session.rollback()
            flash(f'Checkout transaction failed: {e}', 'danger')
            return redirect(url_for('client.checkout'))
            
    return render_template('checkout.html', 
                           addresses=addresses, 
                           default_address=default_address, 
                           subtotal=subtotal, 
                           discount=discount, 
                           delivery_fee=delivery_fee, 
                           total_amount=total_amount)

@client_bp.route('/order/success/<int:order_id>')
@login_required
def order_success(order_id):
    order = Order.query.options(joinedload(Order.items)).get_or_404(order_id)
    if order.user_id != session['user_id']:
        flash('Unauthorized access: This order does not belong to your account.', 'danger')
        return redirect(url_for('client.orders'))
    return render_template('order_success.html', order=order)

# --- Razorpay Payment Gateway API Integration ---

@client_bp.route('/checkout/razorpay/create', methods=['POST'])
@login_required
def razorpay_create_order():
    import razorpay
    cart = session.get('cart', {})
    if not cart:
        return jsonify({'success': False, 'message': 'Cart is empty.'}), 400
        
    user_id = session['user_id']
    user = User.query.get(user_id)
    
    # Calculate cart values
    subtotal = 0.0
    products = Product.query.filter(Product.id.in_(cart.keys()), Product.is_active == True).all()
    for p in products:
        subtotal += p.price * cart[str(p.id)]
        
    coupon_code = session.get('discount_coupon')
    discount = 0.0
    if coupon_code:
        coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
        if coupon and coupon.expiry_date >= datetime.utcnow() and subtotal >= coupon.min_order_amount:
            if coupon.discount_type == 'Percentage':
                discount = subtotal * (coupon.discount_amount / 100.0)
                if coupon.max_discount_amount > 0:
                    discount = min(discount, coupon.max_discount_amount)
            else:
                discount = coupon.discount_amount
                
    delivery_fee = 30.0 if subtotal < 499.0 else 0.0
    total_amount = max(0.0, subtotal - discount + delivery_fee)
    
    recipient_name = sanitize_string(request.json.get('recipient_name'))
    recipient_phone = sanitize_string(request.json.get('recipient_phone'))
    village = sanitize_string(request.json.get('village'))
    landmark = sanitize_string(request.json.get('landmark'))
    pincode = sanitize_string(request.json.get('pincode'))
    delivery_slot = request.json.get('delivery_slot')
    
    if not recipient_name or not recipient_phone or not village or not landmark or not pincode:
        return jsonify({'success': False, 'message': 'Please specify delivery address details.'}), 400
        
    # Check inventory before creating payment intent
    for p in products:
        qty = cart[str(p.id)]
        if p.stock_count < qty:
            return jsonify({'success': False, 'message': f'Insufficient stock for product {p.name}. Only {p.stock_count} units left.'}), 400
            
    try:
        # Create DB order in PendingPayment state
        order = Order(
            user_id=user_id,
            recipient_name=recipient_name,
            recipient_phone=recipient_phone,
            delivery_village=village,
            delivery_landmark=landmark,
            delivery_pincode=pincode,
            payment_method='Razorpay',
            payment_status='Pending',
            order_status='PendingPayment',
            delivery_fee=delivery_fee,
            total_amount=total_amount,
            delivery_slot=delivery_slot
        )
        db.session.add(order)
        db.session.flush()
        
        # Associate items
        for p in products:
            qty = cart[str(p.id)]
            db.session.add(OrderItem(
                order_id=order.id,
                product_id=p.id,
                quantity=qty,
                price=p.price
            ))
            
        # Create Razorpay Order
        key_id = current_app.config['RAZORPAY_KEY_ID']
        key_secret = current_app.config['RAZORPAY_KEY_SECRET']
        client = razorpay.Client(auth=(key_id, key_secret))
        
        order_data = {
            'amount': int(total_amount * 100),
            'currency': 'INR',
            'receipt': f'receipt_order_{order.id}',
            'payment_capture': 1
        }
        
        razorpay_order = client.order.create(data=order_data)
        
        order.razorpay_order_id = razorpay_order['id']
        db.session.commit()
        
        return jsonify({
            'success': True,
            'key_id': key_id,
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency'],
            'order_id': razorpay_order['id'],
            'recipient_name': recipient_name,
            'recipient_phone': recipient_phone,
            'user_email': user.phone + "@gramkart.com",
            'db_order_id': order.id
        })
    except Exception as ex:
        db.session.rollback()
        current_app.logger.error(f"Razorpay order creation failed: {ex}")
        return jsonify({'success': False, 'message': f'Razorpay order creation failed: {ex}'}), 500


@client_bp.route('/payment/verify', methods=['POST'])
@login_required
def razorpay_verify_payment():
    import razorpay
    data = request.json
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_signature = data.get('razorpay_signature')
    db_order_id = data.get('db_order_id')
    
    order = Order.query.get(db_order_id)
    if not order:
        return jsonify({'success': False, 'message': 'Order not found.'}), 404
        
    # Verify signature
    key_id = current_app.config['RAZORPAY_KEY_ID']
    key_secret = current_app.config['RAZORPAY_KEY_SECRET']
    client = razorpay.Client(auth=(key_id, key_secret))
    
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }
    
    try:
        client.utility.verify_payment_signature(params_dict)
        
        # Atomically deduct stock levels
        db.session.begin_nested()
        for item in order.items:
            success, msg = check_and_deduct_stock(item.product_id, item.quantity, reason='Order')
            if not success:
                db.session.rollback()
                order.order_status = 'Cancelled'
                order.payment_status = 'Refunded'
                order.refund_status = 'Processed'
                db.session.commit()
                # Trigger automatic refund immediately
                try:
                    client.payment.refund(razorpay_payment_id, {'amount': int(order.total_amount * 100)})
                except:
                    pass
                return jsonify({'success': False, 'message': f'Payment success, but stock deduction failed. Auto-refund triggered: {msg}'}), 400
                
        # Confirm order placement
        order.payment_status = 'Paid'
        order.payment_reference = razorpay_payment_id
        order.razorpay_payment_id = razorpay_payment_id
        order.razorpay_signature = razorpay_signature
        order.order_status = 'Placed'
        
        db.session.add(OrderTimeline(
            order_id=order.id,
            status='Placed',
            message='Online payment verified successfully.'
        ))
        
        db.session.commit()
        db.session.commit()
        
        # Clear cart session
        session.pop('cart', None)
        session.pop('discount_coupon', None)
        
        # Emit SocketIO real-time notification
        try:
            from extensions import socketio
            socketio.emit('new_order', {'order_id': order.id, 'total': order.total_amount}, to='admin_room')
            socketio.emit('order_status_update', {'order_id': order.id, 'status': 'Placed'}, room=f'user_{order.user_id}')
        except Exception as socket_ex:
            current_app.logger.warning(f"SocketIO order notifications failed: {socket_ex}")
            
        # Send confirmation email
        try:
            user = User.query.get(order.user_id)
            send_order_confirmation(user.phone + "@gramkart.com", user.name, order.id, order.total_amount)
        except:
            pass
            
        return jsonify({'success': True, 'message': 'Payment verified and order placed.'})
    except Exception as ex:
        current_app.logger.error(f"Razorpay signature verification failed: {ex}")
        order.payment_status = 'Failed'
        db.session.commit()
        return jsonify({'success': False, 'message': f'Signature verification failed: {ex}'}), 400

@client_bp.route('/payment/retry/<int:order_id>', methods=['POST'])
@login_required
def payment_retry(order_id):
    import razorpay
    order = Order.query.get_or_404(order_id)
    if order.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized access.'}), 403
        
    if order.payment_status == 'Paid':
        return jsonify({'success': False, 'message': 'Order is already paid.'}), 400
        
    for item in order.items:
        if item.product.stock_count < item.quantity:
            return jsonify({'success': False, 'message': f'Cannot retry payment: {item.product.name} is currently out of stock.'}), 400
            
    try:
        key_id = current_app.config['RAZORPAY_KEY_ID']
        key_secret = current_app.config['RAZORPAY_KEY_SECRET']
        client = razorpay.Client(auth=(key_id, key_secret))
        
        order_data = {
            'amount': int(order.total_amount * 100),
            'currency': 'INR',
            'receipt': f'receipt_order_{order.id}',
            'payment_capture': 1
        }
        
        razorpay_order = client.order.create(data=order_data)
        
        order.razorpay_order_id = razorpay_order['id']
        db.session.commit()
        
        user = User.query.get(order.user_id)
        return jsonify({
            'success': True,
            'key_id': key_id,
            'amount': razorpay_order['amount'],
            'currency': razorpay_order['currency'],
            'order_id': razorpay_order['id'],
            'recipient_name': order.recipient_name,
            'recipient_phone': order.recipient_phone,
            'user_email': user.phone + "@gramkart.com",
            'db_order_id': order.id
        })
    except Exception as ex:
        current_app.logger.error(f"Razorpay retry order creation failed: {ex}")
        return jsonify({'success': False, 'message': f'Razorpay retry order creation failed: {ex}'}), 500

# --- Wishlist ---

@client_bp.route('/wishlist')
@login_required
def wishlist():
    # Eager load products on wishlist query
    items = Wishlist.query.options(joinedload(Wishlist.product)).filter_by(user_id=session['user_id']).all()
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('wishlist.html', items=items, categories=categories)

@client_bp.route('/wishlist/add/<int:product_id>', methods=['POST'])
@login_required
def wishlist_toggle(product_id):
    user_id = session['user_id']
    existing = Wishlist.query.filter_by(user_id=user_id, product_id=product_id).first()
    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({'success': True, 'added': False})
    else:
        db.session.add(Wishlist(user_id=user_id, product_id=product_id))
        db.session.commit()
        return jsonify({'success': True, 'added': True})

# --- Profile Section ---

@client_bp.route('/profile')
@login_required
def profile():
    user_id = session['user_id']
    user = User.query.get(user_id)
    addresses = Address.query.filter_by(user_id=user_id).all()
    
    # Eager load items and products on order history
    orders = Order.query.options(joinedload(Order.items).joinedload(OrderItem.product)).filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    
    return render_template('profile.html', user=user, addresses=addresses, orders=orders)

@client_bp.route('/profile/address/add', methods=['POST'])
@login_required
def address_add():
    recipient_name = sanitize_string(request.form.get('recipient_name'))
    recipient_phone = sanitize_string(request.form.get('recipient_phone'))
    village = sanitize_string(request.form.get('village'))
    landmark = sanitize_string(request.form.get('landmark'))
    pincode = sanitize_string(request.form.get('pincode'))
    
    if not recipient_name or not recipient_phone or not village or not landmark or not pincode:
        flash('All fields are required.', 'danger')
        return redirect(url_for('client.profile'))
        
    user_id = session['user_id']
    
    # If this is the user's first address, set as default
    is_default = Address.query.filter_by(user_id=user_id).count() == 0
    
    addr = Address(
        user_id=user_id,
        recipient_name=recipient_name,
        recipient_phone=recipient_phone,
        village=village,
        landmark=landmark,
        pincode=pincode,
        is_default=is_default
    )
    db.session.add(addr)
    db.session.commit()
    flash('Address saved successfully.', 'success')
    return redirect(url_for('client.profile'))

@client_bp.route('/profile/address/default/<int:address_id>', methods=['POST'])
@login_required
def address_default(address_id):
    user_id = session['user_id']
    # Reset all default flags
    Address.query.filter_by(user_id=user_id).update({'is_default': False})
    
    addr = Address.query.filter_by(id=address_id, user_id=user_id).first_or_404()
    addr.is_default = True
    db.session.commit()
    flash('Default address updated.', 'success')
    return redirect(url_for('client.profile'))

@client_bp.route('/notifications/read/<int:notification_id>', methods=['POST'])
@login_required
def notification_read(notification_id):
    notif = Notification.query.filter_by(id=notification_id, user_id=session['user_id']).first_or_404()
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})

@client_bp.route('/support/ticket/create', methods=['POST'])
@login_required
def ticket_create():
    # support ticket logs placeholder (Phase 2 feature preservation)
    flash('Support ticket raised. Staff will review shortly.', 'success')
    return redirect(url_for('client.profile'))

@client_bp.route('/reorder/<int:order_id>', methods=['POST'])
@login_required
def reorder(order_id):
    order = Order.query.get_or_404(order_id)
    cart = {}
    for item in order.items:
        cart[str(item.product_id)] = item.quantity
    session['cart'] = cart
    session.modified = True
    flash('Items added to cart from previous order.', 'success')
    return redirect(url_for('client.cart_summary'))

@client_bp.route('/orders', endpoint='orders')
@login_required
def orders():
    user_id = session['user_id']
    orders = Order.query.options(joinedload(Order.items).joinedload(OrderItem.product)).filter_by(user_id=user_id).order_by(Order.created_at.desc()).all()
    return render_template('orders.html', orders=orders)

@client_bp.route('/order/<int:order_id>', endpoint='order_detail')
@login_required
def order_detail(order_id):
    user_id = session['user_id']
    order = Order.query.options(joinedload(Order.items).joinedload(OrderItem.product)).filter_by(id=order_id, user_id=user_id).first_or_404()
    return render_template('order_detail.html', order=order)

@client_bp.route('/support')
@login_required
def support():
    categories = Category.query.filter_by(is_active=True).all()
    return render_template('support.html', categories=categories)

# --- Localization Support ---

@client_bp.app_template_global('_t')
def translate(key):
    lang = session.get('lang', 'en')
    translations = {
        'en': {
            'search_placeholder': 'Search for groceries...',
            'categories': 'Categories',
            'add_to_cart': 'Add to Cart',
            'wishlist': 'Wishlist',
            'checkout': 'Checkout',
            'order_now': 'Order Now',
            'trending': 'Trending Near You',
            'recommended': 'Recommended for You',
            'voice_search': 'Voice Search',
            'delivery_slot': 'Delivery Slot',
            'payment_method': 'Payment Method'
        },
        'hi': {
            'search_placeholder': 'किराना सामान खोजें...',
            'categories': 'श्रेणियाँ',
            'add_to_cart': 'कार्ट में जोड़ें',
            'wishlist': 'इच्छा-सूची',
            'checkout': 'चेकआउट',
            'order_now': 'अभी खरीदें',
            'trending': 'आपके पास लोकप्रिय',
            'recommended': 'आपके लिए अनुशंसित',
            'voice_search': 'आवाज खोज',
            'delivery_slot': 'डिलीवरी का समय',
            'payment_method': 'भुगतान का तरीका'
        },
        'kn': {
            'search_placeholder': 'ಕಿರಾಣಿ ಸಾಮಗ್ರಿಗಳನ್ನು ಹುಡುಕಿ...',
            'categories': 'ವರ್ಗಗಳು',
            'add_to_cart': 'ಕಾರ್ಟ್‌ಗೆ ಸೇರಿಸಿ',
            'wishlist': 'ವಿಶ್‌ಲಿಸ್ಟ್',
            'checkout': 'ಚೆಕ್‌ಔಟ್',
            'order_now': 'ಈಗಲೇ ಖರೀದಿಸಿ',
            'trending': 'ನಿಮ್ಮ ಹತ್ತಿರದ ಟ್ರೆಂಡಿಂಗ್',
            'recommended': 'ನಿಮಗಾಗಿ ಶಿಫಾರಸು ಮಾಡಲಾಗಿದೆ',
            'voice_search': 'ಧ್ವನಿ ಹುಡುಕಾಟ',
            'delivery_slot': 'ವಿತರಣಾ ಸಮಯ',
            'payment_method': 'ಪಾವತಿ ವಿಧಾನ'
        }
    }
    return translations.get(lang, translations['en']).get(key, key)

@client_bp.route('/language/<lang_code>')
def set_language(lang_code):
    if lang_code in ['en', 'hi', 'kn']:
        session['lang'] = lang_code
        session.modified = True
        flash(f"Language switched successfully.", "success")
    return redirect(request.referrer or url_for('client.index'))

# --- Dynamic SEO & Sitemap ---

@client_bp.route('/sitemap.xml')
def sitemap():
    sitemap_xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap_xml.append(f'<url><loc>{url_for("client.index", _external=True)}</loc><changefreq>daily</changefreq><priority>1.0</priority></url>')
    
    categories = Category.query.filter_by(is_active=True).all()
    for cat in categories:
        sitemap_xml.append(f'<url><loc>{url_for("client.category_detail", slug=cat.slug, _external=True)}</loc><changefreq>weekly</changefreq><priority>0.8</priority></url>')
        
    products = Product.query.filter_by(is_active=True).all()
    for prod in products:
        sitemap_xml.append(f'<url><loc>{url_for("client.product_detail", product_id=prod.id, _external=True)}</loc><changefreq>weekly</changefreq><priority>0.6</priority></url>')
    sitemap_xml.append('</urlset>')
    
    response = make_response('\n'.join(sitemap_xml))
    response.headers["Content-Type"] = "application/xml"
    return response

@client_bp.route('/robots.txt')
def robots():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /checkout/",
        "Disallow: /profile/",
        f"Sitemap: {url_for('client.sitemap', _external=True)}"
    ]
    response = make_response('\n'.join(lines))
    response.headers["Content-Type"] = "text/plain"
    return response

# --- AI Recommendation Engine Helpers ---

def get_personalized_recommendations(user_id, limit=4):
    if not user_id:
        return Product.query.filter_by(is_active=True, is_recommended=True).limit(limit).all()
    
    try:
        past_orders = Order.query.filter_by(user_id=user_id).all()
        order_ids = [o.id for o in past_orders]
        
        cat_ids = db.session.query(Product.category_id).join(OrderItem).filter(
            OrderItem.order_id.in_(order_ids)
        ).distinct().all()
        
        cat_ids = [c[0] for c in cat_ids if c[0]]
        
        if not cat_ids:
            wish_cat_ids = db.session.query(Product.category_id).join(Wishlist).filter(
                Wishlist.user_id == user_id
            ).distinct().all()
            cat_ids = [c[0] for c in wish_cat_ids if c[0]]
            
        if not cat_ids:
            return Product.query.filter_by(is_active=True, is_recommended=True).limit(limit).all()
            
        return Product.query.filter(
            Product.category_id.in_(cat_ids),
            Product.is_active == True
        ).limit(limit).all()
    except:
        return Product.query.filter_by(is_active=True, is_recommended=True).limit(limit).all()

def get_trending_near_you(pincode, limit=4):
    if not pincode:
        return Product.query.filter_by(is_active=True, is_trending=True).limit(limit).all()
        
    try:
        trending_items = db.session.query(
            OrderItem.product_id,
            db.func.count(OrderItem.id).label('freq')
        ).join(Order).filter(
            Order.delivery_pincode == pincode
        ).group_by(OrderItem.product_id).order_by(db.desc('freq')).limit(limit).all()
        
        if not trending_items:
            return Product.query.filter_by(is_active=True, is_trending=True).limit(limit).all()
            
        trending_ids = [t[0] for t in trending_items]
        return Product.query.filter(Product.id.in_(trending_ids), Product.is_active == True).all()
    except:
        return Product.query.filter_by(is_active=True, is_trending=True).limit(limit).all()

def get_frequently_bought_together(product_id, limit=4):
    try:
        order_ids = [item.order_id for item in OrderItem.query.filter_by(product_id=product_id).all()]
        if not order_ids:
            return Product.query.filter(Product.id != product_id, Product.is_active == True).limit(limit).all()
            
        co_occurring = db.session.query(
            OrderItem.product_id,
            db.func.count(OrderItem.id).label('freq')
        ).filter(
            OrderItem.order_id.in_(order_ids),
            OrderItem.product_id != product_id
        ).group_by(OrderItem.product_id).order_by(db.desc('freq')).limit(limit).all()
        
        if not co_occurring:
            return Product.query.filter(Product.id != product_id, Product.is_active == True).limit(limit).all()
            
        co_ids = [item[0] for item in co_occurring]
        return Product.query.filter(Product.id.in_(co_ids), Product.is_active == True).all()
    except:
        return Product.query.filter(Product.id != product_id, Product.is_active == True).limit(limit).all()
