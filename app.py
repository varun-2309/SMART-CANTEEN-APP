"""
Smart Canteen Management System
A complete web-based solution for managing canteen operations including
menu browsing, order placement/tracking, and staff dashboard.
"""

from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import secrets
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = secrets.token_hex(16)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///canteen.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    is_staff = db.Column(db.Boolean, default=False)
    orders = db.relationship('Order', backref='customer', lazy=True)

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text)
    available = db.Column(db.Boolean, default=True)
    image_url = db.Column(db.String(200))
    preparation_time = db.Column(db.Integer, default=15)  # in minutes

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    order_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')  # pending, preparing, ready, completed, cancelled
    total_amount = db.Column(db.Float, nullable=False)
    special_instructions = db.Column(db.Text)
    estimated_time = db.Column(db.DateTime)
    items = db.relationship('OrderItem', backref='order', lazy=True, cascade='all, delete-orphan')

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Float, nullable=False)
    menu_item = db.relationship('MenuItem', backref='order_items')

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/menu')
def menu():
    categories = db.session.query(MenuItem.category).distinct().all()
    categories = [c[0] for c in categories]
    items = MenuItem.query.filter_by(available=True).all()
    return render_template('menu.html', items=items, categories=categories)

@app.route('/api/menu')
def api_menu():
    items = MenuItem.query.filter_by(available=True).all()
    return jsonify([{
        'id': item.id,
        'name': item.name,
        'category': item.category,
        'price': item.price,
        'description': item.description,
        'preparation_time': item.preparation_time
    } for item in items])

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if User.query.filter_by(username=username).first():
            return jsonify({'error': 'Username already exists'}), 400
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        
        return jsonify({'message': 'Registration successful'}), 201
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return jsonify({'message': 'Login successful', 'is_staff': user.is_staff}), 200
        
        return jsonify({'error': 'Invalid credentials'}), 401
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/place_order', methods=['POST'])
@login_required
def place_order():
    data = request.get_json()
    items = data.get('items', [])
    special_instructions = data.get('special_instructions', '')
    
    if not items:
        return jsonify({'error': 'No items in order'}), 400
    
    total_amount = 0
    max_prep_time = 0
    
    order = Order(
        user_id=current_user.id,
        special_instructions=special_instructions,
        total_amount=0  
    )
    db.session.add(order)
    db.session.flush()  
    
    for item in items:
        menu_item = MenuItem.query.get(item['id'])
        if not menu_item or not menu_item.available:
            db.session.rollback()
            return jsonify({'error': f'Item {item.get("name", "unknown")} not available'}), 400
        
        order_item = OrderItem(
            order_id=order.id,
            menu_item_id=menu_item.id,
            quantity=item['quantity'],
            price=menu_item.price
        )
        db.session.add(order_item)
        
        total_amount += menu_item.price * item['quantity']
        max_prep_time = max(max_prep_time, menu_item.preparation_time)
    
    order.total_amount = total_amount
    order.estimated_time = datetime.utcnow().replace(second=0, microsecond=0)
    order.estimated_time = order.estimated_time.replace(minute=order.estimated_time.minute + max_prep_time)
    
    db.session.commit()
    
    return jsonify({
        'message': 'Order placed successfully',
        'order_id': order.id,
        'total_amount': total_amount,
        'estimated_time': order.estimated_time.strftime('%H:%M')
    }), 201

@app.route('/my_orders')
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.order_date.desc()).all()
    return render_template('my_orders.html', orders=orders)

@app.route('/api/order/<int:order_id>')
@login_required
def get_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    if order.user_id != current_user.id and not current_user.is_staff:
        return jsonify({'error': 'Unauthorized'}), 403
    
    return jsonify({
        'id': order.id,
        'status': order.status,
        'total_amount': order.total_amount,
        'order_date': order.order_date.strftime('%Y-%m-%d %H:%M'),
        'estimated_time': order.estimated_time.strftime('%H:%M') if order.estimated_time else None,
        'items': [{
            'name': item.menu_item.name,
            'quantity': item.quantity,
            'price': item.price
        } for item in order.items]
    })

# Staff Dashboard Routes
@app.route('/staff/dashboard')
@login_required
def staff_dashboard():
    if not current_user.is_staff:
        return redirect(url_for('index'))
    
    orders = Order.query.filter(Order.status.in_(['pending', 'preparing', 'ready'])).order_by(Order.order_date).all()
    return render_template('staff_dashboard.html', orders=orders)

@app.route('/api/staff/orders')
@login_required
def api_staff_orders():
    if not current_user.is_staff:
        return jsonify({'error': 'Unauthorized'}), 403
    
    status_filter = request.args.get('status', 'all')
    
    query = Order.query
    if status_filter != 'all':
        query = query.filter_by(status=status_filter)
    
    orders = query.order_by(Order.order_date.desc()).all()
    
    return jsonify([{
        'id': order.id,
        'customer': order.customer.username,
        'status': order.status,
        'total_amount': order.total_amount,
        'order_date': order.order_date.strftime('%Y-%m-%d %H:%M'),
        'items': [{
            'name': item.menu_item.name,
            'quantity': item.quantity
        } for item in order.items],
        'special_instructions': order.special_instructions
    } for order in orders])

@app.route('/api/staff/update_order/<int:order_id>', methods=['PUT'])
@login_required
def update_order_status(order_id):
    if not current_user.is_staff:
        return jsonify({'error': 'Unauthorized'}), 403
    
    order = Order.query.get_or_404(order_id)
    data = request.get_json()
    new_status = data.get('status')
    
    valid_statuses = ['pending', 'preparing', 'ready', 'completed', 'cancelled']
    if new_status not in valid_statuses:
        return jsonify({'error': 'Invalid status'}), 400
    
    order.status = new_status
    db.session.commit()
    
    return jsonify({'message': 'Order status updated successfully', 'new_status': new_status})

@app.route('/api/staff/menu/<int:item_id>', methods=['PUT'])
@login_required
def update_menu_item(item_id):
    if not current_user.is_staff:
        return jsonify({'error': 'Unauthorized'}), 403
    
    item = MenuItem.query.get_or_404(item_id)
    data = request.get_json()
    
    if 'available' in data:
        item.available = data['available']
    if 'price' in data:
        item.price = data['price']
    if 'preparation_time' in data:
        item.preparation_time = data['preparation_time']
    
    db.session.commit()
    
    return jsonify({'message': 'Menu item updated successfully'})


def init_database():
    """Initialize database with tables and sample data"""
    with app.app_context():
        db.create_all()
        
     
        if not User.query.filter_by(username='staff').first():
            staff_user = User(
                username='staff',
                email='staff@canteen.com',
                password_hash=generate_password_hash('staff123'),
                is_staff=True
            )
            db.session.add(staff_user)
        
 
        if MenuItem.query.count() == 0:
            sample_items = [
                MenuItem(name='Veg Burger', category='Burgers', price=5.99, description='Fresh veggie patty with lettuce and tomato', preparation_time=10),
                MenuItem(name='Chicken Burger', category='Burgers', price=7.99, description='Grilled chicken with special sauce', preparation_time=15),
                MenuItem(name='Margherita Pizza', category='Pizza', price=9.99, description='Classic tomato and mozzarella', preparation_time=20),
                MenuItem(name='Pepperoni Pizza', category='Pizza', price=11.99, description='Loaded with pepperoni slices', preparation_time=20),
                MenuItem(name='Caesar Salad', category='Salads', price=6.99, description='Romaine lettuce with caesar dressing', preparation_time=5),
                MenuItem(name='Greek Salad', category='Salads', price=7.99, description='Fresh vegetables with feta cheese', preparation_time=5),
                MenuItem(name='French Fries', category='Sides', price=3.99, description='Crispy golden fries', preparation_time=7),
                MenuItem(name='Onion Rings', category='Sides', price=4.99, description='Battered and fried onion rings', preparation_time=8),
                MenuItem(name='Coke', category='Beverages', price=2.99, description='Chilled soft drink', preparation_time=1),
                MenuItem(name='Fresh Orange Juice', category='Beverages', price=4.99, description='Freshly squeezed orange juice', preparation_time=3),
                MenuItem(name='Coffee', category='Beverages', price=3.49, description='Hot brewed coffee', preparation_time=2),
                MenuItem(name='Chocolate Cake', category='Desserts', price=5.99, description='Rich chocolate layer cake', preparation_time=2),
                MenuItem(name='Ice Cream Sundae', category='Desserts', price=4.99, description='Vanilla ice cream with toppings', preparation_time=3)
            ]
            
            for item in sample_items:
                db.session.add(item)
        
        db.session.commit()
        print("✅ Database initialized successfully!")



def create_templates():
    """Create all HTML template files"""
    os.makedirs('templates', exist_ok=True)
    

    base_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Canteen Management System</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); min-height: 100vh; }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .navbar { background: rgba(255,255,255,0.95); border-radius: 10px; padding: 15px 30px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .nav-brand { font-size: 24px; font-weight: bold; color: #667eea; }
        .nav-links { display: flex; gap: 20px; }
        .nav-links a { text-decoration: none; color: #4a5568; padding: 8px 16px; border-radius: 5px; transition: all 0.3s; }
        .nav-links a:hover { background: #667eea; color: white; }
        .card { background: white; border-radius: 15px; padding: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .btn { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border: none; padding: 12px 30px; border-radius: 25px; cursor: pointer; font-size: 16px; transition: transform 0.3s; }
        .btn:hover { transform: translateY(-2px); }
        .menu-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; margin-top: 20px; }
        .menu-item { background: white; border-radius: 10px; padding: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: transform 0.3s; }
        .menu-item:hover { transform: translateY(-5px); }
        .category-filter { display: flex; gap: 10px; margin-bottom: 20px; flex-wrap: wrap; }
        .category-btn { padding: 8px 16px; border-radius: 20px; border: 2px solid #667eea; background: white; color: #667eea; cursor: pointer; transition: all 0.3s; }
        .category-btn.active { background: #667eea; color: white; }
        .status-badge { display: inline-block; padding: 4px 12px; border-radius: 15px; font-size: 12px; font-weight: bold; }
        .status-pending { background: #ffd93d; color: #333; }
        .status-preparing { background: #6bcf7f; color: white; }
        .status-ready { background: #4a90e2; color: white; }
        .status-completed { background: #9e9e9e; color: white; }
        .cart { position: fixed; bottom: 20px; right: 20px; background: white; border-radius: 50%; width: 60px; height: 60px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 20px rgba(0,0,0,0.2); cursor: pointer; }
        .cart-count { position: absolute; top: -5px; right: -5px; background: red; color: white; border-radius: 50%; width: 24px; height: 24px; display: flex; align-items: center; justify-content: center; font-size: 12px; }
    </style>
</head>
<body>
    <div class="container">
        <nav class="navbar">
            <div class="nav-brand">🍽️ Smart Canteen</div>
            <div class="nav-links">
                <a href="/">Home</a>
                <a href="/menu">Menu</a>
                <a href="/my_orders">My Orders</a>
                <a href="/staff/dashboard">Staff Dashboard</a>
                <a href="/login">Login</a>
            </div>
        </nav>
        {% block content %}{% endblock %}
    </div>
    <script>
        // Global cart management
        let cart = JSON.parse(localStorage.getItem('cart') || '[]');
        
        function updateCartDisplay() {
            const cartCount = document.querySelector('.cart-count');
            if (cartCount) {
                const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
                cartCount.textContent = totalItems;
            }
        }
        
        function addToCart(item) {
            const existingItem = cart.find(i => i.id === item.id);
            if (existingItem) {
                existingItem.quantity += 1;
            } else {
                cart.push({...item, quantity: 1});
            }
            localStorage.setItem('cart', JSON.stringify(cart));
            updateCartDisplay();
            showNotification('Item added to cart!');
        }
        
        function showNotification(message) {
            const notification = document.createElement('div');
            notification.textContent = message;
            notification.style.cssText = 'position:fixed;top:20px;right:20px;background:#667eea;color:white;padding:15px 25px;border-radius:5px;z-index:1000;';
            document.body.appendChild(notification);
            setTimeout(() => notification.remove(), 3000);
        }
    </script>
</body>
</html>"""
    
    index_template = """{% extends "base.html" %}
{% block content %}
<div class="card">
    <h1 style="color: #667eea; margin-bottom: 20px;">Welcome to Smart Canteen! 🍴</h1>
    <p style="font-size: 18px; color: #4a5568; line-height: 1.6;">Order delicious food quickly and easily. Track your orders in real-time!</p>
    <div style="margin-top: 30px; display: flex; gap: 20px;">
        <a href="/menu" class="btn" style="text-decoration: none;">Browse Menu</a>
        <a href="/login" class="btn" style="text-decoration: none; background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">Login / Register</a>
    </div>
</div>
{% endblock %}"""
    

    menu_template = """{% extends "base.html" %}
{% block content %}
<div class="card">
    <h1 style="color: #667eea; margin-bottom: 20px;">Our Menu 📋</h1>
    <div class="category-filter">
        <button class="category-btn active" onclick="filterCategory('all')">All Items</button>
        {% for category in categories %}
        <button class="category-btn" onclick="filterCategory('{{ category }}')">{{ category }}</button>
        {% endfor %}
    </div>
    <div class="menu-grid">
        {% for item in items %}
        <div class="menu-item" data-category="{{ item.category }}">
            <h3 style="color: #2d3748; margin-bottom: 10px;">{{ item.name }}</h3>
            <p style="color: #718096; font-size: 14px; margin-bottom: 10px;">{{ item.description }}</p>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 15px;">
                <span style="font-size: 20px; font-weight: bold; color: #667eea;">₹{{ "%.2f"|format(item.price) }}</span>
                <button class="btn" style="padding: 8px 20px; font-size: 14px;" onclick="addToCart({id: {{ item.id }}, name: '{{ item.name }}', price: {{ item.price }}})">Add to Cart</button>
            </div>
            <span style="font-size: 12px; color: #a0aec0;">⏱️ {{ item.preparation_time }} mins</span>
        </div>
        {% endfor %}
    </div>
</div>
<div class="cart" onclick="viewCart()">
    🛒
    <div class="cart-count">0</div>
</div>
<script>
    function filterCategory(category) {
        const items = document.querySelectorAll('.menu-item');
        const buttons = document.querySelectorAll('.category-btn');
        
        buttons.forEach(btn => btn.classList.remove('active'));
        event.target.classList.add('active');
        
        items.forEach(item => {
            if (category === 'all' || item.dataset.category === category) {
                item.style.display = 'block';
            } else {
                item.style.display = 'none';
            }
        });
    }
    
    function viewCart() {
        if (cart.length === 0) {
            alert('Your cart is empty!');
            return;
        }
        
        let cartHtml = '<h2>Your Cart</h2>';
        let total = 0;
        cart.forEach(item => {
            const subtotal = item.price * item.quantity;
            total += subtotal;
            cartHtml += '<div style="margin: 10px 0; padding: 10px; background: #f7fafc; border-radius: 5px;">';
            cartHtml += '<strong>' + item.name + '</strong> x ' + item.quantity + ' = ₹' + subtotal.toFixed(2);
            cartHtml += '</div>';
        });
        cartHtml += '<h3 style="margin-top: 20px;">Total: ₹' + total.toFixed(2) + '</h3>';
        cartHtml += '<button onclick="checkout()" class="btn" style="margin-top: 20px;">Checkout</button>';
        
        const modal = document.createElement('div');
        modal.style.cssText = 'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:white;padding:30px;border-radius:10px;box-shadow:0 10px 40px rgba(0,0,0,0.3);z-index:1000;min-width:300px;';
        modal.innerHTML = cartHtml;
        document.body.appendChild(modal);
        
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.5);z-index:999;';
        overlay.onclick = () => {
            modal.remove();
            overlay.remove();
        };
        document.body.appendChild(overlay);
    }
    
    function checkout() {
        fetch('/place_order', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({items: cart, special_instructions: ''})
        })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                alert('Error: ' + data.error);
            } else {
                alert('Order placed successfully! Order ID: ' + data.order_id);
                cart = [];
                localStorage.setItem('cart', '[]');
                updateCartDisplay();
                window.location.href = '/my_orders';
            }
        })
        .catch(error => {
            alert('Please login to place an order');
            window.location.href = '/login';
        });
    }
    
    updateCartDisplay();
</script>
{% endblock %}"""
    
    login_template = """{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 400px; margin: 50px auto;">
    <h1 style="color: #667eea; margin-bottom: 20px; text-align: center;">Login 🔐</h1>
    <form id="loginForm" style="display: flex; flex-direction: column; gap: 15px;">
        <input type="text" id="username" placeholder="Username" required style="padding: 12px; border: 1px solid #cbd5e0; border-radius: 5px; font-size: 14px;">
        <input type="password" id="password" placeholder="Password" required style="padding: 12px; border: 1px solid #cbd5e0; border-radius: 5px; font-size: 14px;">
        <button type="submit" class="btn">Login</button>
        <p style="text-align: center; color: #718096;">Don't have an account? <a href="/register" style="color: #667eea;">Register here</a></p>
    </form>
</div>
<script>
    document.getElementById('loginForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('username').value;
        const password = document.getElementById('password').value;
        
        try {
            const response = await fetch('/login', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, password})
            });
            
            const data = await response.json();
            
            if (response.ok) {
                showNotification('Login successful!');
                setTimeout(() => {
                    if (data.is_staff) {
                        window.location.href = '/staff/dashboard';
                    } else {
                        window.location.href = '/menu';
                    }
                }, 1000);
            } else {
                alert(data.error || 'Login failed');
            }
        } catch (error) {
            alert('Login error. Please try again.');
        }
    });
</script>
{% endblock %}"""
    
 
    register_template = """{% extends "base.html" %}
{% block content %}
<div class="card" style="max-width: 400px; margin: 50px auto;">
    <h1 style="color: #667eea; margin-bottom: 20px; text-align: center;">Register 📝</h1>
    <form id="registerForm" style="display: flex; flex-direction: column; gap: 15px;">
        <input type="text" id="username" placeholder="Username" required style="padding: 12px; border: 1px solid #cbd5e0; border-radius: 5px; font-size: 14px;">
        <input type="email" id="email" placeholder="Email" required style="padding: 12px; border: 1px solid #cbd5e0; border-radius: 5px; font-size: 14px;">
        <input type="password" id="password" placeholder="Password" required style="padding: 12px; border: 1px solid #cbd5e0; border-radius: 5px; font-size: 14px;">
        <input type="password" id="confirmPassword" placeholder="Confirm Password" required style="padding: 12px; border: 1px solid #cbd5e0; border-radius: 5px; font-size: 14px;">
        <button type="submit" class="btn">Register</button>
        <p style="text-align: center; color: #718096;">Already have an account? <a href="/login" style="color: #667eea;">Login here</a></p>
    </form>
</div>
<script>
    document.getElementById('registerForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        const username = document.getElementById('username').value;
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const confirmPassword = document.getElementById('confirmPassword').value;
        
        if (password !== confirmPassword) {
            alert('Passwords do not match!');
            return;
        }
        
        try {
            const response = await fetch('/register', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({username, email, password})
            });
            
            const data = await response.json();
            
            if (response.ok) {
                showNotification('Registration successful!');
                setTimeout(() => {
                    window.location.href = '/login';
                }, 1500);
            } else {
                alert(data.error || 'Registration failed');
            }
        } catch (error) {
            alert('Registration error. Please try again.');
        }
    });
</script>
{% endblock %}"""
    
    
    my_orders_template = """{% extends "base.html" %}
{% block content %}
<div class="card">
    <h1 style="color: #667eea; margin-bottom: 20px;">My Orders 📦</h1>
    {% if orders %}
        {% for order in orders %}
        <div class="card" style="margin-bottom: 15px; background: #f8f9fa;">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div style="flex: 1;">
                    <h3>Order #{{ order.id }}</h3>
                    <p style="color: #666; margin: 5px 0;">Date: {{ order.order_date.strftime('%Y-%m-%d %H:%M') }}</p>
                    <p style="color: #666; margin: 5px 0;">Total: ₹{{ "%.2f"|format(order.total_amount) }}</p>
                    {% if order.estimated_time %}
                    <p style="color: #666; margin: 5px 0;">Estimated Ready Time: {{ order.estimated_time.strftime('%H:%M') }}</p>
                    {% endif %}
                    <div style="margin: 10px 0;">
                        <strong>Items:</strong>
                        {% for item in order.items %}
                        <div>• {{ item.menu_item.name }} x{{ item.quantity }} - ₹{{ "%.2f"|format(item.price * item.quantity) }}</div>
                        {% endfor %}
                    </div>
                    {% if order.special_instructions %}
                    <p style="color: #e53e3e; font-style: italic; margin-top: 10px;">Note: {{ order.special_instructions }}</p>
                    {% endif %}
                </div>
                <div>
                    <span class="status-badge status-{{ order.status }}">{{ order.status.upper() }}</span>
                    <button onclick="refreshOrderStatus({{ order.id }})" class="btn" style="margin-top: 10px; padding: 8px 16px; font-size: 14px;">Refresh Status</button>
                </div>
            </div>
        </div>
        {% endfor %}
    {% else %}
        <div style="text-align: center; padding: 40px; color: #718096;">
            <p style="font-size: 18px; margin-bottom: 20px;">You haven't placed any orders yet!</p>
            <a href="/menu" class="btn" style="text-decoration: none;">Browse Menu</a>
        </div>
    {% endif %}
</div>
<script>
    function refreshOrderStatus(orderId) {
        fetch(`/api/order/${orderId}`)
            .then(response => response.json())
            .then(data => {
                showNotification('Order status: ' + data.status.toUpperCase());
                setTimeout(() => location.reload(), 1000);
            })
            .catch(error => {
                alert('Error fetching order status');
            });
    }
    
    // Auto-refresh every 30 seconds
    setInterval(() => {
        location.reload();
    }, 30000);
</script>
{% endblock %}"""
    

    staff_dashboard_template = """{% extends "base.html" %}
{% block content %}
<div class="card">
    <h1 style="color: #667eea; margin-bottom: 20px;">Staff Dashboard 👨‍🍳</h1>
    <div style="display: flex; gap: 10px; margin-bottom: 20px;">
        <button class="category-btn active" onclick="filterOrders('all')">All Orders</button>
        <button class="category-btn" onclick="filterOrders('pending')">Pending</button>
        <button class="category-btn" onclick="filterOrders('preparing')">Preparing</button>
        <button class="category-btn" onclick="filterOrders('ready')">Ready</button>
    </div>
    <div id="orders-container">
        {% for order in orders %}
        <div class="card" style="margin-bottom: 15px; background: #f8f9fa;">
            <div style="display: flex; justify-content: space-between; align-items: start;">
                <div>
                    <h3>Order #{{ order.id }}</h3>
                    <p style="color: #666; margin: 5px 0;">Customer: {{ order.customer.username }}</p>
                    <p style="color: #666; margin: 5px 0;">Time: {{ order.order_date.strftime('%H:%M') }}</p>
                    <div style="margin: 10px 0;">
                        {% for item in order.items %}
                        <div>• {{ item.menu_item.name }} x{{ item.quantity }}</div>
                        {% endfor %}
                    </div>
                    {% if order.special_instructions %}
                    <p style="color: #e53e3e; font-style: italic;">Note: {{ order.special_instructions }}</p>
                    {% endif %}
                </div>
                <div>
                    <span class="status-badge status-{{ order.status }}">{{ order.status.upper() }}</span>
                    <div style="margin-top: 10px;">
                        <select onchange="updateStatus({{ order.id }}, this.value)" style="padding: 5px; border-radius: 5px; border: 1px solid #cbd5e0;">
                            <option value="pending" {% if order.status == 'pending' %}selected{% endif %}>Pending</option>
                            <option value="preparing" {% if order.status == 'preparing' %}selected{% endif %}>Preparing</option>
                            <option value="ready" {% if order.status == 'ready' %}selected{% endif %}>Ready</option>
                            <option value="completed" {% if order.status == 'completed' %}selected{% endif %}>Completed</option>
                            <option value="cancelled" {% if order.status == 'cancelled' %}selected{% endif %}>Cancelled</option>
                        </select>
                    </div>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
<script>
    function updateStatus(orderId, status) {
        fetch(`/api/staff/update_order/${orderId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({status: status})
        })
        .then(response => response.json())
        .then(data => {
            showNotification('Order status updated!');
            setTimeout(() => location.reload(), 1000);
        })
        .catch(error => {
            alert('Error updating status');
        });
    }
    
    function filterOrders(status) {
        fetch(`/api/staff/orders?status=${status}`)
            .then(response => response.json())
            .then(orders => {
                location.reload();
            });
    }
    
    // Auto-refresh every 30 seconds
    setInterval(() => {
        location.reload();
    }, 30000);
</script>
{% endblock %}"""
    
    with open('templates/base.html', 'w', encoding='utf-8') as f:
        f.write(base_template)
    
    with open('templates/index.html', 'w', encoding='utf-8') as f:
        f.write(index_template)
    
    with open('templates/menu.html', 'w', encoding='utf-8') as f:
        f.write(menu_template)
    
    with open('templates/login.html', 'w', encoding='utf-8') as f:
        f.write(login_template)
    
    with open('templates/register.html', 'w', encoding='utf-8') as f:
        f.write(register_template)
    
    with open('templates/my_orders.html', 'w', encoding='utf-8') as f:
        f.write(my_orders_template)
    
    with open('templates/staff_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(staff_dashboard_template)
    
    print("✅ All templates created successfully!")

create_templates()
init_database()
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
