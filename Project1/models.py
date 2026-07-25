from datetime import datetime
from extensions import db

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(15), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    village = db.Column(db.String(100), nullable=False)
    landmark = db.Column(db.String(100), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    is_blocked = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    orders = db.relationship('Order', backref='customer', lazy=True, cascade="all, delete-orphan")
    wishlist_items = db.relationship('Wishlist', backref='user', lazy=True, cascade="all, delete-orphan")
    addresses = db.relationship('Address', backref='user', lazy=True, cascade="all, delete-orphan")
    reviews = db.relationship('Review', backref='user', lazy=True, cascade="all, delete-orphan")
    notifications = db.relationship('Notification', backref='user', lazy=True, cascade="all, delete-orphan")

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False, index=True)
    image_url = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    
    products = db.relationship('Product', backref='category', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'image_url': self.image_url,
            'is_active': self.is_active,
            'sort_order': self.sort_order
        }

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price = db.Column(db.Float, nullable=False)
    mrp = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(50), nullable=False)
    stock_count = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, index=True)
    
    # Extra columns
    subcategory = db.Column(db.String(100), nullable=True)
    brand = db.Column(db.String(100), nullable=True)
    sku = db.Column(db.String(100), nullable=True)
    barcode = db.Column(db.String(100), nullable=True)
    weight = db.Column(db.String(50), nullable=True)
    min_stock = db.Column(db.Integer, default=5)
    max_stock = db.Column(db.Integer, default=100)
    specifications = db.Column(db.Text, nullable=True)
    ingredients = db.Column(db.Text, nullable=True)
    expiry_date = db.Column(db.DateTime, nullable=True)
    is_featured = db.Column(db.Boolean, default=False)
    is_trending = db.Column(db.Boolean, default=False)
    is_flash_sale = db.Column(db.Boolean, default=False)
    is_best_seller = db.Column(db.Boolean, default=False)
    is_recommended = db.Column(db.Boolean, default=False)
    image_urls = db.Column(db.Text, nullable=True)

    def to_dict(self):
        return {
            'id': self.id,
            'category_id': self.category_id,
            'name': self.name,
            'description': self.description,
            'price': self.price,
            'mrp': self.mrp,
            'unit': self.unit,
            'stock_count': self.stock_count,
            'image_url': self.image_url,
            'is_active': self.is_active,
            'subcategory': self.subcategory,
            'brand': self.brand,
            'sku': self.sku,
            'barcode': self.barcode,
            'weight': self.weight,
            'min_stock': self.min_stock,
            'max_stock': self.max_stock,
            'specifications': self.specifications,
            'ingredients': self.ingredients,
            'expiry_date': self.expiry_date.strftime('%Y-%m-%d') if self.expiry_date else None,
            'is_featured': self.is_featured,
            'is_trending': self.is_trending,
            'is_flash_sale': self.is_flash_sale,
            'is_best_seller': self.is_best_seller,
            'is_recommended': self.is_recommended,
            'image_urls': self.image_urls
        }

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    recipient_name = db.Column(db.String(100), nullable=False)
    recipient_phone = db.Column(db.String(15), nullable=False)
    delivery_village = db.Column(db.String(100), nullable=False)
    delivery_landmark = db.Column(db.String(100), nullable=False)
    delivery_pincode = db.Column(db.String(10), nullable=False)
    payment_method = db.Column(db.String(20), nullable=False) # "COD" or "UPI"
    payment_reference = db.Column(db.String(100), nullable=True)
    payment_status = db.Column(db.String(20), default='Pending', index=True) # "Pending", "Paid"
    order_status = db.Column(db.String(20), default='Placed', index=True) # "Placed", "Packed", "Out for Delivery", "Delivered"
    delivery_fee = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Advanced delivery attributes
    delivery_slot = db.Column(db.String(100), nullable=True)
    
    # Razorpay payment attributes
    razorpay_order_id = db.Column(db.String(100), nullable=True)
    razorpay_payment_id = db.Column(db.String(100), nullable=True)
    razorpay_signature = db.Column(db.String(255), nullable=True)
    refund_status = db.Column(db.String(50), nullable=True) # "Requested", "Processed", "Failed"
    
    # Advanced delivery logistics
    delivery_partner_id = db.Column(db.Integer, db.ForeignKey('delivery_partners.id', ondelete='SET NULL'), nullable=True)
    delivery_otp = db.Column(db.String(10), nullable=True)
    delivery_proof_url = db.Column(db.String(255), nullable=True)
    driver_latitude = db.Column(db.Float, default=25.5941)
    driver_longitude = db.Column(db.Float, default=85.1376)
    
    items = db.relationship('OrderItem', backref='order', lazy='subquery', cascade="all, delete-orphan")
    timeline_logs = db.relationship('OrderTimeline', backref='order', lazy=True, cascade="all, delete-orphan")

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='RESTRICT'), nullable=False, index=True)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False) # Price at which ordered
    
    product = db.relationship('Product', lazy='joined')

class Address(db.Model):
    __tablename__ = 'addresses'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    recipient_name = db.Column(db.String(100), nullable=False)
    recipient_phone = db.Column(db.String(15), nullable=False)
    village = db.Column(db.String(100), nullable=False)
    landmark = db.Column(db.String(100), nullable=False)
    pincode = db.Column(db.String(10), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Wishlist(db.Model):
    __tablename__ = 'wishlists'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    
    product = db.relationship('Product', backref='wishlisted_by', lazy='joined')

class Review(db.Model):
    __tablename__ = 'reviews'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(255), nullable=True)
    likes = db.Column(db.Integer, default=0)
    admin_reply = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='Approved') # 'Approved', 'Pending', 'Rejected'
    is_featured = db.Column(db.Boolean, default=False)
    is_reported = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', backref=db.backref('reviews_list', lazy=True, cascade="all, delete-orphan"))

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'product_id': self.product_id,
            'rating': self.rating,
            'comment': self.comment,
            'image_url': self.image_url,
            'likes': self.likes,
            'admin_reply': self.admin_reply,
            'status': self.status,
            'is_featured': self.is_featured,
            'is_reported': self.is_reported,
            'created_at': self.created_at.strftime('%Y-%m-%d')
        }

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    title = db.Column(db.String(150), nullable=False)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Coupon(db.Model):
    __tablename__ = 'coupons'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False, index=True)
    discount_amount = db.Column(db.Float, nullable=False)
    min_order_amount = db.Column(db.Float, default=0.0)
    usage_limit = db.Column(db.Integer, default=1)
    times_used = db.Column(db.Integer, default=0)
    expiry_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    discount_type = db.Column(db.String(20), default='Flat') # 'Flat', 'Percentage'
    max_discount_amount = db.Column(db.Float, default=0.0)
    customer_limit = db.Column(db.Integer, default=1)

class RecentlyViewed(db.Model):
    __tablename__ = 'recently_viewed'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', lazy='joined')

class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(50), nullable=False, default='Manager')
    is_active = db.Column(db.Boolean, default=True)
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id', ondelete='SET NULL'), nullable=True, index=True)
    action = db.Column(db.String(255), nullable=False)
    ip_address = db.Column(db.String(50), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    admin = db.relationship('Admin', backref=db.backref('logs_list', lazy='dynamic'))

class Offer(db.Model):
    __tablename__ = 'offers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    offer_type = db.Column(db.String(50), nullable=False)
    discount_percent = db.Column(db.Float, default=0.0)
    start_date = db.Column(db.DateTime, nullable=False)
    end_date = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=True, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=True, index=True)
    brand = db.Column(db.String(100), nullable=True)
    
    product = db.relationship('Product', lazy='joined')
    category = db.relationship('Category', lazy='joined')

class Banner(db.Model):
    __tablename__ = 'banners'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    image_url = db.Column(db.String(255), nullable=False)
    link_url = db.Column(db.String(255), nullable=True)
    priority = db.Column(db.Integer, default=0)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

class DeliverySetting(db.Model):
    __tablename__ = 'delivery_settings'
    id = db.Column(db.Integer, primary_key=True)
    pincode = db.Column(db.String(10), unique=True, nullable=False, index=True)
    zone_name = db.Column(db.String(100), nullable=False)
    delivery_charge = db.Column(db.Float, default=30.0)
    min_free_delivery_amount = db.Column(db.Float, default=499.0)
    estimated_time = db.Column(db.String(100), default='15-30 Mins')
    is_active = db.Column(db.Boolean, default=True)

class DeliveryPartner(db.Model):
    __tablename__ = 'delivery_partners'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    vehicle_number = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(50), default='Active')
    
    # Relation back to orders
    orders = db.relationship('Order', backref='driver', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'phone': self.phone,
            'status': self.status,
            'vehicle_number': self.vehicle_number
        }

class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)

class InventoryLog(db.Model):
    __tablename__ = 'inventory_logs'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    change_qty = db.Column(db.Integer, nullable=False)
    previous_stock = db.Column(db.Integer, nullable=False)
    new_stock = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.String(255), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('admins.id', ondelete='SET NULL'), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    product = db.relationship('Product', backref=db.backref('inventory_logs_list', lazy='dynamic', cascade="all, delete-orphan"))
    admin = db.relationship('Admin', lazy='joined')

class OrderTimeline(db.Model):
    __tablename__ = 'order_timeline'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    status = db.Column(db.String(50), nullable=False)
    message = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


