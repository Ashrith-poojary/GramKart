import os
os.environ['TESTING'] = 'true'
import unittest
from app import app
from extensions import db
from models import User, Category, Product, Order, OrderItem

class GramkartTestCase(unittest.TestCase):
    def setUp(self):
        # Configure app for testing
        app.config['TESTING'] = True
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        app.config['WTF_CSRF_ENABLED'] = False
        
        self.client = app.test_client()
        
        # Initialize database
        with app.app_context():
            db.create_all()
            
            # Seed test category
            cat = Category(name="Test Category", slug="test-category")
            db.session.add(cat)
            db.session.commit()
            
            # Seed test product
            prod = Product(
                category_id=cat.id,
                name="Test Product",
                description="Testing product item",
                price=100.0,
                mrp=120.0,
                unit="1 kg",
                stock_count=10,
                image_url="/static/images/placeholder.png"
            )
            db.session.add(prod)
            db.session.commit()

    def tearDown(self):
        with app.app_context():
            db.session.remove()
            db.drop_all()

    def test_homepage(self):
        """Test homepage loading."""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Gramkart', response.data)

    def test_customer_registration_and_login(self):
        """Test customer registration, login and session persistence."""
        # 1. Register a user
        reg_response = self.client.post('/register', data={
            'name': 'Test Customer',
            'phone': '9876543210',
            'password': 'password123',
            'village': 'Rampur',
            'landmark': 'Near Well',
            'pincode': '123456'
        }, follow_redirects=True)
        self.assertEqual(reg_response.status_code, 200)
        self.assertIn(b'Account created successfully!', reg_response.data)

        # Logout user first
        self.client.get('/logout')

        # 2. Login user
        login_response = self.client.post('/login', data={
            'phone': '9876543210',
            'password': 'password123'
        }, follow_redirects=True)
        self.assertEqual(login_response.status_code, 200)
        self.assertIn(b'Logged in successfully!', login_response.data)

    def test_cart_operations(self):
        """Test adding item to cart and updating quantity."""
        # Add product to cart
        response = self.client.post('/cart/add/1')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['cart_count'], 1)

        # Update cart quantity
        response_update = self.client.post('/cart/update/1', json={'quantity': 5})
        self.assertEqual(response_update.status_code, 200)
        self.assertTrue(response_update.get_json()['success'])

    def test_checkout_and_order_flow(self):
        """Test checkout submission, order record creation, and stock deduction."""
        # Register and login customer
        self.client.post('/register', data={
            'name': 'Test Customer',
            'phone': '9876543210',
            'password': 'password123',
            'village': 'Rampur',
            'landmark': 'Near Well',
            'pincode': '123456'
        }, follow_redirects=True)

        # Add item to cart
        self.client.post('/cart/add/1')

        # Submit checkout
        response = self.client.post('/checkout', data={
            'recipient_name': 'Test Customer',
            'recipient_phone': '9876543210',
            'village': 'Rampur',
            'landmark': 'Near Well',
            'pincode': '123456',
            'payment_method': 'COD'
        }, follow_redirects=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Order placed successfully!', response.data)

        # Verify stock count deducted
        with app.app_context():
            product = Product.query.get(1)
            self.assertEqual(product.stock_count, 9) # 10 - 1 = 9

            order = Order.query.first()
            self.assertIsNotNone(order)
            self.assertEqual(order.recipient_name, 'Test Customer')
            self.assertEqual(order.payment_method, 'COD')
            self.assertEqual(order.order_status, 'Placed')

    def test_admin_login(self):
        """Test separate admin authentication."""
        # Login admin with mock credentials matching defaults
        response = self.client.post('/admin/login', data={
            'admin_id': 'gramkart_admin',
            'admin_password': 'GramkartSecure2026'
        }, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Dashboard Overview', response.data)

if __name__ == '__main__':
    unittest.main()
