import os
from app import db, Category, Product, app

def seed_database():
    print("Clearing and initializing database tables...")
    db.drop_all()
    db.create_all()

    print("Seeding categories...")
    categories = [
        Category(
            name="Dairy, Bread & Eggs",
            slug="dairy-bread-eggs",
            image_url="https://images.unsplash.com/photo-1550583724-b2692b85b150?w=200&auto=format&fit=crop&q=80"
        ),
        Category(
            name="Groceries & Staples",
            slug="groceries-staples",
            image_url="https://images.unsplash.com/photo-1542838132-92c53300491e?w=200&auto=format&fit=crop&q=80"
        ),
        Category(
            name="Fresh Veggies & Fruits",
            slug="fresh-veggies-fruits",
            image_url="https://images.unsplash.com/photo-1540420773420-3366772f4999?w=200&auto=format&fit=crop&q=80"
        ),
        Category(
            name="Snacks & Beverages",
            slug="snacks-beverages",
            image_url="https://images.unsplash.com/photo-1534080391025-a87e899080e8?w=200&auto=format&fit=crop&q=80"
        ),
        Category(
            name="Household & Cleaning",
            slug="household-cleaning",
            image_url="https://images.unsplash.com/photo-1583947215259-38e31be8751f?w=200&auto=format&fit=crop&q=80"
        ),
        Category(
            name="Personal Care",
            slug="personal-care",
            image_url="https://images.unsplash.com/photo-1607006342445-360f141b0ebd?w=200&auto=format&fit=crop&q=80"
        )
    ]

    for cat in categories:
        db.session.add(cat)
    db.session.commit()

    # Query categories to map product category IDs
    cat_map = {c.slug: c.id for c in Category.query.all()}

    print("Seeding products...")
    products = [
        # Dairy, Bread & Eggs
        Product(
            category_id=cat_map["dairy-bread-eggs"],
            name="Fresh Cow Milk (ताज़ा दूध)",
            description="Pure, fresh and pasteurized cow milk from local dairy farms.",
            price=62.0,
            mrp=65.0,
            unit="1 Litre",
            stock_count=45,
            image_url="https://images.unsplash.com/photo-1563636619-e9143da7973b?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["dairy-bread-eggs"],
            name="Fresh Farm Eggs (अंडे)",
            description="Rich in protein, farm fresh brown eggs.",
            price=72.0,
            mrp=84.0,
            unit="1 Dozen",
            stock_count=35,
            image_url="https://images.unsplash.com/photo-1506976785307-8732e854ad03?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["dairy-bread-eggs"],
            name="Amul Pasteurized Butter",
            description="Deliciously salted pasteurized butter.",
            price=54.0,
            mrp=56.0,
            unit="100g pack",
            stock_count=50,
            image_url="https://images.unsplash.com/photo-1589985270826-4b7bb135bc9d?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["dairy-bread-eggs"],
            name="Sliced White Bread (ब्रेड)",
            description="Soft and fresh sliced sandwich bread.",
            price=28.0,
            mrp=30.0,
            unit="400g pack",
            stock_count=20,
            image_url="https://images.unsplash.com/photo-1509440159596-0249088772ff?w=400&auto=format&fit=crop&q=80"
        ),

        # Groceries & Staples
        Product(
            category_id=cat_map["groceries-staples"],
            name="Basmati Rice (Premium)",
            description="Long grain basmati rice, perfect for biryani and daily meals.",
            price=75.0,
            mrp=90.0,
            unit="1 kg",
            stock_count=50,
            image_url="https://images.unsplash.com/photo-1586201375761-83865001e31c?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["groceries-staples"],
            name="Mustard Oil (Kachi Ghani)",
            description="Pure cold pressed mustard oil for cooking.",
            price=165.0,
            mrp=190.0,
            unit="1 Litre",
            stock_count=30,
            image_url="https://images.unsplash.com/photo-1608797178974-15b35a61d121?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["groceries-staples"],
            name="Chana Dal",
            description="High protein, clean and unpolished chana dal.",
            price=85.0,
            mrp=100.0,
            unit="1 kg",
            stock_count=40,
            image_url="https://images.unsplash.com/photo-1590080875515-8a3a8dc5735e?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["groceries-staples"],
            name="Tata Salt (Iodized)",
            description="Desh ka namak, vacuum evaporated iodized salt.",
            price=24.0,
            mrp=28.0,
            unit="1 kg",
            stock_count=100,
            image_url="https://images.unsplash.com/photo-1599819811279-d5ad9cccf838?w=400&auto=format&fit=crop&q=80"
        ),

        # Fresh Veggies & Fruits
        Product(
            category_id=cat_map["fresh-veggies-fruits"],
            name="Fresh Potatoes (आलू)",
            description="Farm fresh high-quality local potatoes.",
            price=28.0,
            mrp=35.0,
            unit="1 kg",
            stock_count=80,
            image_url="https://images.unsplash.com/photo-1518977676601-b53f82aba655?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["fresh-veggies-fruits"],
            name="Fresh Onions (प्याज़)",
            description="Dry and well-cured red onions from Nashik.",
            price=38.0,
            mrp=45.0,
            unit="1 kg",
            stock_count=60,
            image_url="https://images.unsplash.com/photo-1618519764620-7403abdbfee9?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["fresh-veggies-fruits"],
            name="Ripe Bananas (केला)",
            description="Sweet and nutritious yellow bananas.",
            price=45.0,
            mrp=60.0,
            unit="1 Dozen",
            stock_count=15,
            image_url="https://images.unsplash.com/photo-1571771894821-ce9b6c11b08e?w=400&auto=format&fit=crop&q=80"
        ),

        # Snacks & Beverages
        Product(
            category_id=cat_map["snacks-beverages"],
            name="Britannia Marie Gold",
            description="Crisp tea-time biscuit with goodness of wheat.",
            price=30.0,
            mrp=30.0,
            unit="250g pack",
            stock_count=70,
            image_url="https://images.unsplash.com/photo-1558961363-fa8fdf82db35?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["snacks-beverages"],
            name="Red Label Tea",
            description="Brooke Bond Red Label strong tea leaves.",
            price=140.0,
            mrp=155.0,
            unit="250g pack",
            stock_count=35,
            image_url="https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=400&auto=format&fit=crop&q=80"
        ),

        # Household & Cleaning
        Product(
            category_id=cat_map["household-cleaning"],
            name="Vim Liquid Gel",
            description="Power of 100 lemons for grease removal.",
            price=55.0,
            mrp=60.0,
            unit="250ml bottle",
            stock_count=4,
            image_url="https://images.unsplash.com/photo-1563453392212-326f5e854473?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["household-cleaning"],
            name="Surf Excel Easy Wash",
            description="Stain removal powder for laundry.",
            price=125.0,
            mrp=140.0,
            unit="500g pack",
            stock_count=25,
            image_url="https://images.unsplash.com/photo-1583947215259-38e31be8751f?w=400&auto=format&fit=crop&q=80"
        ),

        # Personal Care
        Product(
            category_id=cat_map["personal-care"],
            name="Dettol Bath Soap",
            description="Classic germ protection bar soap.",
            price=45.0,
            mrp=50.0,
            unit="125g bar",
            stock_count=90,
            image_url="https://images.unsplash.com/photo-1607006342445-360f141b0ebd?w=400&auto=format&fit=crop&q=80"
        ),
        Product(
            category_id=cat_map["personal-care"],
            name="Colgate Strong Teeth",
            description="Iodized calcium toothpaste for clean gums.",
            price=60.0,
            mrp=65.0,
            unit="150g tube",
            stock_count=55,
            image_url="https://images.unsplash.com/photo-1559599151-28668fc3147f?w=400&auto=format&fit=crop&q=80"
        )
    ]

    for prod in products:
        db.session.add(prod)
    db.session.commit()
    print("Database seeded successfully with categories and products!")

if __name__ == "__main__":
    with app.app_context():
        seed_database()
