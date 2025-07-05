from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import logging
import uuid
import re

DEVELOPMENT_MODE = False  # Set to True for local testing without AWS

app = Flask(__name__)
app.secret_key = 'dev'  # You can replace this with a random secure string

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AWS Configuration
if not DEVELOPMENT_MODE:
    import boto3
    from botocore.exceptions import NoCredentialsError

    try:
        aws_session = boto3.Session()
        credentials = aws_session.get_credentials()
        if credentials is None:
            raise NoCredentialsError()

        dynamodb = aws_session.resource('dynamodb', region_name='us-east-1')
        sns = aws_session.client('sns', region_name='us-east-1')
        users_table = dynamodb.Table('photography_users')
        bookings_table = dynamodb.Table('photography_bookings')
        photographers_table = dynamodb.Table('photographers')
        sns_topic_arn = "arn:aws:sns:us-east-1:842676002305:Booking-Alert"  # Replace with real ARN
    except NoCredentialsError:
        logger.error("AWS credentials not found.")
        exit()
else:
    logger.warning("Running in development mode without AWS")
    users_table = bookings_table = photographers_table = sns = sns_topic_arn = None


@app.route('/')
def index():
    if 'username' in session:
        return redirect(url_for('home'))
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'username' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if DEVELOPMENT_MODE:
            if username == "testuser" and password == "1234":
                session['username'] = username
                session['fullname'] = "Test User"
                flash("Login successful (mock)", "success")
                return redirect(url_for('home'))
            flash("Mock login failed", "error")
        else:
            try:
                user = users_table.get_item(Key={'username': username}).get('Item')
                if user and check_password_hash(user['password'], password):
                    session['username'] = username
                    session['fullname'] = user['fullname']
                    flash("Login successful", "success")
                    return redirect(url_for('home'))
                flash("Invalid username or password", "error")
            except Exception as e:
                logger.error(f"Login error: {e}")
                flash("Login failed. Please try again.", "error")

    return render_template('login.html')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if 'username' in session:
        return redirect(url_for('home'))

    if request.method == 'POST':
        fullname = request.form['fullname']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Invalid email format", "error")
            return redirect(url_for('signup'))

        if DEVELOPMENT_MODE:
            flash("Mock signup successful. Please login.", "success")
            return redirect(url_for('login'))
        else:
            try:
                response = users_table.get_item(Key={'username': username})
                if 'Item' in response:
                    flash("Username already exists.", "error")
                    return redirect(url_for('signup'))

                users_table.put_item(Item={
                    'username': username,
                    'password': generate_password_hash(password),
                    'fullname': fullname,
                    'email': email,
                    'created_at': datetime.utcnow().isoformat()
                })

                flash("Signup successful. Please login.", "success")
                return redirect(url_for('login'))
            except Exception as e:
                logger.error(f"Signup error: {e}")
                flash("Signup failed. Try again.", "error")

    return render_template('signup.html')


@app.route('/logout')
def logout():
    session.clear()
    flash("Logged out successfully", "info")
    return redirect(url_for('index'))


@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login'))
    return render_template('home.html', username=session['username'])


@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/services')
def services():
    return render_template('services.html')


@app.route('/photographers')
def photographers():
    if DEVELOPMENT_MODE:
        photographers = [
            {'photographer_id': 'p1', 'name': 'John Doe', 'availability': ['2025-07-10-10AM', '2025-07-12-4PM']},
            {'photographer_id': 'p2', 'name': 'Jane Smith', 'availability': ['2025-07-15-9AM', '2025-07-18-6PM']}
        ]
    else:
        try:
            photographers = photographers_table.scan().get('Items', [])
        except Exception as e:
            logger.error(f"Photographer fetch failed: {e}")
            flash("Could not load photographers", "error")
            return redirect(url_for('home'))

    availability_data = {
        p['photographer_id']: p.get('availability', []) for p in photographers
    }
    return render_template('photographers.html', photographers=photographers, availability_data=availability_data)


@app.route('/booking', methods=['GET', 'POST'])
def booking():
    if 'username' not in session:
        flash('Please login to book a photographer', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        event_type = request.form.get('event_type')
        photographer = request.form.get('photographer')
        package = request.form.get('package')
        payment = request.form.get('payment')
        notes = request.form.get('notes', '')

        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash("Invalid email", "error")
            return redirect(url_for('booking'))

        if not re.match(r"^[6-9]\d{9}$", phone):
            flash("Invalid phone number", "error")
            return redirect(url_for('booking'))

        booking_id = f"{photographer}-{uuid.uuid4()}"

        if DEVELOPMENT_MODE:
            logger.info(f"Mock booking for {name} | Event: {event_type}")
            flash("Mock booking successful", "success")
            return redirect(url_for('success'))
        else:
            try:
                bookings_table.put_item(Item={
                    'booking_id': booking_id,
                    'username': session['username'],
                    'name': name,
                    'email': email,
                    'phone': phone,
                    'event_type': event_type,
                    'photographer': photographer,
                    'package': package,
                    'date_slot': f"{start_date} to {end_date}",
                    'notes': notes,
                    'payment': payment,
                    'timestamp': datetime.utcnow().isoformat()
                })

                sns.publish(
                    TopicArn=sns_topic_arn,
                    Subject="New Photography Booking",
                    Message=(
                        f"New Booking Confirmed\n\n"
                        f"Name: {name}\n"
                        f"Email: {email}\n"
                        f"Phone: {phone}\n"
                        f"Event: {event_type}\n"
                        f"Photographer: {photographer}\n"
                        f"Package: {package}\n"
                        f"Dates: {start_date} to {end_date}\n"
                        f"Payment: {payment}\n"
                        f"Notes: {notes}"
                    )
                )

                flash("Booking successful and notification sent", "success")
                return redirect(url_for('success'))

            except Exception as e:
                logger.error(f"Booking error: {e}")
                flash("Booking failed. Try again", "error")
                return redirect(url_for('booking'))

    return render_template('booking.html')


@app.route('/success')
def success():
    return render_template('success.html')


@app.route('/contact')
def contact():
    return render_template('contact.html')


if __name__ == '__main__':
    print("Flask server running at http://0.0.0.0:5000")
    app.run(debug=True, host='0.0.0.0', port=5000)
