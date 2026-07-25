from flask import Blueprint, jsonify, request, session
from models import Product, Category, Order
from extensions import db

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/products', methods=['GET'])
def get_products():
    """RESTful API to retrieve catalog products with pagination, sorting, and category filters."""
    # Pagination args
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    # Filtering args
    cat_slug = request.args.get('category')
    search_q = request.args.get('q')
    
    # Sorting args
    sort_by = request.args.get('sort_by', 'name') # 'name', 'price_asc', 'price_desc'
    
    query = Product.query.filter_by(is_active=True)
    
    if cat_slug:
        cat = Category.query.filter_by(slug=cat_slug).first()
        if cat:
            query = query.filter_by(category_id=cat.id)
            
    if search_q:
        query = query.filter(Product.name.like(f"%{search_q}%"))
        
    # Sorting logic
    if sort_by == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort_by == 'price_desc':
        query = query.order_by(Product.price.desc())
    else:
        query = query.order_by(Product.name.asc())
        
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    products_list = [p.to_dict() for p in pagination.items]
    
    return jsonify({
        'products': products_list,
        'page': page,
        'per_page': per_page,
        'total_pages': pagination.pages,
        'total_items': pagination.total,
        'has_next': pagination.has_next,
        'has_prev': pagination.has_prev
    }), 200

@api_bp.route('/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Retrieve detailed product specifications."""
    product = Product.query.filter_by(id=product_id, is_active=True).first()
    if not product:
        return jsonify({'error': 'Product not found', 'code': 404}), 404
        
    return jsonify(product.to_dict()), 200

@api_bp.route('/categories', methods=['GET'])
def get_categories():
    """Retrieve active storefront category tags."""
    categories = Category.query.filter_by(is_active=True).order_by(Category.sort_order.asc()).all()
    return jsonify([c.to_dict() for c in categories]), 200

@api_bp.route('/orders/<int:order_id>', methods=['GET'])
def get_order_status(order_id):
    """Retrieve verified order tracking logs."""
    # Ensure caller is authenticated (either customer or admin)
    if 'user_id' not in session and not session.get('is_admin'):
        return jsonify({'error': 'Unauthorized', 'code': 401}), 401

    order = Order.query.get(order_id)
    if not order:
        return jsonify({'error': 'Order not found', 'code': 404}), 404

    # Enforce ownership check for customers (admins bypass this)
    if not session.get('is_admin') and order.user_id != session.get('user_id'):
        return jsonify({'error': 'Forbidden', 'code': 403}), 403

    return jsonify({
        'order_id': order.id,
        'status': order.order_status,
        'payment_status': order.payment_status,
        'total_amount': order.total_amount,
        'timeline': [{
            'status': log.status,
            'message': log.message,
            'time': log.created_at.strftime('%Y-%m-%d %H:%M:%S')
        } for log in order.timeline_logs]
    }), 200
