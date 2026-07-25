from functools import wraps
from flask import session, flash, redirect, url_for, request
from models import User, Admin

def login_required(f):
    """Decorator to protect customer endpoints requiring authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or User.query.get(session['user_id']) is None:
            session.pop('user_id', None)
            flash('Please log in or register to access this page.', 'warning')
            return redirect(url_for('client.login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to verify standard admin session state."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('is_admin', False) or not session.get('admin_user_id'):
            flash('Admin access required.', 'danger')
            return redirect(url_for('admin.admin_login'))
        admin = Admin.query.get(session.get('admin_user_id'))
        if not admin or not admin.is_active:
            session.clear()
            flash('Admin account inactive or deleted.', 'danger')
            return redirect(url_for('admin.admin_login'))
        return f(*args, **kwargs)
    return decorated_function

def check_permission(required_roles):
    """Decorator to assert specific role authorizations."""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            admin = Admin.query.get(session.get('admin_user_id'))
            if not admin or admin.role not in required_roles:
                flash('Unauthorized access: Insufficient privileges for this role.', 'danger')
                return redirect(url_for('admin.admin_dashboard'))
            return f(*args, **kwargs)
        return wrapper
    return decorator
