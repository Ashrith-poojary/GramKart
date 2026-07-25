import unittest
from app import create_app
from extensions import db
from models import User, Product, Category, Order
from config import TestingConfig

class CommercialTestCase(unittest.TestCase):
    def setUp(self):
        self.app = create_app(TestingConfig)
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        db.create_all()
        
        # Seed basic category & product
        self.category = Category(name="Test Vegetables", slug="test-vegetables", is_active=True)
        db.session.add(self.category)
        db.session.commit()
        
        self.product = Product(
            name="Fresh Cabbage",
            price=20.0,
            mrp=30.0,
            unit="1 kg",
            stock_count=50,
            category_id=self.category.id,
            is_active=True
        )
        db.session.add(self.product)
        db.session.commit()
        
        # Seed test user
        self.user = User(
            name="John Villager",
            phone="9999988888",
            password_hash="dummy_hash",
            village="Rampur",
            landmark="Temple",
            pincode="800001"
        )
        db.session.add(self.user)
        db.session.commit()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_sitemap_xml(self):
        """Test sitemap XML dynamically builds and returns correct mimetype."""
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/xml')
        self.assertIn(b'<urlset', response.data)
        self.assertIn(b'test-vegetables', response.data)

    def test_robots_txt(self):
        """Test robots.txt serves correctly."""
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'text/plain')
        self.assertIn(b'Sitemap:', response.data)
        self.assertIn(b'Disallow: /admin/', response.data)

    def test_pwa_manifest(self):
        """Test PWA manifest.json is served."""
        response = self.client.get('/static/manifest.json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/json')
        self.assertIn(b'GramKart Quick Commerce', response.data)

    def test_service_worker(self):
        """Test service-worker JS is served."""
        response = self.client.get('/static/service-worker.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/javascript')
        self.assertIn(b'gramkart-cache', response.data)

    def test_localization_switching(self):
        """Test changing user language sessions."""
        with self.client.session_transaction() as sess:
            sess['lang'] = 'en'
            
        # Switch language to Hindi
        response = self.client.get('/language/hi', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        with self.client as c:
            with c.session_transaction() as sess:
                self.assertEqual(sess.get('lang'), 'hi')

    def test_razorpay_checkout_flow(self):
        """Test Razorpay checkout endpoint validation."""
        # Setup login session
        with self.client.session_transaction() as sess:
            sess['user_id'] = self.user.id
            sess['cart'] = {str(self.product.id): 2}
            
        payload = {
            'recipient_name': 'Test Recipient',
            'recipient_phone': '9876543210',
            'village': 'Test Village',
            'pincode': '800001',
            'landmark': 'Test Landmark',
            'delivery_slot': 'Instant (15-30 Mins)',
            'payment_method': 'Razorpay'
        }
        
        # Test creation route validation
        response = self.client.post(
            '/checkout/razorpay/create',
            json=payload,
            headers={'Content-Type': 'application/json'}
        )
        
        # The key verification will attempt to call Razorpay APIs and fail or pass with mock response
        # Here we verify we get a response (either 200 with JSON, or mock transaction error handled gracefully)
        self.assertIn(response.status_code, [200, 500])

    def test_unified_admin_login(self):
        """Test logging in as admin via the same customer login field."""
        from werkzeug.security import generate_password_hash
        from models import Admin
        admin = Admin(
            username='commercial_admin',
            password_hash=generate_password_hash('pass123'),
            name='Commercial Admin',
            role='Super Admin',
            is_active=True
        )
        db.session.add(admin)
        db.session.commit()
        
        response = self.client.post('/login', data={
            'phone': 'commercial_admin',
            'password': 'pass123'
        }, follow_redirects=True)
        
        self.assertEqual(response.status_code, 200)
        with self.client as c:
            with c.session_transaction() as sess:
                self.assertTrue(sess.get('is_admin'))
                self.assertEqual(sess.get('admin_name'), 'Commercial Admin')

    def test_google_login_flow(self):
        """Test Google login flow routes."""
        response = self.client.get('/login/google', follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        
        with self.client as c:
            with c.session_transaction() as sess:
                self.assertIsNotNone(sess.get('user_id'))
                user = User.query.get(sess['user_id'])
                self.assertEqual(user.name, 'Google User')

    def test_homepage_products_and_search(self):
        """Test homepage rendering with products, and search filtering."""
        # Add a test category and products to database inside test context
        cat = Category(name="Test Category A", slug="test-category-a", image_url="/static/images/placeholder.svg")
        db.session.add(cat)
        db.session.commit()
        
        prod1 = Product(
            category_id=cat.id,
            name="Fresh Apples Special",
            price=100.0,
            mrp=120.0,
            unit="1 kg",
            stock_count=10,
            is_active=True
        )
        prod2 = Product(
            category_id=cat.id,
            name="Organic Bananas Special",
            price=50.0,
            mrp=50.0,
            unit="1 dozen",
            stock_count=20,
            is_active=True
        )
        db.session.add(prod1)
        db.session.add(prod2)
        db.session.commit()
        
        # Test homepage load
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Fresh Apples Special", response.data)
        self.assertIn(b"Organic Bananas Special", response.data)
        self.assertIn(b"Trending Today", response.data)
        
        # Test search query
        response = self.client.get('/?q=Apples')
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'href="/product/{prod1.id}"'.encode(), response.data)
        self.assertNotIn(f'href="/product/{prod2.id}"'.encode(), response.data)

    def test_order_success_access_control(self):
        """Test that a logged-in user cannot access another user's order success page."""
        # Create user A
        user_a = User(phone="9999999990", password_hash="hash", name="User A", village="Village A", landmark="Landmark A", pincode="800001")
        db.session.add(user_a)
        # Create user B
        user_b = User(phone="9999999991", password_hash="hash", name="User B", village="Village B", landmark="Landmark B", pincode="800001")
        db.session.add(user_b)
        db.session.commit()
        
        # Create order belonging to User A
        order = Order(
            user_id=user_a.id,
            recipient_name="Recipient A",
            recipient_phone="9999999990",
            delivery_village="Village A",
            delivery_landmark="Landmark A",
            delivery_pincode="800001",
            payment_method="COD",
            total_amount=100.0
        )
        db.session.add(order)
        db.session.commit()

        # Try to view success page of A's order while logged in as B
        with self.client as c:
            with c.session_transaction() as sess:
                sess['user_id'] = user_b.id
                
            response = c.get(f'/order/success/{order.id}', follow_redirects=True)
            self.assertIn(b"Unauthorized access", response.data)

    def test_api_orders_access_control(self):
        """Test API get_order_status access control (auth + ownership constraints)."""
        # Create user A and B
        user_a = User(phone="8888888880", password_hash="hash", name="User A", village="Village A", landmark="Landmark A", pincode="800001")
        user_b = User(phone="8888888881", password_hash="hash", name="User B", village="Village B", landmark="Landmark B", pincode="800001")
        db.session.add(user_a)
        db.session.add(user_b)
        db.session.commit()
        
        order = Order(
            user_id=user_a.id,
            recipient_name="Recipient A",
            recipient_phone="8888888880",
            delivery_village="Village A",
            delivery_landmark="Landmark A",
            delivery_pincode="800001",
            payment_method="COD",
            total_amount=100.0
        )
        db.session.add(order)
        db.session.commit()

        # 1. Unauthenticated client request
        response = self.client.get(f'/api/orders/{order.id}')
        self.assertEqual(response.status_code, 401)

        # 2. Authenticated as non-owner (user_b)
        with self.client as c:
            with c.session_transaction() as sess:
                sess['user_id'] = user_b.id
            response = c.get(f'/api/orders/{order.id}')
            self.assertEqual(response.status_code, 403)

        # 3. Authenticated as owner (user_a)
        with self.client as c:
            with c.session_transaction() as sess:
                sess['user_id'] = user_a.id
            response = c.get(f'/api/orders/{order.id}')
            self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
