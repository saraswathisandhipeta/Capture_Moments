from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import logging
import boto3
import uuid
import os
from botocore.exceptions import ClientError

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_very_secure_secret_key_here')

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize AWS services
dynamodb = boto3.resource('dynamodb', region_name='ap-south-1')
sns = boto3.client('sns', region_name='ap-south-1')

# Define DynamoDB tables
users_table = dynamodb.Table('photography_users')
bookings_table = dynamodb.Table('photography_bookings')

# SNS Topic ARN for notifications
sns_topic_arn = os.environ.get('SNS_TOPIC_ARN', 'arn:aws:sns:ap-south-1:605134430972:photographernotifications')

def send_booking_notification(booking_data):
    """
    Send an SNS notification about a new booking
    """
    try:
        message = f"New booking received!\n\n" \
                 f"Event: {booking_data['event_type']}\n" \
                 f"Client: {booking_data['name']}\n" \
                 f"Photographer: {booking_data['photographer']}\n" \
                 f"Date: {booking_data['start_date']} to {booking_data['end_date']}\n" \
                 f"Contact: {booking_data['email']}, {booking_data['phone']}"
        
        # Send to the topic (admin notification)
        sns.publish(
            TopicArn=sns_topic_arn,
            Message=message,
            Subject="New Photography Booking"
        )
        
        # Send directly to the customer
        sns.publish(
            PhoneNumber=booking_data['phone'],  # Make sure this is in E.164 format
            Message=f"Thank you for your booking with Capture Moments! Your {booking_data['event_type']} " \
                   f"photography session with {booking_data['photographer']} is confirmed for {booking_data['start_date']}."
        )
        
        logger.info(f"Notification sent for booking: {booking_data['booking_id']}")
        return True
    except ClientError as e:
        logger.error(f"Failed to send notification: {e}")
        return False

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
        
        try:
            # Query the users table
            response = users_table.get_item(Key={'username': username})
            user = response.get('Item')
            
            if user and check_password_hash(user['password'], password):
                session['username'] = username
                session['fullname'] = user['fullname']
                flash('Login successful!', 'success')
                
                # Check if there's a next parameter in the query string for redirection
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                return redirect(url_for('home'))
            flash('Invalid username or password', 'error')
        
        except ClientError as e:
            logger.error(f"Database error during login: {e}")
            flash('An error occurred during login. Please try again.', 'error')
    
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
        
        try:
            # Check if username already exists
            response = users_table.get_item(Key={'username': username})
            if 'Item' in response:
                flash('Username already exists!', 'error')
                return redirect(url_for('signup'))
            
            # Create new user in DynamoDB
            users_table.put_item(
                Item={
                    'username': username,
                    'password': generate_password_hash(password),
                    'fullname': fullname,
                    'email': email,
                    'created_at': datetime.now().isoformat()
                }
            )
            
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        
        except ClientError as e:
            logger.error(f"Database error during signup: {e}")
            flash('An error occurred during registration. Please try again.', 'error')
    
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    session.pop('fullname', None)
    flash('You have been logged out', 'info')
    return redirect(url_for('index'))

@app.route('/home')
def home():
    if 'username' not in session:
        return redirect(url_for('login', next=request.path))
    return render_template('home.html', username=session['username'])

@app.route('/about')
def about():
    return render_template('about.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/photographers')
def photographers():
    return render_template('photographers.html')

@app.route('/booking', methods=['GET', 'POST'])
def booking():
    if 'username' not in session:
        flash('Please login to book a photographer', 'error')
        return redirect(url_for('login', next=request.path))
    
    event_type = request.args.get('event', '')
    
    if request.method == 'POST':
        try:
            # Retrieve user data
            response = users_table.get_item(Key={'username': session['username']})
            user = response.get('Item', {})
            
            # Validate required fields
            required_fields = ['event_type', 'photographer', 'start_date', 'end_date', 'name', 'email', 'phone', 'package', 'payment']
            missing_fields = [field for field in required_fields if not request.form.get(field)]
            
            if missing_fields:
                flash(f'Please fill all required fields: {", ".join(missing_fields)}', 'error')
                return redirect(url_for('booking', event=event_type))
            
            # Generate a unique booking ID
            booking_id = str(uuid.uuid4())
            
            # Process booking form
            booking_data = {
                'booking_id': booking_id,
                'username': session['username'],
                'user': session['fullname'],
                'user_email': user.get('email', ''),
                'name': request.form['name'],
                'email': request.form['email'],
                'phone': request.form['phone'],
                'event_type': request.form['event_type'],
                'photographer': request.form['photographer'],
                'start_date': request.form['start_date'],
                'end_date': request.form['end_date'],
                'package': request.form['package'],
                'payment_method': request.form['payment'],
                'notes': request.form.get('notes', ''),
                'booking_date': datetime.now().isoformat(),
                'status': 'Confirmed'
            }
            
            # Save to DynamoDB
            bookings_table.put_item(Item=booking_data)
            logger.info(f"Booking created with ID: {booking_id}")
            
            # Send notification
            send_booking_notification(booking_data)
            
            # Store booking ID in session for the success page
            session['last_booking_id'] = booking_id
            
            return redirect(url_for('success'))
        
        except Exception as e:
            logger.error(f"Error in booking form: {str(e)}")
            flash(f'An error occurred: {str(e)}', 'error')
            return redirect(url_for('booking', event=event_type))
    
    return render_template('booking.html', event_type=event_type)

@app.route('/success',methods=['GET', 'POST'])
def success():
    if 'username' not in session:
        return redirect(url_for('login'))
    
    # Just render the success template without passing booking details
    return render_template('success.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

# @app.route('/my_bookings')
# def my_bookings():
#     if 'username' not in session:
#         flash('Please login to view your bookings', 'error')
#         return redirect(url_for('login', next=request.path))
    
#     try:
#         # Query bookings for this user
#         response = bookings_table.scan(
#             FilterExpression=boto3.dynamodb.conditions.Attr('username').eq(session['username'])
#         )
#         user_bookings = response.get('Items', [])
        
#         return render_template('my_bookings.html', bookings=user_bookings)
#     except ClientError as e:
#         logger.error(f"Error retrieving bookings: {e}")
#         flash('Failed to retrieve your bookings', 'error')
#         return redirect(url_for('home'))

# @app.errorhandler(404)
# def page_not_found(e):
#     return render_template('404.html'), 404



if __name__ == '__main__':
    # Create tables if they don't exist
    
    # Run the Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)