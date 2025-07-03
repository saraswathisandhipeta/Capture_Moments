from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'capture_moments_secret_key_2025')  # safer

# Database setup
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'users.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    bookings = db.relationship('Booking', backref='user', lazy=True)  # Backref

# Booking model
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    photographer_id = db.Column(db.String(10), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    package = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Photographer & availability data here (same as yours)
# ... [Insert photographers and availability_data dictionaries as in your original code] ...
# ... [Insert packages list here as well] ...

# Routes
@app.route('/')
def home():
    return render_template('home.html', username=session.get('username'), photographers=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['username'] = user.username
            flash('Welcome back! You have been logged in successfully.', 'success')
            return redirect(url_for('home'))
        flash('Invalid username or password. Please try again.', 'danger')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        existing_user = User.query.filter_by(username=username).first()
        existing_email = User.query.filter_by(email=email).first()
        
        if existing_user:
            flash('Username already exists! Please choose a different one.', 'warning')
        elif existing_email:
            flash('Email already registered! Please use a different email.', 'warning')
        else:
            hashed_password = generate_password_hash(password)
            new_user = User(username=username, email=email, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            flash('Account created successfully! Please login to continue.', 'success')
            return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('home'))

@app.route('/photographers')
def show_photographers():
    return render_template('photographers.html', photographers=photographers, availability_data=availability_data)

@app.route('/photographer/<photographer_id>')
def photographer_detail(photographer_id):
    photographer = next((p for p in photographers if p['id'] == photographer_id), None)
    if not photographer:
        flash('Photographer not found.', 'error')
        return redirect(url_for('show_photographers'))
    return render_template('photographer_detail.html', photographer=photographer, packages=packages)

@app.route('/book', methods=['GET', 'POST'])
def book():
    if 'user_id' not in session:
        flash('Please login to book a photographer.', 'warning')
        return redirect(url_for('login'))

    if request.method == 'POST':
        photographer_id = request.form.get('photographer_id')
        date = request.form.get('date')
        package = request.form.get('package')

        # Prevent double booking
        existing = Booking.query.filter_by(photographer_id=photographer_id, date=date).first()
        if existing:
            flash('Sorry, the photographer is already booked on this date. Please choose another.', 'danger')
            return redirect(url_for('book'))

        booking = Booking(
            user_id=session['user_id'],
            photographer_id=photographer_id,
            date=date,
            package=package
        )
        db.session.add(booking)
        db.session.commit()

        photographer = next((p for p in photographers if p['id'] == photographer_id), None)
        return render_template('confirmation.html', 
                               photographer=photographer, 
                               date=date, 
                               package=package,
                               booking_id=booking.id)

    return render_template('book.html', photographers=photographers, packages=packages)

@app.route('/pricing')
def pricing():
    return render_template('pricing.html', packages=packages)

@app.route('/gallery')
def gallery():
    return render_template('gallery.html', photographers=photographers)

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/delivery')
def delivery():
    return render_template('delivery.html')

@app.route('/api/availability/<photographer_id>')
def get_availability(photographer_id):
    all_dates = availability_data.get(photographer_id, [])
    booked_dates = [b.date for b in Booking.query.filter_by(photographer_id=photographer_id).all()]
    available = [d for d in all_dates if d not in booked_dates]
    return jsonify({
        "photographer_id": photographer_id,
        "available_dates": available
    })

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
