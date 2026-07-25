import os
os.environ['TESTING'] = 'true'
import unittest
from datetime import datetime, timedelta
from app import app
from extensions import db
from models import User, Category, Product, Order, Admin, AuditLog, Coupon, Offer, InventoryLog
from werkzeug.security import generate_password_hash

class GramkartAdminTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        
        self.client = app.test_client()
        
        with app.app_context():
            db.create_all()
            
            # Create a mock category
            self.cat = Category(name="Groceries", slug="groceries")
            db.session.add(self.cat)
            db.session.commit()
            
            # Create a mock product
            self.prod = Product(
                category_id=self.cat.id,
                name="Potato",
                price=30.0,
                mrp=40.0,
                unit="1 kg",
                stock_count=50,
                image_url="/static/images/placeholder.png",
                min_stock=5
            )
            db.session.add(self.prod)
            
            # Seed Super Admin
            self.admin = Admin(
                username='superadmin',
                password_hash=generate_password_hash('password123'),
                name='Super User',
                role='Super Admin',
                is_active=True
            )
            db.session.add(self.admin)
            
            # Seed Manager Admin
            self.manager = Admin(
                username='manager',
                password_hash=generate_password_hash('password123'),
                name='Manager User',
                role='Manager',
                is_active=True
            )
            db.session.add(self.manager)
            
            # Seed Support Staff Admin
            self.staff = Admin(
                username='staff',
                password_hash=generate_password_hash('password123'),
                name='Support User',
                role='Support Staff',
                is_active=True
            )
            db.session.add(self.staff)
            
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_unauthorized_dashboard_access_redirects(self):
        """Verify that accessing dashboard without session redirects to login gate."""
        response = self.client.get('/admin/dashboard')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin-gate', response.location)

    def test_admin_successful_login_gate(self):
        """Test successful authentication on hidden gateway."""
        response = self.client.post('/admin-gate', data={
            'admin_id': 'superadmin',
            'admin_password': 'password123',
            'remember': 'true'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Super Admin', response.data)
        self.assertIn(b'Dashboard Overview', response.data)

    def test_admin_failed_login_and_lockout(self):
        """Test authentication failed attempts increment and lockout."""
        # 1. Login with wrong credentials 5 times
        for i in range(5):
            self.client.post('/admin-gate', data={
                'admin_id': 'superadmin',
                'admin_password': 'wrongpassword'
            })
            
        # 6th attempt should flag lockout
        response = self.client.post('/admin-gate', data={
            'admin_id': 'superadmin',
            'admin_password': 'password123'
        })
        self.assertIn(b'Account locked due to failed logins', response.data)

    def test_product_duplication(self):
        """Verify product duplication endpoint creates duplicate copy with stock=0."""
        # Login first
        self.client.post('/admin-gate', data={
            'admin_id': 'superadmin',
            'admin_password': 'password123'
        })
        
        response = self.client.post('/admin/products/duplicate/1', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        with app.app_context():
            dup = Product.query.get(2)
            self.assertIsNotNone(dup)
            self.assertEqual(dup.name, "Copy of Potato")
            self.assertEqual(dup.stock_count, 0)
            self.assertEqual(dup.price, 30.0)

    def test_role_based_permissions(self):
        """Assert that Support Staff role cannot delete products."""
        # Login as Support Staff
        self.client.post('/admin-gate', data={
            'admin_id': 'staff',
            'admin_password': 'password123'
        })
        
        # Try to delete product ID 1
        response = self.client.post('/admin/products/delete/1', follow_redirects=True)
        self.assertIn(b'Unauthorized access: Insufficient privileges', response.data)
        
        with app.app_context():
            p = Product.query.get(1)
            self.assertIsNotNone(p) # Product should still exist

    def test_inventory_adjustment_logging(self):
        """Verify stock adjustments log records inside InventoryLog table."""
        # Login as superadmin
        self.client.post('/admin-gate', data={
            'admin_id': 'superadmin',
            'admin_password': 'password123'
        })
        
        # Adjust stock
        response = self.client.post('/admin/inventory/adjust/1', data={
            'change_qty': '15',
            'reason': 'Restock'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        with app.app_context():
            p = Product.query.get(1)
            self.assertEqual(p.stock_count, 65) # 50 + 15
            
            log = InventoryLog.query.order_by(InventoryLog.created_at.desc()).first()
            self.assertIsNotNone(log)
            self.assertEqual(log.change_qty, 15)
            self.assertEqual(log.reason, 'Restock')

    def test_reports_compilation_download(self):
        """Test downloading CSV business reports."""
        self.client.post('/admin-gate', data={
            'admin_id': 'superadmin',
            'admin_password': 'password123'
        })
        
        response = self.client.get('/admin/reports/download?type=inventory')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/csv')
        self.assertIn(b'Product ID,Product Name,Category', response.data)

if __name__ == '__main__':
    unittest.main()
