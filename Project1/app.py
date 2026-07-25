import os
import sqlite3
from datetime import datetime
import flask
from werkzeug.routing.exceptions import BuildError

# Monkeypatch flask.url_for globally to route legacy names to blueprints
original_url_for = flask.url_for

def custom_url_for(endpoint, *args, **values):
    mappings = {
        'admin_login_gate': 'admin_login',
        'admin.admin_login_gate': 'admin.admin_login'
    }
    endpoint = mappings.get(endpoint, endpoint)
    try:
        return original_url_for(endpoint, *args, **values)
    except BuildError:
        try:
            return original_url_for(f"client.{endpoint}", *args, **values)
        except BuildError:
            return original_url_for(f"admin.{endpoint}", *args, **values)

flask.url_for = custom_url_for

from flask import Flask, render_template, jsonify
from sqlalchemy.exc import SQLAlchemyError
from config import Config, DevelopmentConfig, ProductionConfig, TestingConfig
from extensions import db, csrf, limiter, mail, cache, migrate, socketio
from models import Coupon, Admin, SystemSetting

def init_extra_columns(app):
    """Fallback migrations ensuring all dynamic columns exist in the SQLite engine on startup."""
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite:///'):
        return
        
    db_file = db_uri[len('sqlite:///'):]
    if db_file == ':memory:':
        return
        
    if not os.path.isabs(db_file):
        db_path = os.path.join(app.instance_path, db_file)
    else:
        db_path = db_file
        
    # Ensure instance directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    con = sqlite3.connect(db_path)
    cursor = con.cursor()
    
    # Products Table Checks
    cursor.execute("PRAGMA table_info(products)")
    columns = [col[1] for col in cursor.fetchall()]
    extra_cols = {
        'subcategory': 'TEXT',
        'brand': 'TEXT',
        'sku': 'TEXT',
        'barcode': 'TEXT',
        'weight': 'TEXT',
        'min_stock': 'INTEGER DEFAULT 5',
        'max_stock': 'INTEGER DEFAULT 100',
        'specifications': 'TEXT',
        'ingredients': 'TEXT',
        'expiry_date': 'TIMESTAMP',
        'is_featured': 'BOOLEAN DEFAULT 0',
        'is_trending': 'BOOLEAN DEFAULT 0',
        'is_flash_sale': 'BOOLEAN DEFAULT 0',
        'is_best_seller': 'BOOLEAN DEFAULT 0',
        'is_recommended': 'BOOLEAN DEFAULT 0',
        'image_urls': 'TEXT'
    }
    for col, ctype in extra_cols.items():
        if col not in columns:
            cursor.execute(f"ALTER TABLE products ADD COLUMN {col} {ctype}")
            
    # Users Table Checks
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'is_blocked' not in columns:
        cursor.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT 0")
        
    # Categories Table Checks
    cursor.execute("PRAGMA table_info(categories)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'is_active' not in columns:
        cursor.execute("ALTER TABLE categories ADD COLUMN is_active BOOLEAN DEFAULT 1")
    if 'sort_order' not in columns:
        cursor.execute("ALTER TABLE categories ADD COLUMN sort_order INTEGER DEFAULT 0")
        
    # Reviews Table Checks
    cursor.execute("PRAGMA table_info(reviews)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'status' not in columns:
        cursor.execute("ALTER TABLE reviews ADD COLUMN status TEXT DEFAULT 'Approved'")
    if 'is_featured' not in columns:
        cursor.execute("ALTER TABLE reviews ADD COLUMN is_featured BOOLEAN DEFAULT 0")
    if 'is_reported' not in columns:
        cursor.execute("ALTER TABLE reviews ADD COLUMN is_reported BOOLEAN DEFAULT 0")
        
    # Coupons Table Checks
    cursor.execute("PRAGMA table_info(coupons)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'discount_type' not in columns:
        cursor.execute("ALTER TABLE coupons ADD COLUMN discount_type TEXT DEFAULT 'Flat'")
    if 'max_discount_amount' not in columns:
        cursor.execute("ALTER TABLE coupons ADD COLUMN max_discount_amount REAL DEFAULT 0.0")
    if 'customer_limit' not in columns:
        cursor.execute("ALTER TABLE coupons ADD COLUMN customer_limit INTEGER DEFAULT 1")
        
    # Orders Table Checks
    cursor.execute("PRAGMA table_info(orders)")
    columns = [col[1] for col in cursor.fetchall()]
    order_cols = {
        'delivery_slot': 'TEXT',
        'razorpay_order_id': 'TEXT',
        'razorpay_payment_id': 'TEXT',
        'razorpay_signature': 'TEXT',
        'refund_status': 'TEXT',
        'delivery_partner_id': 'INTEGER',
        'delivery_otp': 'TEXT',
        'delivery_proof_url': 'TEXT',
        'driver_latitude': 'REAL DEFAULT 25.5941',
        'driver_longitude': 'REAL DEFAULT 85.1376'
    }
    for col, ctype in order_cols.items():
        if col not in columns:
            cursor.execute(f"ALTER TABLE orders ADD COLUMN {col} {ctype}")
            
    # Addresses Table Checks
    cursor.execute("PRAGMA table_info(addresses)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'created_at' not in columns:
        cursor.execute("ALTER TABLE addresses ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        
    con.commit()
    cursor.close()
    con.close()

def create_app(config_class=None):
    """Application Factory Pattern building and configuring the Flask app instance."""
    app = Flask(__name__)
    app.jinja_env.globals['url_for'] = custom_url_for
    
    # Load configuration classes based on environment flags
    if not config_class:
        env = os.environ.get('FLASK_ENV', 'development').lower()
        is_testing = os.environ.get('TESTING', 'false').lower() == 'true'
        if is_testing or env == 'testing':
            config_class = TestingConfig
        elif env == 'production':
            config_class = ProductionConfig
        else:
            config_class = DevelopmentConfig
            
    app.config.from_object(config_class)
    
    # Initialize Sentry Error Monitoring if DSN is configured and not in testing
    sentry_dsn = app.config.get('SENTRY_DSN')
    if sentry_dsn and not app.config.get('TESTING'):
        try:
            import sentry_sdk
            from sentry_sdk.integrations.flask import FlaskIntegration
            sentry_sdk.init(
                dsn=sentry_dsn,
                integrations=[FlaskIntegration()],
                traces_sample_rate=1.0,
                profiles_sample_rate=1.0
            )
        except Exception as ex:
            app.logger.error(f"Sentry SDK initialization failed: {ex}")
    
    # Initialize Flask Extensions
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)
    cache.init_app(app)
    migrate.init_app(app, db)
    socketio.init_app(app)
    
    # Register blueprints
    from routes.client import client_bp
    from routes.admin import admin_bp
    from routes.api import api_bp
    
    app.register_blueprint(client_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    
    # Exempt Restful API Blueprint endpoints from standard CSRF verification checks
    csrf.exempt(api_bp)
    
    # Auto-inject CSRF tokens into all HTML POST forms dynamically
    @app.after_request
    def inject_csrf_token(response):
        import re
        if response.status_code == 200 and response.headers.get("Content-Type", "").startswith("text/html"):
            try:
                from flask_wtf.csrf import generate_csrf
                token = generate_csrf()
                content = response.get_data(as_text=True)
                pattern = re.compile(r'(<form\b[^>]*\bmethod=["\']?post["\']?[^>]*>)', re.IGNORECASE)
                new_content = pattern.sub(rf'\1\n<input type="hidden" name="csrf_token" value="{token}">', content)
                response.set_data(new_content)
            except Exception as ex:
                app.logger.error(f"CSRF injection exception: {ex}")
        return response
    
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        if app.config.get('ENV') == 'production' or not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        
        csp_policy = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.tailwindcss.com https://cdnjs.cloudflare.com https://unpkg.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdnjs.cloudflare.com https://unpkg.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: https://images.unsplash.com https://*.tile.openstreetmap.org https://unpkg.com; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none';"
        )
        response.headers['Content-Security-Policy'] = csp_policy
        return response

    # Configure custom log rotation
    from utils.helpers import setup_logger
    setup_logger(app)
    
    # --- Global Exception Handlers ---
    
    @app.errorhandler(400)
    def bad_request_error(e):
        app.logger.warning(f"400 Bad Request: {e}")
        return render_template('error.html', error_title="Bad Request", error_msg="The server could not understand your request."), 400
        
    @app.errorhandler(401)
    def unauthorized_error(e):
        app.logger.warning(f"401 Unauthorized: {e}")
        return render_template('error.html', error_title="Unauthorized", error_msg="Access is denied due to invalid credentials."), 401
        
    @app.errorhandler(403)
    def forbidden_error(e):
        app.logger.warning(f"403 Forbidden: {e}")
        return render_template('error.html', error_title="Forbidden", error_msg="You do not have permission to view this resource."), 403
        
    @app.errorhandler(404)
    def page_not_found(e):
        app.logger.info(f"404 Not Found: {request.url if 'request' in globals() else ''}")
        return render_template('error.html', error_title="Page Not Found", error_msg="The resource you are looking for has been moved or deleted."), 404
        
    @app.errorhandler(500)
    def internal_server_error(e):
        app.logger.error(f"500 Internal Server Error: {e}")
        return render_template('error.html', error_title="Server Error", error_msg="An unexpected error occurred. Please try again later."), 500
        
    @app.errorhandler(SQLAlchemyError)
    def database_error(e):
        db.session.rollback()
        app.logger.error(f"Database Query/Session error: {e}")
        return render_template('error.html', error_title="Database Error", error_msg="A secure database transaction rollback was performed."), 500

    # --- Metrics & Health Status Endpoint ---
    
    @app.route('/health', methods=['GET'])
    @limiter.exempt
    def health_check():
        """Publicly accessible health monitor checking SQL availability and file systems."""
        db_ok = True
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception as e:
            db_ok = False
            app.logger.error(f"Health check SQL failure: {e}")
            
        return jsonify({
            'status': 'healthy' if db_ok else 'unhealthy',
            'database': 'connected' if db_ok else 'disconnected',
            'timestamp': datetime.utcnow().isoformat()
        }), 200 if db_ok else 500

    # --- Database Seeding and Setup ---
    
    with app.app_context():
        # Only run startup ALTER scripts if NOT running in testing memory DB mode
        if not app.config.get('TESTING'):
            try:
                init_extra_columns(app)
            except Exception as e:
                app.logger.error(f"Alter columns check failed or columns already present: {e}")
                
        db.create_all()
        
        # Seed default coupons
        from werkzeug.security import generate_password_hash
        if not Coupon.query.filter_by(code='GRAM50').first():
            db.session.add(Coupon(
                code='GRAM50',
                discount_amount=50.0,
                min_order_amount=299.0,
                usage_limit=10,
                times_used=0,
                expiry_date=datetime(2028, 12, 31),
                is_active=True
            ))
        if not Coupon.query.filter_by(code='WELCOME100').first():
            db.session.add(Coupon(
                code='WELCOME100',
                discount_amount=100.0,
                min_order_amount=499.0,
                usage_limit=10,
                times_used=0,
                expiry_date=datetime(2028, 12, 31),
                is_active=True
            ))
            
        # Clean up old default admins so they get re-seeded with latest password
        old_admin = Admin.query.filter_by(username='admin').first()
        if old_admin:
            db.session.delete(old_admin)
            db.session.commit()

        old_gramkart_admin = Admin.query.filter_by(username='gramkart_admin').first()
        if old_gramkart_admin:
            db.session.delete(old_gramkart_admin)
            db.session.commit()

        # Seed default super admin
        admin_username = os.environ.get('ADMIN_USERNAME', os.environ.get('ADMIN_ID', 'gramkart_admin'))
        admin_password = os.environ.get('ADMIN_PASSWORD', 'GramkartSecure2026')
        print(f"DEBUG STARTUP: admin_username='{admin_username}', admin_password='{admin_password}'")
        if not Admin.query.filter_by(username=admin_username).first():
            db.session.add(Admin(
                username=admin_username,
                password_hash=generate_password_hash(admin_password),
                name='Super Admin User',
                role='Super Admin',
                is_active=True
            ))
            
        # Seed default system settings
        default_settings = {
            'site_name': 'GramKart',
            'site_logo': '/static/images/hero.png',
            'contact_email': 'contact@gramkart.com',
            'contact_phone': '+91 98765 43210',
            'maintenance_mode': 'False',
            'currency': 'INR',
            'language': 'en'
        }
        for k, v in default_settings.items():
            if not SystemSetting.query.filter_by(key=k).first():
                db.session.add(SystemSetting(key=k, value=v))
                
        db.session.commit()

    return app

# Instantiate primary app object for standard launchers
app = create_app()

# --- SocketIO Event Listeners ---

from flask_socketio import join_room, leave_room
from flask import current_app
from models import Order

@socketio.on('join')
def on_join(data):
    room = data.get('room')
    if room:
        join_room(room)
        current_app.logger.info(f"Socket Client joined room: {room}")

@socketio.on('driver_location_update')
def handle_driver_location(data):
    order_id = data.get('order_id')
    lat = data.get('latitude')
    lng = data.get('longitude')
    
    with app.app_context():
        order = Order.query.get(order_id)
        if order:
            order.driver_latitude = lat
            order.driver_longitude = lng
            db.session.commit()
            
            socketio.emit('driver_moved', {
                'order_id': order_id,
                'latitude': lat,
                'longitude': lng
            }, room=f'user_{order.user_id}')

if __name__ == '__main__':
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
