"""
Flask REST API for Metro Ticket Booking System
-----------------------------------------------
Main application file with all API endpoints

FEATURES:
- User registration and login
- Ticket booking, viewing, cancellation
- Wallet and MetroCard management
- Feedback and support tickets
- Admin operations (user management, stations, announcements)
- Support staff operations
- Monthly passes
"""

from flask import Flask, request, jsonify, session, redirect, send_file, send_from_directory
from flask_cors import CORS
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
import logging
import math
import random
import io
import os
import json
import base64

import qrcode
import psutil

import db
from models import (User, Admin, SupportStaff, Ticket, Feedback,
                    SupportTicket, MetroCard, MonthlyPass,
                    Role, SupportTicketStatus)
from utils import hash_password, verify_password, format_date, format_datetime
from ds import MetroDataStore, Queue, StationInfo

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'ljuni@metro'  # Production secret key

# Enable CORS for frontend integration
CORS(app, 
     supports_credentials=True,
     origins=["http://localhost:5000", "http://127.0.0.1:5000"],
     allow_headers=["Content-Type"],
     expose_headers=["Content-Type"])


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize datastore
datastore = MetroDataStore.get_instance()

# Booking queue — uses custom Queue (DSA) to track recent bookings in FIFO order
booking_queue = Queue()
MAX_QUEUE_SIZE = 50  # Keep only the 50 most recent bookings in memory

# Feature LL: Server startup time tracking
import time as _time_mod
_server_start_time = _time_mod.time()


# ============================================================================
# Feature LL: /api/health — System Health Endpoint
# ============================================================================
@app.route('/api/health', methods=['GET'])
def api_health():
    """Live system health check — used by admin health monitor panel."""
    # DB ping
    db_ok = False
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1')
        cursor.fetchone()
        cursor.close()
        conn.close()
        db_ok = True
    except Exception:
        pass

    # Uptime
    elapsed = _time_mod.time() - _server_start_time
    hours   = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    uptime_str = f"{hours}h {minutes}m" if hours else f"{minutes}m"

    # System stats (psutil is already imported)
    try:
        cpu_pct = psutil.cpu_percent(interval=None)
        mem     = psutil.virtual_memory()
        mem_pct = mem.percent
    except Exception:
        cpu_pct = 0
        mem_pct = 0

    return jsonify({
        'status':  'ok' if db_ok else 'degraded',
        'db_ok':   db_ok,
        'uptime':  uptime_str,
        'version': '1.0.0',
        'cpu':     cpu_pct,
        'mem':     mem_pct,
    }), 200


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_current_user() -> Optional[Dict[str, Any]]:
    """Get currently logged-in user from session (returns dict for backward compatibility)"""
    username = session.get('username')
    if username:
        return db.get_user_by_username(username)
    return None


def get_current_user_object():
    """
    Get currently logged-in user as a proper model object (User/Admin/SupportStaff).
    Uses OOP classes from models.py for business logic.
    Returns None if not logged in or user not found.
    """
    username = session.get('username')
    if not username:
        return None
    user_data = db.get_user_by_username(username)
    if not user_data:
        return None
    role = user_data.get('role', Role.USER)
    if role == Role.ADMIN:
        return Admin(user_data['username'], user_data['password'])
    elif role == Role.SUPPORT_STAFF:
        return SupportStaff(user_data['username'], user_data['password'])
    else:
        return User(user_data['username'], user_data['password'],
                    float(user_data.get('walletBalance', 0.0)))


def require_login(func):
    """Decorator to require login for protected routes"""
    def wrapper(*args, **kwargs):
        if 'username' not in session:
            return jsonify({'success': False, 'error': 'Not logged in'}), 401
        return func(*args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


def require_role(required_role: str):
    """Decorator to require specific role"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({'success': False, 'error': 'Not logged in'}), 401
            if user['role'] != required_role:
                return jsonify({'success': False, 'error': 'Insufficient permissions'}), 403
            return func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        return wrapper
    return decorator


# ============================================================================
# AUTHENTICATION ROUTES
# ============================================================================

@app.route('/api/register', methods=['POST'])
def api_register():
    """
    Register a new user
    
    Request JSON:
        {
            "username": "string",
            "password": "string",
            "role": "USER" (optional, default)
        }
    
    Returns:
        {"success": true, "message": "User registered successfully"}
    """
    try:
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        email = data.get('email', '').strip() or None
        role = data.get('role', Role.USER)
        
        # Validation
        if not username or len(username) < 3 or len(username) > 12:
            return jsonify({'success': False, 'error': 'Username must be 3–12 characters'}), 400
        
        import re
        if not re.match(r'^[a-zA-Z0-9@_$]+$', username):
            return jsonify({'success': False, 'error': 'Username can only contain letters, numbers, @, _ and $'}), 400
        
        # Password is already SHA-256 hashed by frontend (64 hex chars)
        if not password or len(password) != 64:
            return jsonify({'success': False, 'error': 'Invalid password format'}), 400
        
        # Email validation (optional but validate format if provided)
        if email:
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
                return jsonify({'success': False, 'error': 'Invalid email format'}), 400
        
        if role not in [Role.USER, Role.ADMIN, Role.SUPPORT_STAFF]:
            role = Role.USER
        
        # Check if username exists
        if db.username_exists(username):
            return jsonify({'success': False, 'error': 'Username already exists'}), 400
        
        # Password is already hashed by frontend, store directly
        initial_balance = 0.0
        
        if db.insert_user(username, password, initial_balance, role, email):
            # Create metro card for new user
            db.insert_metro_card(username, 0.0, False, 50.0)
            
            # Create model object and add to datastore (OOP integration)
            if role == Role.ADMIN:
                user_obj = Admin(username, password)
            elif role == Role.SUPPORT_STAFF:
                user_obj = SupportStaff(username, password)
            else:
                user_obj = User(username, password, initial_balance)
            datastore.add_user(user_obj)
            
            logger.info(f"New user registered: {username} (Role: {role})")
            return jsonify({
                'success': True,
                'message': 'User registered successfully',
                'username': username,
                'role': role
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Failed to create user'}), 500
        
    except Exception as e:
        logger.error(f"Registration error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/check-username/<username>', methods=['GET'])
def api_check_username(username):
    """
    Check if a username is available (for real-time register form validation)
    Returns: {"available": true/false}
    """
    try:
        username = username.strip()
        import re
        if len(username) < 3:
            return jsonify({'available': False, 'reason': 'Too short'}), 200
        if not re.match(r'^[a-zA-Z0-9@_$]+$', username):
            return jsonify({'available': False, 'reason': 'Invalid characters'}), 200
        
        exists = db.username_exists(username)
        return jsonify({
            'available': not exists,
            'reason': 'Username already taken' if exists else 'Available'
        }), 200
    except Exception as e:
        return jsonify({'available': False, 'reason': 'Check failed'}), 500


@app.route('/api/login', methods=['POST'])
def api_login():
    """
    User login
    
    Request JSON:
        {
            "username": "string",
            "password": "string"
        }
    
    Returns:
        {"success": true, "user": {...}, "message": "Login successful"}
    """
    try:
        session.clear()
        data = request.json
        username = data.get('username', '').strip()
        password = data.get('password', '')
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password required'}), 400
        
        # Rate limit check
        ip = request.remote_addr or 'unknown'
        is_blocked, remaining = _check_rate_limit(ip)
        if is_blocked:
            return jsonify({
                'success': False, 
                'error': f'Too many login attempts. Try again in {remaining} seconds.',
                'rate_limited': True,
                'retry_after': remaining
            }), 429
        
        # Get user from database
        user = db.get_user_by_username(username)
        
        if not user:
            _record_failed_attempt(ip)
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        # Verify password (frontend sends SHA-256 hash directly)
        if password != user['password']:
            _record_failed_attempt(ip)
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        # Success — clear rate limit tracking
        _clear_attempts(ip)
        
        # Set session
        session['username'] = username
        session['role'] = user['role']
        
        # Track last login — save previous login for display, then update
        previous_login = None
        try:
            conn = db.get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT last_login FROM users WHERE username = %s", (username,))
            row = cursor.fetchone()
            if row and row.get('last_login'):
                previous_login = row['last_login'].strftime('%Y-%m-%d %H:%M:%S')
            cursor.execute("UPDATE users SET last_login = NOW() WHERE username = %s", (username,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception:
            pass  # Non-critical — don't block login if this fails
        
        logger.info(f"User logged in: {username}")
        
        # Remove password from response
        user_data = {
            'username': user['username'],
            'walletBalance': user['walletBalance'],
            'role': user['role']
        }
        
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'user': user_data,
            'previous_login': previous_login
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




@app.route('/api/logout', methods=['POST'])
def api_logout():
    """Logout current user - Bulletproof Version"""
    # 1. Capture username for logs before clearing (optional)
    username = session.get('username', 'Unknown')
    
    # 2. Aggressively Clear Session
    session.clear() 
    
    # 3. Log it
    logger.info(f"User logged out: {username}")
    
    # 4. Return success even if they were already logged out
    response = jsonify({'success': True, 'message': 'Logged out successfully'})
    
    # 5. Force Cookie Deletion (The Fix for 'Stuck' sessions)
    response.delete_cookie('session')
    return response, 200

@app.route('/api/me', methods=['GET'])
@require_login
def api_get_current_user():
    """Get current logged-in user details with profile summary data"""
    user = get_current_user()
    if user:
        # Fetch extra profile data: memberSince, totalTrips
        member_since = 'January 2026'
        total_trips = 0
        try:
            conn = db.get_db_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            # Get earliest booking date as "Member Since"
            cursor.execute(
                "SELECT MIN(bookingDate) as first_booking, COUNT(*) as trip_count "
                "FROM tickets WHERE username = %s AND cancelled = FALSE",
                (user['username'],)
            )
            row = cursor.fetchone()
            if row and row.get('first_booking'):
                fb = row['first_booking']
                if hasattr(fb, 'strftime'):
                    member_since = fb.strftime('%B %Y')
                else:
                    member_since = str(fb)[:7]  # 'YYYY-MM'
            total_trips = int(row.get('trip_count', 0)) if row else 0
            cursor.close()
            conn.close()
        except Exception as e:
            logger.warning(f"Profile extra data fetch error: {e}")

        return jsonify({
            'success': True,
            'user': {
                'username': user['username'],
                'walletBalance': float(user['walletBalance']),
                'role': user['role'],
                'loyaltyPoints': user.get('loyaltyPoints', 0),
                'memberSince': member_since,
                'totalTrips': total_trips,
            }
        }), 200
    else:
        return jsonify({'success': False, 'error': 'User not found'}), 404
# ============================================================================
# USER ROUTES (Wallet, Profile)
# ============================================================================

# Note: /api/user/analytics is defined later with full monthly_spending, favorite_routes, daily_trips data



@app.route('/api/user/wallet/recharge', methods=['POST'])
@require_login
def api_recharge_wallet():
    try:
        data = request.json
        # 1. Ensure amount is a float
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Amount must be positive'}), 400
        
        user = get_current_user()
        
        # 2. CRITICAL FIX: Force walletBalance to float to prevent Decimal/Float conflicts
        current_balance = float(user['walletBalance']) 
        new_balance = current_balance + amount
        
        # 3. Wallet cap check
        if new_balance > 10000:
            max_allowed = 10000 - current_balance
            return jsonify({
                'success': False, 
                'error': f'Wallet can only carry ₹10,000. You can add up to ₹{max_allowed:.0f}'
            }), 400
        
        # 3. Perform the update
        if db.update_user_wallet_balance(user['username'], new_balance):
            
            # 4. Save to History (Fail-safe: inside its own try/except)
            try:
                conn = db.get_db_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO wallet_history (username, amount, type, description) VALUES (%s, %s, 'CREDIT', 'Wallet Recharge')",
                    (user['username'], amount)
                )
                conn.commit()
                conn.close()
            except Exception as log_error:
                logger.warning(f"History Save Warning: {log_error}")

            return jsonify({
                'success': True,
                'message': f'Wallet recharged with Rs. {amount:.2f}',
                'newBalance': new_balance
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Database update failed'}), 500
        
    except Exception as e:
        logger.error(f"Recharge Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/user/wallet/balance', methods=['GET'])
@require_login
def api_get_wallet_balance():
    """Get current wallet balance"""
    user = get_current_user()
    return jsonify({
        'success': True,
        'balance': user['walletBalance']
    }), 200


# /api/metrocard/create is defined later in the file (see api_issue_metro_card)
@app.route('/api/user/change-password', methods=['POST'])
@require_login
def api_change_password():
    """
    Change password
    
    Request JSON:
        {
            "oldPassword": "string",
            "newPassword": "string"
        }
    """
    try:
        data = request.json
        old_password = data.get('oldPassword', '')
        new_password = data.get('newPassword', '')
        
        if not old_password or not new_password:
            return jsonify({'success': False, 'error': 'Both passwords required'}), 400
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'error': 'New password must be at least 6 characters'}), 400
        
        user = get_current_user()
        
        # Verify old password
        if not verify_password(old_password, user['password']):
            return jsonify({'success': False, 'error': 'Old password incorrect'}), 400
        
        # Check if new password is same as old
        if verify_password(new_password, user['password']):
            return jsonify({'success': False, 'error': 'New password must be different'}), 400
        
        # Update password
        new_hash = hash_password(new_password)
        if db.update_user_password(user['username'], new_hash):
            return jsonify({
                'success': True,
                'message': 'Password changed successfully'
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to update password'}), 500
        
    except Exception as e:
        logger.error(f"Password change error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500




# ============================================================================
# FEATURE 1 & 4: SMART FARE CALCULATOR (Update this existing function)
# ============================================================================
def calculate_dynamic_fare(source, destination, passengers, travel_hour=None):
    """Calculate fare, distance, AND time with Peak Hour logic.
    
    Args:
        travel_hour: If provided, use this hour (0-23) for peak detection
                     instead of the current time. This allows fair pricing
                     for advance bookings based on when the user will travel.
    """
    # 1. Get coordinates
    loc1 = db.get_station_location(source)
    loc2 = db.get_station_location(destination)
    
    if not loc1 or not loc2:
        return 50.0 * passengers, 0.0, 0, False
    
    # 2. Calculate Distance (Math)
    dist = math.sqrt((loc2['x'] - loc1['x'])**2 + (loc2['y'] - loc1['y'])**2) * 100
    
    # 3. Calculate Estimated Time (Assuming 30km/h avg speed + 2 mins per station)
    time_minutes = int((dist / 30) * 60) + 5 
    
    # 4. Base Calculation
    base_rate = 5.0
    base_cost = 10.0 + (dist * base_rate)
    
    # 5. PEAK HOUR LOGIC — uses travel_hour if provided, else current time
    check_hour = travel_hour if travel_hour is not None else datetime.now().hour
    is_peak = False
    
    # Peak hours: 8–10:59 AM and 5–6:59 PM (i.e. 8-11 AM, 5-7 PM labels)
    if (8 <= check_hour < 11) or (17 <= check_hour < 19):
        base_cost *= 1.25  # 25% Surge pricing
        is_peak = True
        
    # Rounding
    single_fare = max(10, round(base_cost / 5) * 5)
    total_fare = single_fare * passengers
    
    return total_fare, round(dist, 1), time_minutes, is_peak

# Update the API to send this new data to frontend
@app.route('/api/tickets/calculate-fare', methods=['POST'])
def api_calculate_fare_details():
    try:
        data = request.json
        source = data.get('source', '').lower().strip()
        destination = data.get('destination', '').lower().strip()
        passengers = int(data.get('passengers', 1))
        travel_date_str = data.get('travelDate', '')
        travel_time_str = data.get('travelTime', '')  # e.g. "09:00" or "now"
        
        if not source or not destination:
            return jsonify({'success': False, 'error': 'Stations required'}), 400
        
        # Determine the travel hour for peak pricing
        travel_hour = None  # None = use current time (default)
        
        if travel_time_str and travel_time_str != 'now':
            # User selected a specific travel time
            try:
                travel_hour = int(travel_time_str.split(':')[0])
            except (ValueError, IndexError):
                travel_hour = None
        elif travel_date_str:
            # If travel date is in the future but no time selected, default off-peak
            try:
                travel_date = datetime.strptime(travel_date_str, '%Y-%m-%d').date()
                if travel_date > date.today():
                    travel_hour = 14  # Default to 2 PM (off-peak) for future dates
            except ValueError:
                pass
            
        # Calculate fare using travel hour
        fare, distance, time, is_peak = calculate_dynamic_fare(
            source, destination, passengers, travel_hour=travel_hour
        )
        
        return jsonify({
            'success': True,
            'fare': fare,
            'distance': distance,
            'time': time,
            'is_peak': is_peak,
            'passengers': passengers,
            'travel_hour': travel_hour if travel_hour is not None else datetime.now().hour
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# FEATURE 2: PDF TICKET DOWNLOAD (New Endpoint)
# ============================================================================
@app.route('/api/tickets/<int:ticket_id>/pdf', methods=['GET'])
def generate_ticket_pdf(ticket_id):
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Auth required'}), 401
        
    try:
        ticket = db.get_ticket_by_id(ticket_id)
        if not ticket or ticket['username'] != username:
            return jsonify({'success': False, 'message': 'Invalid ticket'}), 404

        # Create PDF in memory
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        
        # Design the PDF Receipt
        c.setFont("Helvetica-Bold", 24)
        c.drawString(200, 750, "METRO TICKET")
        
        c.setFont("Helvetica", 12)
        c.drawString(50, 700, f"Ticket ID: #{ticket_id}")
        c.drawString(50, 680, f"Date: {ticket['travelDate']}")
        c.drawString(50, 660, f"Passenger: {username}")
        
        c.line(50, 640, 550, 640)
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 600, f"From: {ticket['source'].upper()}")
        c.drawString(50, 570, f"To:   {ticket['destination'].upper()}")
        
        c.setFont("Helvetica", 12)
        c.drawString(50, 530, f"Passengers: {ticket['passengers']}")
        c.drawString(50, 510, f"Status: {'CANCELLED' if ticket['cancelled'] else 'CONFIRMED'}")
        
        c.setFont("Helvetica-Bold", 18)
        c.drawString(400, 530, f"Total: Rs. {ticket['fare']}")
        
        c.save()
        buffer.seek(0)
        
        # Convert to base64 to send to frontend
        pdf_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'pdf_file': f"data:application/pdf;base64,{pdf_base64}",
            'filename': f"ticket_{ticket_id}.pdf"
        })
    except Exception as e:
        logger.error(f"PDF Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500



@app.route('/api/tickets/book', methods=['POST'])
@require_login
def api_book_ticket():
    # --- Promo code definitions (server-side truth) ---
    PROMO_CODES = {
        'METRO10': {'type': 'percent', 'value': 10, 'label': '10% Off'},
        'FIRST50': {'type': 'flat', 'value': 50, 'label': '₹50 Off'},
        'SAVE20': {'type': 'percent', 'value': 20, 'label': '20% Off'},
    }
    
    try:
        data = request.json
        source = data.get('source', '').lower().strip()
        destination = data.get('destination', '').lower().strip()
        passengers = int(data.get('passengers', 1))
        travel_date_str = data.get('travelDate', '')
        
        # New booking fields
        ticket_class = data.get('ticketClass', 'standard').lower().strip()
        coach_preference = data.get('coachPreference', 'general').lower().strip()
        payment_method = data.get('paymentMethod', 'wallet').lower().strip()
        promo_code = data.get('promoCode', '').upper().strip()
        
        # 1. Validation
        if not source or not destination:
            return jsonify({'success': False, 'error': 'Source and destination required'}), 400
        
        if source == destination:
            return jsonify({'success': False, 'error': 'Source and destination must be different'}), 400
        
        if passengers < 1 or passengers > 6:
            return jsonify({'success': False, 'error': 'Passengers must be between 1 and 6'}), 400
        
        if ticket_class not in ('standard', 'business'):
            ticket_class = 'standard'
        if coach_preference not in ('general', 'ladies', 'senior_citizen'):
            coach_preference = 'general'
        if payment_method not in ('wallet', 'metrocard'):
            payment_method = 'wallet'
        
        # 2. Parse travel date
        try:
            travel_date = datetime.strptime(travel_date_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({'success': False, 'error': 'Invalid date format (use YYYY-MM-DD)'}), 400
        
        if travel_date < date.today():
            return jsonify({'success': False, 'error': 'Travel date must be in the future'}), 400
        
        # ---------------------------------------------------------
        # 3. Calculate fare using travel time (not booking time)
        # ---------------------------------------------------------
        travel_time_str = data.get('travelTime', '')
        travel_hour = None
        
        if travel_time_str and travel_time_str != 'now':
            try:
                travel_hour = int(travel_time_str.split(':')[0])
            except (ValueError, IndexError):
                travel_hour = None
            
            # Reject past times when booking for today
            if travel_hour is not None and travel_date == date.today():
                current_hour = datetime.now().hour
                if travel_hour < current_hour:
                    return jsonify({
                        'success': False, 
                        'error': f'Cannot book for {travel_time_str} — that time has already passed today'
                    }), 400
                    
        elif travel_date > date.today():
            travel_hour = 14  # Default off-peak for future dates without time
        
        fare, distance, time, is_peak = calculate_dynamic_fare(
            source, destination, passengers, travel_hour=travel_hour
        )
        
        # ---------------------------------------------------------
        # 3.2  TICKET CLASS MULTIPLIER (Business = 1.5x)
        # ---------------------------------------------------------
        class_multiplier = 1.5 if ticket_class == 'business' else 1.0
        if class_multiplier != 1.0:
            fare = round(fare * class_multiplier / 5) * 5  # Round to nearest ₹5
        
        # ---------------------------------------------------------
        # 3.3  PROMO CODE DISCOUNT
        # ---------------------------------------------------------
        promo_discount = 0.0
        promo_label = ''
        if promo_code and promo_code in PROMO_CODES:
            promo = PROMO_CODES[promo_code]
            if promo['type'] == 'percent':
                promo_discount = round(fare * promo['value'] / 100)
            else:
                promo_discount = min(promo['value'], fare)
            # Cap promo discount at 50% of fare
            promo_discount = min(promo_discount, fare * 0.5)
            fare = max(10, fare - promo_discount)  # Minimum fare ₹10
            promo_label = promo['label']
        
        # Get user details
        user = get_current_user()
        
        # ---------------------------------------------------------
        # 3.5  MONTHLY PASS CHECK — covers 1 passenger only
        # ---------------------------------------------------------
        original_fare = fare
        pass_applied = False
        pass_discount = 0.0
        matched_pass_id = None
        matched_plan_type = None
        
        try:
            conn_mp = db.get_db_connection()
            cursor_mp = conn_mp.cursor(dictionary=True)
            
            # Auto-expire old passes
            cursor_mp.execute("UPDATE monthly_passes SET status = 'expired' WHERE expiryDate < CURRENT_DATE AND status = 'active'")
            conn_mp.commit()
            
            # Find active pass covering this route (exact, reverse, or unlimited)
            cursor_mp.execute("""
                SELECT passId, source, destination, planType,
                       COALESCE(tripsUsed, 0) as tripsUsed
                FROM monthly_passes 
                WHERE username = %s AND status = 'active' AND expiryDate >= CURRENT_DATE
                AND (
                    (LOWER(source) = %s AND LOWER(destination) = %s)
                    OR (LOWER(source) = %s AND LOWER(destination) = %s)
                    OR (source = 'ALL' AND destination = 'ALL')
                )
                ORDER BY expiryDate ASC
                LIMIT 1
            """, (user['username'], source, destination, destination, source))
            
            active_pass = cursor_mp.fetchone()
            
            if active_pass:
                # Pass covers ONLY 1 passenger (the pass holder)
                per_person_fare = fare / passengers if passengers > 0 else fare
                pass_discount = per_person_fare  # 1 passenger free
                fare = fare - pass_discount      # remaining passengers pay
                pass_applied = True
                matched_pass_id = active_pass['passId']
                matched_plan_type = active_pass['planType']
                
                # Increment trip usage counter
                cursor_mp.execute(
                    "UPDATE monthly_passes SET tripsUsed = tripsUsed + 1 WHERE passId = %s",
                    (active_pass['passId'],)
                )
                conn_mp.commit()
                
                logger.info(f"🎫 Monthly pass #{active_pass['passId']} applied for {user['username']}: "
                           f"discount ₹{pass_discount:.2f}, final fare ₹{fare:.2f} "
                           f"({passengers} passengers, 1 covered by pass)")
            
            cursor_mp.close()
            conn_mp.close()
        except Exception as mp_err:
            logger.error(f"Monthly pass check error (non-fatal): {mp_err}")
            # Don't fail booking if pass check fails — just charge normal fare
        
        # 4. Payment — Wallet or MetroCard
        new_balance = user['walletBalance']  # track wallet balance regardless
        
        if payment_method == 'metrocard':
            card = db.get_metro_card_by_username(user['username'])
            if not card:
                return jsonify({'success': False, 'error': 'You do not have a Metro Card. Please create one first.'}), 400
            card_balance = float(card['balance'])
            if fare > card_balance:
                return jsonify({
                    'success': False,
                    'error': f'Insufficient Metro Card balance. Required: ₹{fare:.2f}, Available: ₹{card_balance:.2f}'
                }), 400
            # Deduct from metro card
            new_card_balance = card_balance - fare
            db.update_metro_card(card['cardNumber'], new_card_balance, card['autoRechargeEnabled'], card['minBalanceThreshold'])
        else:
            # Default: Wallet payment
            if fare > user['walletBalance']:
                return jsonify({
                    'success': False,
                    'error': f'Insufficient wallet balance. Required: ₹{fare:.2f}, Available: ₹{user["walletBalance"]:.2f}'
                }), 400
            new_balance = user['walletBalance'] - fare
            if not db.update_user_wallet_balance(user['username'], new_balance):
                return jsonify({'success': False, 'error': 'Failed to update wallet balance'}), 500
        
        # 6. Insert ticket (with travel time, class, coach, payment method)
        travel_time_val = data.get('travelTime', 'now')
        ticket_id = db.insert_ticket(
            user['username'],
            source,
            destination,
            passengers,
            fare,
            travel_date,
            distance,
            False,
            travel_time_val,
            ticket_class,
            coach_preference,
            payment_method
        )
        if ticket_id > 0:
            # --- NEW: AWARD LOYALTY POINTS (1 Point per Rs 2 spent) ---
            points_earned = int(fare / 2)
            try:
                conn = db.get_db_connection()
                cursor = conn.cursor()
                # Update User Points
                cursor.execute("UPDATE users SET loyaltyPoints = loyaltyPoints + %s WHERE username = %s", (points_earned, user['username']))
                # Send Notification
                if pass_applied:
                    msg = f"🎫 Monthly Pass trip! Saved ₹{pass_discount:.0f} on this booking. You earned {points_earned} Green Points."
                else:
                    msg = f"Booking confirmed! You earned {points_earned} Green Points."
                cursor.execute("INSERT INTO notifications (username, message) VALUES (%s, %s)", (user['username'], msg))
                conn.commit()
                conn.close()
            except Exception as e:
                logger.error(f"Loyalty Error: {e}") # Don't fail booking if loyalty fails
            # -----------------------------------------------------------# Don't fail booking if loyalty fails
            
            # --- AUTO-RECHARGE: Trigger if enabled and balance is low ---
            auto_recharged = 0
            try:
                card = db.get_metro_card_by_username(user['username'])
                if card and (card['autoRechargeEnabled'] == 1 or card['autoRechargeEnabled'] is True):
                    threshold = float(card.get('minBalanceThreshold', 50))
                    if new_balance < threshold:
                        auto_amount = 200.0
                        new_balance += auto_amount
                        db.update_user_wallet_balance(user['username'], new_balance)
                        # Update metro card balance too
                        db.update_metro_card(card['cardNumber'], card['balance'], 1, threshold)
                        auto_recharged = auto_amount
                        # Notify user
                        conn2 = db.get_db_connection()
                        cur2 = conn2.cursor()
                        cur2.execute("INSERT INTO notifications (username, message) VALUES (%s, %s)",
                            (user['username'], f"⚡ Auto-recharged ₹{auto_amount:.0f} — your balance was below ₹{threshold:.0f}"))
                        conn2.commit()
                        cur2.close()
                        conn2.close()
                        logger.info(f"Auto-recharge: ₹{auto_amount} added to {user['username']} (balance was ₹{new_balance - auto_amount:.2f})")
            except Exception as e:
                logger.error(f"Auto-recharge Error: {e}")
            # -----------------------------------------------------------
            
            # Enqueue booking into the live booking queue (DSA Queue usage)
            booking_record = {
                'ticketId': ticket_id,
                'username': user['username'],
                'source': source,
                'destination': destination,
                'passengers': passengers,
                'fare': fare,
                'travelDate': travel_date_str,
                'bookedAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            booking_queue.enqueue(booking_record)
            # Keep queue bounded — dequeue oldest if over capacity
            while booking_queue.size() > MAX_QUEUE_SIZE:
                booking_queue.dequeue()
            
            logger.info(f"📋 Booking queue size: {booking_queue.size()}")
            return jsonify({
                'success': True,
                'message': 'Ticket booked successfully',
                'ticket': {
                    'ticketId': ticket_id,
                    'source': source,
                    'destination': destination,
                    'passengers': passengers,
                    'fare': fare,
                    'travelDate': travel_date_str,
                    'time': time,
                    'is_peak': is_peak,
                    'ticketClass': ticket_class,
                    'coachPreference': coach_preference,
                    'paymentMethod': payment_method
                },
                'newBalance': new_balance,
                'autoRecharged': auto_recharged,
                'passApplied': pass_applied,
                'passDiscount': pass_discount,
                'originalFare': original_fare,
                'passId': matched_pass_id,
                'passPlanType': matched_plan_type,
                'promoDiscount': promo_discount,
                'promoCode': promo_code if promo_discount > 0 else '',
                'promoLabel': promo_label,
                'classMultiplier': class_multiplier
            }), 200
        else:
            # Refund if ticket insertion fails
            db.update_user_wallet_balance(user['username'], user['walletBalance'])
            return jsonify({'success': False, 'error': 'Database error: Failed to generate ticket'}), 500
        
    except Exception as e:
        logger.error(f"Ticket booking error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/tickets/my-tickets', methods=['GET'])
@require_login
def api_get_my_tickets():
    """Get all tickets for current user"""
    try:
        user = get_current_user()
        tickets = db.get_tickets_by_user(user['username'])
        
        # Format tickets for response
        formatted_tickets = []
        for ticket in tickets:
            formatted_tickets.append({
                'ticketId': ticket['ticketId'],
                'source': ticket['source'],
                'destination': ticket['destination'],
                'passengers': ticket['passengers'],
                'fare': ticket['fare'],
                'distance': ticket.get('distance', 0),
                'travelDate': format_date(ticket['travelDate']),
                'cancelled': ticket['cancelled'],
                'status': ticket.get('status', 'ACTIVE'),
                'bookingDate': format_datetime(ticket['bookingDate'])
            })
        
        return jsonify({
            'success': True,
            'tickets': formatted_tickets
        }), 200
        
    except Exception as e:
        logger.error(f"Get tickets error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tickets/cancel/<int:ticket_id>', methods=['POST'])
@require_login
def api_cancel_ticket(ticket_id):
    """
    Cancel a ticket and get refund
    
    Refund: 80% if cancelled 24+ hours before travel, else 50%
    """
    try:
        user = get_current_user()
        
        # Get ticket data from DB
        ticket_data = db.get_ticket_by_id(ticket_id)
        
        if not ticket_data:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        if ticket_data['username'] != user['username']:
            return jsonify({'success': False, 'error': 'This ticket does not belong to you'}), 403
        
        if ticket_data['cancelled']:
            return jsonify({'success': False, 'error': 'Ticket already cancelled'}), 400
        
        # Create Ticket model object for refund calculation (models.py OOP)
        ticket_obj = Ticket(
            ticket_data['username'],
            ticket_data['source'],
            ticket_data['destination'],
            ticket_data['passengers'],
            float(ticket_data['fare']),
            ticket_data['travelDate']
        )
        ticket_obj.ticket_id = ticket_data['ticketId']
        
        # Use Ticket.cancel() — calculates refund with 80%/50% logic
        refund = round(ticket_obj.cancel(), 2)
        
        # Derive the same fields the frontend expects
        travel_datetime = datetime.combine(ticket_data['travelDate'], datetime.min.time())
        time_diff = travel_datetime - datetime.now()
        hours_before = max(time_diff.total_seconds() / 3600, 0)
        
        original_fare = float(ticket_data['fare'])
        refund_rate = 0.8 if hours_before >= 24 else 0.5
        charge_reason = ('Standard cancellation (24+ hours before travel)' 
                         if hours_before >= 24 
                         else 'Late cancellation (less than 24 hours before travel)')
        cancellation_charge = round(original_fare - refund, 2)
        
        # Cancel ticket in database
        if db.cancel_ticket(ticket_id):
            # Add refund to wallet
            new_balance = user['walletBalance'] + refund
            db.update_user_wallet_balance(user['username'], new_balance)
            
            return jsonify({
                'success': True,
                'message': 'Ticket cancelled successfully',
                'originalFare': original_fare,
                'refundRate': int(refund_rate * 100),
                'cancellationCharge': cancellation_charge,
                'refund': refund,
                'chargeReason': charge_reason,
                'hoursBefore': round(hours_before, 1),
                'newBalance': new_balance
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to cancel ticket'}), 500
        
    except Exception as e:
        logger.error(f"Ticket cancellation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# RECENT ROUTES & SMART COMMUTE (Phase 1 Improvement)
# ============================================================================

@app.route('/api/tickets/recent-routes', methods=['GET'])
@require_login
def api_recent_routes():
    """Get user's top 5 most-used routes for quick re-booking"""
    try:
        user = get_current_user()
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT source, destination, 
                   COUNT(*) as tripCount,
                   MAX(travelDate) as lastUsed,
                   ROUND(AVG(fare / passengers), 0) as avgFare
            FROM tickets 
            WHERE username = %s AND cancelled = 0
            GROUP BY source, destination
            ORDER BY tripCount DESC, lastUsed DESC
            LIMIT 5
        """, (user['username'],))
        routes = cursor.fetchall()
        cursor.close()
        conn.close()
        
        formatted = []
        for r in routes:
            formatted.append({
                'source': r['source'],
                'destination': r['destination'],
                'tripCount': r['tripCount'],
                'lastUsed': format_date(r['lastUsed']) if r['lastUsed'] else '',
                'avgFare': float(r['avgFare']) if r['avgFare'] else 0
            })
        
        return jsonify({'success': True, 'routes': formatted}), 200
    except Exception as e:
        logger.error(f"Recent routes error: {e}")
        return jsonify({'success': True, 'routes': []}), 200


@app.route('/api/commute/next-departure', methods=['GET'])
@require_login
def api_next_departure():
    """Get user's most frequent route with current fare & peak status for smart commute widget"""
    try:
        user = get_current_user()
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Find the user's #1 most-used route
        cursor.execute("""
            SELECT source, destination, COUNT(*) as tripCount
            FROM tickets 
            WHERE username = %s AND cancelled = 0
            GROUP BY source, destination
            ORDER BY tripCount DESC
            LIMIT 1
        """, (user['username'],))
        top_route = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not top_route:
            return jsonify({'success': True, 'hasRoute': False}), 200
        
        # Calculate current fare for this route
        current_hour = datetime.now().hour
        is_peak = (8 <= current_hour < 11) or (17 <= current_hour < 19)
        fare, distance, time_mins, _ = calculate_dynamic_fare(
            top_route['source'], top_route['destination'], 1
        )
        
        return jsonify({
            'success': True,
            'hasRoute': True,
            'source': top_route['source'],
            'destination': top_route['destination'],
            'tripCount': top_route['tripCount'],
            'fare': fare,
            'distance': distance,
            'time': time_mins,
            'isPeak': is_peak,
            'currentHour': current_hour
        }), 200
    except Exception as e:
        logger.error(f"Next departure error: {e}")
        return jsonify({'success': True, 'hasRoute': False}), 200


# ============================================================================
# FEEDBACK ROUTES
# ============================================================================

@app.route('/api/feedback/submit', methods=['POST'])
@require_login
def api_submit_feedback():
    """
    Submit feedback or complaint
    
    Request JSON:
        {
            "text": "string",
            "type": "feedback" or "complaint"
        }
    """
    try:
        data = request.json
        text = data.get('text', '').strip()
        feedback_type = data.get('type', 'feedback')
        
        if not text:
            return jsonify({'success': False, 'error': 'Feedback text required'}), 400
        
        if feedback_type not in ['feedback', 'complaint']:
            feedback_type = 'feedback'
        
        user = get_current_user()
        feedback_id = db.insert_feedback(user['username'], text, feedback_type)
        
        if feedback_id > 0:
            # Create Feedback model object and add to datastore (OOP integration)
            feedback_obj = Feedback(user['username'], text, feedback_type)
            feedback_obj.feedback_id = feedback_id
            feedback_obj.timestamp = datetime.now()
            datastore.add_feedback(feedback_obj)
            
            # If it's a complaint, create a support ticket using model
            if feedback_type == 'complaint':
                db.insert_support_ticket(feedback_id, SupportTicketStatus.OPEN)
                support_ticket_obj = SupportTicket(feedback_obj)
                datastore.add_support_ticket(support_ticket_obj)
            
            return jsonify({
                'success': True,
                'message': f'{feedback_type.capitalize()} submitted successfully',
                'feedbackId': feedback_id
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Failed to submit feedback'}), 500
        
    except Exception as e:
        logger.error(f"Feedback submission error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/feedback/my-feedbacks', methods=['GET'])
@require_login
def api_get_my_feedbacks():
    """Get all feedbacks submitted by current user"""
    try:
        user = get_current_user()
        feedbacks = db.get_feedbacks_by_username(user['username'])
        
        formatted_feedbacks = []
        for fb in feedbacks:
            formatted_feedbacks.append({
                'feedbackId': fb['feedbackId'],
                'text': fb['text'],
                'type': fb['type'],
                'timestamp': format_datetime(fb['timestamp'])
            })
        
        return jsonify({
            'success': True,
            'feedbacks': formatted_feedbacks
        }), 200
        
    except Exception as e:
        logger.error(f"Get feedbacks error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500



# ============================================================================
# METRO CARD ROUTES (Robust Integer Fix)
# ============================================================================

@app.route('/api/metrocard/details', methods=['GET'])
@require_login
def api_get_metrocard():
    """Get metro card details (Creates one if missing) — uses MetroCard model"""
    try:
        user = get_current_user()
        card = db.get_metro_card_by_username(user['username'])
        
        if not card:
            logger.info(f"Creating missing metro card for {user['username']}")
            insert_result = db.insert_metro_card(user['username'], 0.0, 0, 50.0)
            
            if not insert_result:
                return jsonify({'success': False, 'error': 'Failed to create metro card in database'}), 500
            
            card = db.get_metro_card_by_username(user['username'])
        
        if card:
            # Create MetroCard model object (OOP integration)
            card_obj = MetroCard(
                card_number=card.get('cardNumber'),
                initial_balance=float(card.get('balance', 0))
            )
            card_obj.auto_recharge_enabled = (card.get('autoRechargeEnabled', 0) == 1 
                                              or card.get('autoRechargeEnabled', 0) is True)
            card_obj.min_balance_threshold = float(card.get('minBalanceThreshold', 50))
            
            return jsonify({
                'success': True,
                'card': {
                    'cardNumber': card_obj.card_number,
                    'balance': card_obj.balance,
                    'autoRechargeEnabled': card_obj.auto_recharge_enabled, 
                    'minBalanceThreshold': card_obj.min_balance_threshold
                }
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Could not create or retrieve card'}), 500
        
    except KeyError as ke:
        logger.error(f"Missing key in card data: {ke}")
        return jsonify({'success': False, 'error': f'Missing key in card data: {ke}'}), 500
    except Exception as e:
        logger.error(f"Get metro card error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/metrocard/recharge', methods=['POST'])
@require_login
def api_recharge_metrocard():
    """Recharge metro card"""
    try:
        data = request.json
        amount = float(data.get('amount', 0))
        
        if amount <= 0:
            return jsonify({'success': False, 'error': 'Amount must be positive'}), 400
        
        user = get_current_user()
        card = db.get_metro_card_by_username(user['username'])
        
        if not card:
            return jsonify({'success': False, 'error': 'Metro card not found'}), 404
        
        new_balance = card['balance'] + amount
        
        # Preserve existing setting as Integer (1 or 0)
        current_setting = 1 if (card['autoRechargeEnabled'] == 1 or card['autoRechargeEnabled'] is True) else 0
        
        if db.update_metro_card(
            card['cardNumber'],
            new_balance,
            current_setting,
            card['minBalanceThreshold']
        ):
            return jsonify({
                'success': True,
                'message': f'Metro card recharged with Rs. {amount:.2f}',
                'newBalance': new_balance
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to recharge card'}), 500
        
    except Exception as e:
        logger.error(f"Metro card recharge error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# app.py - FIXED Auto-Recharge Route
@app.route('/api/metrocard/autorecharge', methods=['POST'])
@require_login
def toggle_auto_recharge():
    """Toggle the auto-recharge switch"""
    try:
        data = request.json
        # 1. Get the raw boolean (True/False)
        raw_enable = data.get('enable')
        
        # 2. CRITICAL FIX: Convert Boolean to Integer (1 or 0)
        # MySQL needs 1 for True, 0 for False
        enable_int = 1 if raw_enable else 0
        
        user = get_current_user()
        card = db.get_metro_card_by_username(user['username'])
        
        if not card:
            return jsonify({'success': False, 'error': 'No card found'}), 404
            
        # 3. Update Database using the INTEGER value
        if db.update_metro_card(
            card['cardNumber'], 
            card['balance'], 
            enable_int, # Passing 1 or 0
            card['minBalanceThreshold']
        ):
            status = "enabled" if enable_int else "disabled"
            return jsonify({'success': True, 'message': f'Auto-recharge {status}'})
        else:
            return jsonify({'success': False, 'error': 'Database update failed'}), 500
            
    except Exception as e:
        logger.error(f"Auto-recharge Toggle Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# MONTHLY PASS ROUTES
# ============================================================================

MONTHLY_PASS_PLANS = {
    'basic':     {'name': 'Basic Pass',     'price': 999,  'routes': 1},
    'premium':   {'name': 'Premium Pass',   'price': 1999, 'routes': 3},
    'unlimited': {'name': 'Unlimited Pass', 'price': 3499, 'routes': 0},  # 0 = all
}

MONTHLY_PASS_BENEFITS = {
    'basic': [
        'Unlimited trips on 1 fixed route',
        'Valid for 30 days from purchase',
        'Skip-the-queue at entry gates',
        'Green Metro points earned on every trip',
        '5% discount on peak hour surcharges'
    ],
    'premium': [
        'Unlimited trips on any 3 routes',
        'Valid for 30 days from purchase',
        'Priority boarding during peak hours',
        'Free parking at metro stations',
        '10% discount on peak hour surcharges',
        'Companion discount: 20% off for +1 rider',
        'Access to premium waiting lounges'
    ],
    'unlimited': [
        'Unlimited trips on ALL metro routes',
        'Valid for 30 days from purchase',
        'VIP lounge access at all major stations',
        'Free parking at all metro stations',
        'Zero peak hour surcharges',
        'Companion discount: 30% off for +1 rider',
        'Priority customer support via app',
        'Trip insurance coverage up to \u20b910,000',
        'Festival bonus: 2 free day-passes per month'
    ]
}

@app.route('/api/monthly-pass/check-coverage', methods=['GET'])
@require_login
def api_check_pass_coverage():
    """Check if user has an active monthly pass covering the given route"""
    try:
        source = request.args.get('source', '').lower().strip()
        destination = request.args.get('destination', '').lower().strip()
        
        if not source or not destination:
            return jsonify({'success': True, 'covered': False}), 200
        
        user = get_current_user()
        username = user['username']
        
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Auto-expire old passes first
        cursor.execute("UPDATE monthly_passes SET status = 'expired' WHERE expiryDate < CURRENT_DATE AND status = 'active'")
        conn.commit()
        
        # Check for active pass covering this route:
        # 1) Exact route match (source→destination)
        # 2) Reverse route match (destination→source) — pass works both ways
        # 3) Unlimited pass (ALL→ALL)
        cursor.execute("""
            SELECT passId, source, destination, expiryDate, planType,
                   COALESCE(tripsUsed, 0) as tripsUsed,
                   DATEDIFF(expiryDate, CURRENT_DATE) as daysLeft
            FROM monthly_passes 
            WHERE username = %s AND status = 'active' AND expiryDate >= CURRENT_DATE
            AND (
                (LOWER(source) = %s AND LOWER(destination) = %s)
                OR (LOWER(source) = %s AND LOWER(destination) = %s)
                OR (source = 'ALL' AND destination = 'ALL')
            )
            ORDER BY expiryDate DESC
            LIMIT 1
        """, (username, source, destination, destination, source))
        
        pass_row = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if pass_row:
            plan_name = MONTHLY_PASS_PLANS.get(pass_row['planType'], {}).get('name', 'Monthly Pass')
            return jsonify({
                'success': True,
                'covered': True,
                'passId': pass_row['passId'],
                'planType': pass_row['planType'],
                'planName': plan_name,
                'daysLeft': pass_row['daysLeft'],
                'tripsUsed': pass_row['tripsUsed'],
                'message': f'{plan_name} covers this route — 1 passenger rides FREE!'
            }), 200
        else:
            return jsonify({'success': True, 'covered': False}), 200
            
    except Exception as e:
        logger.error(f"Check pass coverage error: {e}")
        return jsonify({'success': True, 'covered': False}), 200


@app.route('/api/monthly-pass/purchase', methods=['POST'])
@require_login
def api_purchase_monthly_pass():
    """Purchase a monthly pass — deducts from wallet, creates DB record"""
    try:
        data = request.json
        plan_key = data.get('plan', '').lower()
        routes = data.get('routes', [])  # list of {source, destination}

        if plan_key not in MONTHLY_PASS_PLANS:
            return jsonify({'success': False, 'error': 'Invalid plan selected'}), 400

        plan = MONTHLY_PASS_PLANS[plan_key]
        price = plan['price']

        # Validate route count
        if plan['routes'] > 0 and len(routes) != plan['routes']:
            return jsonify({'success': False, 'error': f"{plan['name']} requires exactly {plan['routes']} route(s)"}), 400
        if plan['routes'] == 0 and len(routes) == 0:
            routes = [{'source': 'ALL', 'destination': 'ALL'}]

        user = get_current_user()
        username = user['username']

        # --- Duplicate prevention & validation ---
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Auto-expire old passes first
        cursor.execute("UPDATE monthly_passes SET status = 'expired' WHERE expiryDate < CURRENT_DATE AND status = 'active'")
        conn.commit()

        # Check for unlimited pass already active
        if plan_key == 'unlimited':
            cursor.execute("""
                SELECT passId FROM monthly_passes 
                WHERE username = %s AND status = 'active' AND expiryDate >= CURRENT_DATE
                AND source = 'ALL' AND destination = 'ALL'
                LIMIT 1
            """, (username,))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'error': 'You already have an active Unlimited Pass!'}), 400

        # Check each route for duplicates + validate station names
        for route in routes:
            src = route.get('source', '').strip()
            dst = route.get('destination', '').strip()
            
            if src == 'ALL' and dst == 'ALL':
                continue  # unlimited pass, skip validation
            
            if not src or not dst:
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'error': 'Each route must have source and destination'}), 400
            
            if src.lower() == dst.lower():
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'error': f'Source and destination cannot be the same ({src})'}), 400
            
            # Check if route already covered by an active pass
            cursor.execute("""
                SELECT passId FROM monthly_passes 
                WHERE username = %s AND status = 'active' AND expiryDate >= CURRENT_DATE
                AND (
                    (LOWER(source) = %s AND LOWER(destination) = %s)
                    OR (LOWER(source) = %s AND LOWER(destination) = %s)
                    OR (source = 'ALL' AND destination = 'ALL')
                )
                LIMIT 1
            """, (username, src.lower(), dst.lower(), dst.lower(), src.lower()))
            if cursor.fetchone():
                cursor.close()
                conn.close()
                return jsonify({'success': False, 'error': f'You already have an active pass covering {src} ↔ {dst}'}), 400

        cursor.close()
        conn.close()
        # Check wallet balance
        user_data = db.get_user_by_username(username)
        if not user_data or user_data['walletBalance'] < price:
            return jsonify({'success': False, 'error': f'Insufficient balance. Need ₹{price}'}), 400

        # Deduct from wallet
        new_balance = user_data['walletBalance'] - price
        db.update_user_wallet_balance(username, new_balance)

        # Create passes for each route
        from datetime import timedelta
        purchase_date = date.today()
        expiry_date = purchase_date + timedelta(days=30)
        pass_ids = []

        for route in routes:
            src = route.get('source', 'ALL')
            dst = route.get('destination', 'ALL')
            pid = db.insert_monthly_pass(username, src, dst, purchase_date, expiry_date, price / len(routes), plan_key)
            if pid > 0:
                pass_ids.append(pid)
                # Create MonthlyPass model object (OOP integration)
                pass_obj = MonthlyPass(username, src, dst, purchase_date, expiry_date, price / len(routes))
                pass_obj.pass_id = pid
                logger.info(f"📅 Pass #{pid}: valid={pass_obj.is_valid()}, days_remaining={pass_obj.days_remaining()}")

        logger.info(f"Monthly pass purchased: {plan['name']} by {username} — pass IDs {pass_ids}")

        return jsonify({
            'success': True,
            'message': f"{plan['name']} activated! Valid for 30 days.",
            'passIds': pass_ids,
            'newBalance': new_balance,
            'expiryDate': expiry_date.strftime('%Y-%m-%d')
        }), 200

    except Exception as e:
        logger.error(f"Monthly pass purchase error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/monthly-pass/active', methods=['GET'])
@require_login
def api_get_active_passes():
    """Get user's currently active monthly passes"""
    try:
        user = get_current_user()
        username = user['username']

        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Auto-expire old passes
        cursor.execute("UPDATE monthly_passes SET status = 'expired' WHERE expiryDate < CURRENT_DATE AND status = 'active'")
        conn.commit()
        
        cursor.execute("""
            SELECT passId, source, destination, purchaseDate, expiryDate, price,
                   COALESCE(planType, 'basic') as planType
            FROM monthly_passes
            WHERE username = %s AND expiryDate >= CURRENT_DATE
            ORDER BY expiryDate DESC
        """, (username,))
        passes = cursor.fetchall()

        result = []
        for p in passes:
            days_left = (p['expiryDate'] - date.today()).days
            total_days = (p['expiryDate'] - p['purchaseDate']).days
            
            # Count trips taken during this pass period on this route
            if p['source'] == 'ALL':
                cursor.execute("""
                    SELECT COUNT(*) as trip_count FROM tickets 
                    WHERE username = %s AND bookingDate >= %s AND bookingDate <= %s AND cancelled = FALSE
                """, (username, p['purchaseDate'], p['expiryDate']))
            else:
                cursor.execute("""
                    SELECT COUNT(*) as trip_count FROM tickets 
                    WHERE username = %s AND source = %s AND destination = %s 
                    AND bookingDate >= %s AND bookingDate <= %s AND cancelled = FALSE
                """, (username, p['source'], p['destination'], p['purchaseDate'], p['expiryDate']))
            trip_data = cursor.fetchone()
            trip_count = trip_data['trip_count'] if trip_data else 0
            
            # Calculate estimated savings (avg fare ~50 per trip)
            avg_fare = 50.0
            estimated_savings = max(0, (trip_count * avg_fare) - float(p['price']))
            
            plan_type = p['planType']
            benefits = MONTHLY_PASS_BENEFITS.get(plan_type, [])
            
            result.append({
                'passId': p['passId'],
                'source': p['source'],
                'destination': p['destination'],
                'purchaseDate': p['purchaseDate'].strftime('%Y-%m-%d'),
                'expiryDate': p['expiryDate'].strftime('%Y-%m-%d'),
                'daysLeft': days_left,
                'totalDays': total_days,
                'price': float(p['price']),
                'planType': plan_type,
                'tripCount': trip_count,
                'estimatedSavings': round(estimated_savings, 2),
                'benefits': benefits
            })

        cursor.close()
        conn.close()
        return jsonify({'success': True, 'passes': result}), 200

    except Exception as e:
        logger.error(f"Get active passes error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/monthly-pass/history', methods=['GET'])
@require_login
def api_get_pass_history():
    """Get user's complete pass history (active + expired)"""
    try:
        user = get_current_user()
        username = user['username']
        passes = db.get_all_monthly_passes(username)
        
        result = []
        for p in passes:
            result.append({
                'passId': p['passId'],
                'source': p['source'],
                'destination': p['destination'],
                'purchaseDate': p['purchaseDate'].strftime('%Y-%m-%d') if isinstance(p['purchaseDate'], date) else str(p['purchaseDate']),
                'expiryDate': p['expiryDate'].strftime('%Y-%m-%d') if isinstance(p['expiryDate'], date) else str(p['expiryDate']),
                'price': float(p['price']),
                'planType': p.get('planType', 'basic'),
                'status': p.get('status', 'expired')
            })
        
        return jsonify({'success': True, 'passes': result}), 200
    except Exception as e:
        logger.error(f"Pass history error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/monthly-pass/benefits', methods=['GET'])
def api_get_pass_benefits():
    """Get benefits for all pass plans"""
    return jsonify({
        'success': True,
        'plans': {
            'basic': {
                'name': 'Basic Pass',
                'price': 999,
                'routes': 1,
                'benefits': MONTHLY_PASS_BENEFITS['basic']
            },
            'premium': {
                'name': 'Premium Pass',
                'price': 1999,
                'routes': 3,
                'benefits': MONTHLY_PASS_BENEFITS['premium']
            },
            'unlimited': {
                'name': 'Unlimited Pass',
                'price': 3499,
                'routes': 0,
                'benefits': MONTHLY_PASS_BENEFITS['unlimited']
            }
        }
    }), 200


# ============================================================================
# STATION ROUTES
# ============================================================================

@app.route('/api/stations', methods=['GET'])
def api_get_all_stations():
    """Get all station names"""
    try:
        stations = list(db.get_all_station_names())
        return jsonify({
            'success': True,
            'stations': stations
        }), 200
    except Exception as e:
        logger.error(f"Get stations error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ADMIN ROUTES
# ============================================================================

@app.route('/api/admin/users', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_get_all_users():
    """Get all users (Admin only) — uses Admin model"""
    try:
        # Use Admin model object for OOP integration
        admin_obj = get_current_user_object()
        users = admin_obj.get_all_users() if isinstance(admin_obj, Admin) else db.get_all_users()
        
        formatted_users = []
        for user in users:
            formatted_users.append({
                'username': user['username'],
                'walletBalance': user['walletBalance'],
                'role': user['role']
            })
        
        return jsonify({
            'success': True,
            'users': formatted_users
        }), 200
        
    except Exception as e:
        logger.error(f"Admin get users error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/users/<username>', methods=['DELETE'])
@require_role(Role.ADMIN)
def api_admin_remove_user(username):
    """Remove a user (Admin only) — uses Admin model"""
    try:
        current_user = get_current_user()
        
        if username == current_user['username']:
            return jsonify({'success': False, 'error': 'Cannot delete yourself'}), 400
        
        # Use Admin model for removal + update datastore
        admin_obj = get_current_user_object()
        if isinstance(admin_obj, Admin) and admin_obj.remove_user(username):
            # Also remove from in-memory datastore
            ds_user = datastore.find_user_by_username(username)
            if ds_user:
                datastore.remove_user(ds_user)
            return jsonify({
                'success': True,
                'message': f'User {username} removed successfully'
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Failed to remove user'}), 500
        
    except Exception as e:
        logger.error(f"Admin remove user error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/stations/add', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_add_station():
    """
    Add a new station (Admin only) — uses Admin model + StationInfo
    
    Request JSON:
        {
            "name": "station_name",
            "x": 0.0,
            "y": 0.0
        }
    """
    try:
        data = request.json
        name = data.get('name', '').lower().strip()
        x = float(data.get('x', 0.0))
        y = float(data.get('y', 0.0))
        
        if not name:
            return jsonify({'success': False, 'error': 'Station name required'}), 400
        
        # Use Admin model for DB persistence
        admin_obj = get_current_user_object()
        success = False
        if isinstance(admin_obj, Admin):
            success = admin_obj.add_station(name, x, y)
        else:
            success = db.insert_or_update_station_location(name, x, y)
        
        if success:
            # Add to in-memory datastore with StationInfo
            station_info = StationInfo(name)
            station_info.set_location(x, y)
            datastore.add_station_info(name, station_info)
            
            return jsonify({
                'success': True,
                'message': f'Station {name} added successfully'
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Failed to add station'}), 500
        
    except Exception as e:
        logger.error(f"Admin add station error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/announcements', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_add_announcement():
    """
    Add system announcement (Admin only) — uses Admin model + datastore
    
    Request JSON:
        {"message": "string"}
    """
    try:
        data = request.json
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': 'Message required'}), 400
        
        # Use Admin model for DB persistence
        admin_obj = get_current_user_object()
        success = False
        if isinstance(admin_obj, Admin):
            success = admin_obj.add_announcement(message)
        else:
            success = db.insert_announcement(message)
        
        if success:
            # Track in datastore in-memory
            datastore.add_announcement(message)
            
            return jsonify({
                'success': True,
                'message': 'Announcement added successfully'
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Failed to add announcement'}), 500
        
    except Exception as e:
        logger.error(f"Admin add announcement error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/admin/feedbacks', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_get_all_feedbacks():
    """Get all feedbacks (Admin only)"""
    try:
        feedbacks = db.get_all_feedbacks()
        
        formatted_feedbacks = []
        for fb in feedbacks:
            formatted_feedbacks.append({
                'feedbackId': fb['feedbackId'],
                'username': fb['username'],
                'text': fb['text'],
                'type': fb['type'],
                'timestamp': format_datetime(fb['timestamp'])
            })
        
        return jsonify({
            'success': True,
            'feedbacks': formatted_feedbacks
        }), 200
        
    except Exception as e:
        logger.error(f"Admin get feedbacks error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# ANNOUNCEMENTS (Public)
# ============================================================================

# /api/announcements is defined later in the file (see get_public_announcements)






# ============================================================================
# PUBLIC ENDPOINTS (No Auth Required) — For Landing Page
# ============================================================================

@app.route('/api/public/stats', methods=['GET'])
def api_public_stats():
    """Get live system stats for the landing page hero section"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("SELECT COUNT(*) as total FROM users WHERE role = 'USER'")
        users = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM tickets WHERE cancelled = FALSE")
        bookings = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(*) as total FROM station_locations")
        stations = cursor.fetchone()['total']
        
        cursor.execute("SELECT COUNT(DISTINCT username) as active FROM tickets WHERE DATE(bookingDate) >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)")
        active_users = cursor.fetchone()['active']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_users': users,
                'total_bookings': bookings,
                'stations_count': stations,
                'active_commuters': active_users,
                'uptime_pct': 99.9
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Public stats error: {e}")
        return jsonify({'success': True, 'stats': {
            'total_users': 500, 'total_bookings': 2000, 
            'stations_count': 50, 'active_commuters': 120, 'uptime_pct': 99.9
        }}), 200


@app.route('/api/public/testimonials', methods=['GET'])
def api_public_testimonials():
    """Get anonymized positive feedback for testimonials section"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get recent positive feedback (type = 'feedback', not 'complaint')
        cursor.execute("""
            SELECT f.text, f.timestamp, f.username
            FROM feedbacks f
            WHERE f.type = 'feedback'
            ORDER BY f.timestamp DESC
            LIMIT 6
        """)
        feedbacks = cursor.fetchall()
        cursor.close()
        conn.close()
        
        testimonials = []
        for fb in feedbacks:
            # Anonymize: show first 2 chars + ***
            name = fb['username']
            anon_name = name[:2] + '***' if len(name) > 2 else name + '***'
            testimonials.append({
                'text': fb['text'],
                'user': anon_name,
                'date': fb['timestamp'].strftime('%B %Y') if fb['timestamp'] else 'Recent'
            })
        
        return jsonify({'success': True, 'testimonials': testimonials}), 200
        
    except Exception as e:
        logger.error(f"Testimonials error: {e}")
        return jsonify({'success': True, 'testimonials': []}), 200


# ============================================================================
# ERROR HANDLERS
# ============================================================================

@app.errorhandler(404)
def not_found(error):
    # Serve branded 404 page for browser requests
    if request.accept_mimetypes.accept_html:
        return send_from_directory(FRONTEND_DIR, '404.html'), 404
    return jsonify({'success': False, 'error': 'Endpoint not found'}), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({'success': False, 'error': 'Internal server error'}), 500

# ============================================================================
# SERVE FRONTEND PAGES
# ============================================================================



# Get the frontend directory path
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), 'frontend')

@app.route('/index.html')
@app.route('/')
def serve_index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/login.html')
def serve_login():
    # Optional: If already logged in, redirect to appropriate dashboard
    if 'username' in session:
        if session.get('role') == 'ADMIN':
            return redirect('/admin.html')
        return redirect('/dashboard.html')
        
    return send_from_directory(FRONTEND_DIR, 'login.html')

@app.route('/register.html')
def serve_register():
    return send_from_directory(FRONTEND_DIR, 'register.html')

@app.route('/dashboard.html')
def serve_dashboard():
    # 1. SECURITY: Check if logged in
    if 'username' not in session:
        return redirect('/login.html')
    
    return send_from_directory(FRONTEND_DIR, 'dashboard.html')

@app.route('/admin.html')
def serve_admin():
    # 1. SECURITY: Check if logged in
    if 'username' not in session:
        return redirect('/login.html')
    
    # 2. SECURITY: Check Role
    # If a USER tries to access Admin panel, force them to Dashboard
    if session.get('role') != 'ADMIN':
        return redirect('/dashboard.html')
        
    return send_from_directory(FRONTEND_DIR, 'admin.html')

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'css'), filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    return send_from_directory(os.path.join(FRONTEND_DIR, 'js'), filename)

@app.route('/favicon.ico')
def favicon():
    # Return an SVG favicon (metro train icon) to prevent 404 errors
    svg = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
        <text y=".9em" font-size="90">🚇</text></svg>'''
    return app.response_class(svg, mimetype='image/svg+xml')

# ============================================================================
# NEW FEATURES - QR CODE, PDF, ANALYTICS
# ============================================================================



# Generate QR Code for Ticket
@app.route('/api/tickets/<int:ticket_id>/qrcode', methods=['GET'])
def generate_qr_code(ticket_id):
    """Generate QR code for ticket"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        # CORRECTION: Added 'db.' prefix
        ticket = db.get_ticket_by_id(ticket_id)
        
        if not ticket:
            return jsonify({'success': False, 'message': 'Ticket not found'}), 404
        
        # Verify ticket belongs to user
        if ticket['username'] != username:
            return jsonify({'success': False, 'message': 'Unauthorized'}), 403
        
        # Create QR data (includes travelTime for gate validation)
        travel_time = ticket.get('travelTime', 'now')
        qr_data = f"METRO-{ticket_id}|{ticket['source']}|{ticket['destination']}|{ticket['travelDate']}|{ticket['passengers']}|{travel_time}"
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        img_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'qr_code': f'data:image/png;base64,{img_base64}'
        })
    except Exception as e:
        logger.error(f"QR Code Error: {e}") # Log the error to console
        return jsonify({'success': False, 'message': str(e)}), 500


# ============================================================================
# QR CODE GATE VALIDATION
# ============================================================================

@app.route('/api/tickets/<int:ticket_id>/validate-entry', methods=['POST'])
def validate_qr_entry(ticket_id):
    """Validate QR code at metro gate — blocks off-peak tickets during peak hours"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        ticket = db.get_ticket_by_id(ticket_id)
        
        if not ticket:
            return jsonify({
                'success': False,
                'allowed': False,
                'reason': 'Ticket not found',
                'icon': 'times-circle'
            }), 404
        
        # Verify ticket belongs to user
        if ticket['username'] != username:
            return jsonify({
                'success': False,
                'allowed': False,
                'reason': 'Unauthorized — this ticket belongs to another user',
                'icon': 'user-slash'
            }), 403
        
        # Check if ticket is cancelled
        if ticket.get('cancelled'):
            return jsonify({
                'success': True,
                'allowed': False,
                'reason': 'This ticket has been cancelled',
                'icon': 'ban'
            })
        
        # Check travel date
        from datetime import date as date_cls
        today = date_cls.today()
        ticket_date = ticket['travelDate']
        if hasattr(ticket_date, 'date'):
            ticket_date = ticket_date.date()
        
        if ticket_date != today:
            return jsonify({
                'success': True,
                'allowed': False,
                'reason': f'This ticket is valid for {ticket_date.strftime("%d %b %Y")}, not today',
                'icon': 'calendar-times'
            })
        
        # Determine ticket's booked travel time
        ticket_travel_time = ticket.get('travelTime', 'now')
        
        # Parse the hour from the ticket's travel time
        if ticket_travel_time and ticket_travel_time != 'now':
            try:
                ticket_hour = int(ticket_travel_time.split(':')[0])
            except:
                ticket_hour = datetime.now().hour
        else:
            ticket_hour = datetime.now().hour
        
        # Check if the ticket was booked for peak or off-peak
        peak_hours = list(range(8, 11)) + list(range(17, 19))  # 8-10 AM, 5-6 PM
        ticket_is_peak = ticket_hour in peak_hours
        
        # Check current real-world time
        current_hour = datetime.now().hour
        current_is_peak = current_hour in peak_hours
        
        # THE KEY RULE: Off-peak ticket + current peak time = DENIED
        if not ticket_is_peak and current_is_peak:
            return jsonify({
                'success': True,
                'allowed': False,
                'reason': f'Off-peak ticket (booked for {ticket_travel_time}) cannot be used during peak hours (8-11 AM, 5-7 PM). Current time is peak.',
                'icon': 'exclamation-triangle',
                'ticket_type': 'OFF-PEAK',
                'current_period': 'PEAK'
            })
        
        # All checks passed — ENTRY ALLOWED
        entry_type = 'PEAK' if ticket_is_peak else 'OFF-PEAK'
        return jsonify({
            'success': True,
            'allowed': True,
            'reason': f'Entry granted! {entry_type} ticket validated successfully.',
            'icon': 'check-circle',
            'ticket_type': entry_type,
            'current_period': 'PEAK' if current_is_peak else 'OFF-PEAK'
        })
        
    except Exception as e:
        logger.error(f"QR Validation Error: {e}")
        return jsonify({'success': False, 'allowed': False, 'reason': str(e)}), 500


# Get Transaction History

@app.route('/api/user/transactions', methods=['GET'])
def get_transactions():
    """Get unified transaction history (Tickets + Recharges)"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # 1. Get Tickets (DEBITS)
        cursor.execute("""
            SELECT ticketId as id, fare as amount, bookingDate as date, 
                   CONCAT(source, ' -> ', destination) as description, 
                   'DEBIT' as type, cancelled
            FROM tickets
            WHERE username = %s
        """, (username,))
        tickets = cursor.fetchall()
        
        # 2. Get Recharges (CREDITS)
        cursor.execute("""
            SELECT id, amount, date, description, 'CREDIT' as type, 
                   FALSE as cancelled
            FROM wallet_history
            WHERE username = %s
        """, (username,))
        recharges = cursor.fetchall()
        
        conn.close()
        
        # 3. Format dates as strings for JSON (MySQL already stores IST)
        def fmt_date(dt_val):
            """Format datetime to string for JSON serialization"""
            if dt_val is None:
                return ''
            if isinstance(dt_val, datetime):
                return dt_val.strftime('%Y-%m-%d %H:%M:%S')
            return str(dt_val)
        
        # Apply formatting to all transactions
        all_transactions = tickets + recharges
        for t in all_transactions:
            t['date'] = fmt_date(t['date'])
        
        # 4. Sort by Date (Newest First)
        all_transactions.sort(key=lambda x: x['date'], reverse=True)
        
        return jsonify({
            'success': True,
            'transactions': all_transactions[:50] # Limit to 50 items
        })
    except Exception as e:
        logger.error(f"Transaction Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
# Get Spending Analytics
@app.route('/api/user/analytics', methods=['GET'])
@app.route('/api/analytics', methods=['GET'])
@require_login
def get_analytics():
    """Get user spending analytics with REAL DB DISTANCE"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # 1. Total spent and TOTAL DISTANCE (Real DB Data)
        # We use COALESCE to return 0 if the sum is NULL
        cursor.execute("""
            SELECT 
                SUM(fare) as total_spent, 
                COUNT(*) as total_bookings,
                COALESCE(SUM(distance), 0) as total_distance 
            FROM tickets
            WHERE username = %s AND cancelled = FALSE
        """, (username,))
        totals = cursor.fetchone()
        
        # 2. Monthly spending (for the chart)
        cursor.execute("""
            SELECT DATE_FORMAT(bookingDate, '%Y-%m') as month, 
                   SUM(fare) as amount, COUNT(*) as count
            FROM tickets
            WHERE username = %s AND cancelled = FALSE
            GROUP BY DATE_FORMAT(bookingDate, '%Y-%m')
            ORDER BY month DESC
            LIMIT 6
        """, (username,))
        monthly = cursor.fetchall()
        
        # 3. Most used routes
        cursor.execute("""
            SELECT source, destination, COUNT(*) as trip_count
            FROM tickets
            WHERE username = %s AND cancelled = FALSE
            GROUP BY source, destination
            ORDER BY trip_count DESC
            LIMIT 5
        """, (username,))
        routes = cursor.fetchall()
        
        # 4. Daily trip counts for heatmap (last 12 weeks)
        cursor.execute("""
            SELECT DATE(bookingDate) as date, COUNT(*) as count
            FROM tickets
            WHERE username = %s AND cancelled = FALSE
              AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 84 DAY)
            GROUP BY DATE(bookingDate)
            ORDER BY date
        """, (username,))
        daily = cursor.fetchall()
        daily_trips = [
            {'date': str(row['date']), 'count': int(row['count'])}
            for row in daily
        ]

        cursor.close()
        conn.close()

        return jsonify({
            'success': True,
            'analytics': {
                'total_spent': float(totals['total_spent'] or 0),
                'total_bookings': totals['total_bookings'] or 0,
                'total_distance': float(totals['total_distance'] or 0),
                'monthly_spending': monthly,
                'favorite_routes': routes,
                'daily_trips': daily_trips,
            }
        })
    except Exception as e:
        logger.error(f"Analytics Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500
# Save Favorite Route
@app.route('/api/user/favorites', methods=['POST'])
def add_favorite():
    """Add favorite route"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    data = request.json
    source = data.get('source')
    destination = data.get('destination')
    
    if not source or not destination:
        return jsonify({'success': False, 'message': 'Source and destination required'}), 400
    
    try:
        # CORRECTION: Added 'db.' prefix
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # Create favorites table if not exists
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS favorite_routes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50),
                source VARCHAR(100),
                destination VARCHAR(100),
                created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # Add favorite
        cursor.execute("""
            INSERT INTO favorite_routes (username, source, destination)
            VALUES (%s, %s, %s)
        """, (username, source, destination))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Route saved to favorites'})
    except Exception as e:
        logger.error(f"Favorites Error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500

# Get Favorite Routes
@app.route('/api/user/favorites', methods=['GET'])
def get_favorites():
    """Get user's favorite routes"""
    username = session.get('username')
    if not username:
        return jsonify({'success': False, 'message': 'Not authenticated'}), 401
    
    try:
        # CORRECTION: Added 'db.' prefix
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        cursor.execute("""
            SELECT id, source, destination, created_date
            FROM favorite_routes
            WHERE username = %s
            ORDER BY created_date DESC
        """, (username,))
        
        favorites = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'favorites': favorites})
    except Exception as e:
        logger.error(f"Favorites Error: {e}")
        return jsonify({'success': False, 'favorites': [], 'error': str(e)})

        # ============================================================================
# NEW FEATURES: LOYALTY, LOST & FOUND, NOTIFICATIONS
# ============================================================================


@app.route('/api/loyalty/redeem', methods=['POST'])
@require_login
def redeem_loyalty_points():
    """Redeem 50 points for Rs. 20 Wallet Balance"""
    try:
        user = get_current_user()
        points = user.get('loyaltyPoints', 0)
        
        if points < 50:
            return jsonify({'success': False, 'error': 'Need 50 points to redeem!'}), 400
            
        # Logic: Deduct 50 points, Add Rs 20
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Update Points
        cursor.execute("UPDATE users SET loyaltyPoints = loyaltyPoints - 50 WHERE username = %s", (user['username'],))
        # 2. Add Money
        cursor.execute("UPDATE users SET walletBalance = walletBalance + 20 WHERE username = %s", (user['username'],))
        # 3. Add Notification
        msg = "Redeemed 50 Green Points for Rs. 20 credit"
        cursor.execute("INSERT INTO notifications (username, message) VALUES (%s, %s)", (user['username'], msg))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Points redeemed successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/loyalty/redeem-all', methods=['POST'])
@require_login
def redeem_all_loyalty_points():
    """Redeem ALL points to wallet. 50 points = Rs. 20"""
    try:
        user = get_current_user()
        points = user.get('loyaltyPoints', 0)
        
        if points < 50:
            return jsonify({'success': False, 'error': f'Need at least 50 points. You have {points}.'}), 400
        
        # Calculate how many sets of 50 we can redeem
        redeemable_sets = points // 50
        points_to_deduct = redeemable_sets * 50
        money_to_add = redeemable_sets * 20
        remaining_points = points - points_to_deduct
        
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("UPDATE users SET loyaltyPoints = %s WHERE username = %s", (remaining_points, user['username']))
        cursor.execute("UPDATE users SET walletBalance = walletBalance + %s WHERE username = %s", (money_to_add, user['username']))
        msg = f"Converted {points_to_deduct} Green Points to ₹{money_to_add} wallet credit"
        cursor.execute("INSERT INTO notifications (username, message) VALUES (%s, %s)", (user['username'], msg))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': f'₹{money_to_add} added to wallet!',
            'points_redeemed': points_to_deduct,
            'money_added': money_to_add,
            'remaining_points': remaining_points
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/lostfound/my', methods=['GET'])
@require_login
def get_my_lost_reports():
    try:
        user = get_current_user()
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT * FROM lost_found WHERE username = %s ORDER BY reportDate DESC", (user['username'],))
        reports = cursor.fetchall()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'reports': reports})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/system/upgrade', methods=['GET'])
def upgrade_system_tables():
    """Final Fix: Creates missing tables and ignores errors"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # 1. Add Loyalty Points (Ignore if exists)
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN loyaltyPoints INT DEFAULT 0")
        except:
            pass 

        # 2. Create Lost & Found
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lost_found (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50),
                    item VARCHAR(100),
                    description TEXT,
                    status VARCHAR(20) DEFAULT 'SEARCHING',
                    reportDate DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except:
            pass

        # 3. Create Notifications
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50),
                    message VARCHAR(255),
                    is_read BOOLEAN DEFAULT FALSE,
                    date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except:
            pass

        # 4. Create Wallet History (THIS IS THE MISSING TABLE)
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS wallet_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50),
                    amount DOUBLE,
                    type VARCHAR(20),
                    description VARCHAR(100),
                    date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
        except:
            pass

        # 5. Add travelTime column to tickets (for QR gate validation)
        try:
            cursor.execute("ALTER TABLE tickets ADD COLUMN travelTime VARCHAR(10) DEFAULT 'now'")
        except:
            pass  # Column likely exists
        
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'System Upgraded Successfully!'})
    except Exception as e:
        # Even if there is a big error, don't crash the browser, just tell us.
        return jsonify({'success': False, 'error': str(e)})


# Public announcements + alerts endpoint (for live ticker)
@app.route('/api/announcements', methods=['GET'])
@require_login
def get_public_announcements():
    """Get system announcements + user alerts for the live ticker"""
    try:
        user = get_current_user()
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        items = []

        # 1. System-wide announcements
        announcements = db.get_all_announcements()
        for a in announcements:
            msg = a.get('message', '')
            # Auto-detect type from message content
            if any(kw in msg.upper() for kw in ['EMERGENCY', 'URGENT', 'SIGNAL FAILURE', 'DISRUPTION']):
                a_type = 'danger'
            elif any(kw in msg.upper() for kw in ['WARNING', 'DELAY', 'MAINTENANCE', 'CLOSED']):
                a_type = 'warning'
            elif any(kw in msg.upper() for kw in ['NEW', 'LAUNCHED', 'OPENED', 'SUCCESS']):
                a_type = 'success'
            else:
                a_type = 'info'
            items.append({
                'message': msg,
                'type': a_type,
                'source': 'announcement',
                'date': str(a.get('createdDate', ''))
            })

        # 2. User-specific notifications (alerts)
        cursor.execute(
            "SELECT message, date FROM notifications WHERE username = %s ORDER BY date DESC LIMIT 10",
            (user['username'],)
        )
        notifs = cursor.fetchall()
        for n in notifs:
            msg = n.get('message', '')
            if any(kw in msg.upper() for kw in ['EMERGENCY', 'CANCEL', 'FAIL', 'ERROR']):
                n_type = 'danger'
            elif any(kw in msg.upper() for kw in ['REDEEM', 'POINT', 'WARN']):
                n_type = 'warning'
            elif any(kw in msg.upper() for kw in ['SUCCESS', 'TICKET', 'RECEIPT', 'BOOKED']):
                n_type = 'success'
            else:
                n_type = 'info'
            items.append({
                'message': msg,
                'type': n_type,
                'source': 'alert',
                'date': str(n.get('date', ''))
            })

        conn.close()
        return jsonify({
            'success': True,
            'announcements': items
        })
    except Exception as e:
        logger.error(f"Announcements error: {e}")
        return jsonify({'success': False, 'announcements': []}), 500


@app.route('/api/notifications', methods=['GET'])
@require_login
def get_user_notifications():
    try:
        user = get_current_user()
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT id, message, date, is_read FROM notifications WHERE username = %s ORDER BY date DESC LIMIT 20", (user['username'],))
        notifs = cursor.fetchall()
        
        # Count unread
        unread = sum(1 for n in notifs if not n.get('is_read', False))
        
        # Also get Loyalty Points to show on dashboard
        cursor.execute("SELECT loyaltyPoints FROM users WHERE username = %s", (user['username'],))
        points_row = cursor.fetchone()
        points = points_row['loyaltyPoints'] if points_row else 0
        
        conn.close()
        return jsonify({'success': True, 'notifications': notifs, 'loyaltyPoints': points, 'unreadCount': unread})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/notifications/read', methods=['POST'])
@require_login
def mark_notifications_read():
    try:
        user = get_current_user()
        conn = db.get_db_connection()
        cursor = conn.cursor(buffered=True)
        cursor.execute("UPDATE notifications SET is_read = TRUE WHERE username = %s AND is_read = FALSE", (user['username'],))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'All notifications marked as read'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/lost-found/report', methods=['POST'])
@require_login
def report_lost_item():
    try:
        data = request.json
        item_text = data.get('item', '').strip()
        description = data.get('description', item_text).strip() # Use item as desc if empty

        if not item_text:
            return jsonify({'success': False, 'error': 'Item description required'}), 400

        user = get_current_user()

        # FIX: Use the correct table function we just created
        if db.insert_lost_found(user['username'], item_text, description):
            return jsonify({
                'success': True,
                'message': 'Lost item reported successfully! Check "My Reports" for updates.'
            }), 200
        else:
            return jsonify({'success': False, 'error': 'Database error: Failed to save report'}), 500

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500




# 1. GET ALL LOST ITEMS
@app.route('/api/admin/lost-found', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_lost_found():
    items = db.get_all_lost_found_items()
    # Format dates
    for item in items:
        item['reportDate'] = format_datetime(item['reportDate'])
    return jsonify({'success': True, 'items': items})

# 2. UPDATE LOST ITEM STATUS
@app.route('/api/admin/lost-found/<int:item_id>/status', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_update_item_status(item_id):
    data = request.json
    status = data.get('status')
    if db.update_lost_found_status(item_id, status):
        # Notify the user who reported the item
        try:
            conn = db.get_db_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            cursor.execute("SELECT username, item FROM lost_found WHERE id = %s", (item_id,))
            row = cursor.fetchone()
            if row:
                status_msgs = {
                    'FOUND': f"Great news! Your lost item '{row['item']}' has been FOUND! Visit the Lost & Found desk to collect it.",
                    'CLOSED': f"Your lost item report for '{row['item']}' has been CLOSED.",
                    'SEARCHING': f"We are actively searching for your lost item '{row['item']}'. Stay tuned!"
                }
                msg = status_msgs.get(status, f"Your lost item '{row['item']}' status updated to {status}.")
                cursor.execute("INSERT INTO notifications (username, message) VALUES (%s, %s)", (row['username'], msg))
                conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            logger.error(f"Notification error for lost item {item_id}: {e}")
        return jsonify({'success': True, 'message': 'Status updated'})
    return jsonify({'success': False, 'error': 'Update failed'}), 500

# 3. ANALYTICS DATA FOR CHARTS
@app.route('/api/admin/analytics/revenue', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_revenue_stats():
    """
    Get revenue analytics with proper formatting for chart
    Supports period parameter: week, month, year
    """
    period = request.args.get('period', 'week')
    
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    
    labels = []
    data = []
    total = 0
    
    try:
        if period == 'week':
            # Last 7 days revenue
            cursor.execute("""
                SELECT 
                    DAYNAME(bookingDate) as day_name,
                    DATE(bookingDate) as booking_date,
                    COALESCE(SUM(fare), 0) as daily_revenue
                FROM tickets 
                WHERE cancelled = 0 
                    AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY DATE(bookingDate), DAYNAME(bookingDate)
                ORDER BY booking_date ASC
            """)
            results = cursor.fetchall()
            
            days_map = {}
            for row in results:
                days_map[row['day_name']] = float(row['daily_revenue'])
                total += float(row['daily_revenue'])
            
            weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            labels = [day[:3] for day in weekdays]
            data = [days_map.get(day, 0) for day in weekdays]
            
        elif period == 'month':
            # Last 4 weeks revenue
            cursor.execute("""
                SELECT 
                    WEEK(bookingDate, 1) as week_num,
                    COALESCE(SUM(fare), 0) as week_revenue
                FROM tickets 
                WHERE cancelled = 0 
                    AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 28 DAY)
                GROUP BY WEEK(bookingDate, 1)
                ORDER BY week_num ASC
            """)
            results = cursor.fetchall()
            
            for i, row in enumerate(results, 1):
                labels.append(f'Week {i}')
                revenue = float(row['week_revenue'])
                data.append(revenue)
                total += revenue
            
            while len(labels) < 4:
                labels.append(f'Week {len(labels) + 1}')
                data.append(0)
                
        elif period == 'year':
            # Last 12 months revenue
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(bookingDate, '%Y-%m') as month,
                    DATE_FORMAT(bookingDate, '%b') as month_name,
                    COALESCE(SUM(fare), 0) as monthly_revenue
                FROM tickets 
                WHERE cancelled = 0 
                    AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                GROUP BY DATE_FORMAT(bookingDate, '%Y-%m')
                ORDER BY month ASC
            """)
            results = cursor.fetchall()
            
            for row in results:
                labels.append(row['month_name'])
                revenue = float(row['monthly_revenue'])
                data.append(revenue)
                total += revenue
        
        # Get ticket stats
        cursor.execute("""
            SELECT 
                COUNT(CASE WHEN cancelled = 0 THEN 1 END) as active_tickets,
                COUNT(CASE WHEN cancelled = 1 THEN 1 END) as cancelled_tickets,
                COUNT(*) as total_tickets
            FROM tickets
        """)
        ticket_stats = cursor.fetchone()
        
        # Get active users count
        cursor.execute("""
            SELECT COUNT(DISTINCT username) as active_users
            FROM tickets
            WHERE cancelled = 0 
                AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
        """)
        user_stats = cursor.fetchone()
        
        # Calculate growth percentage
        if period == 'week':
            cursor.execute("""
                SELECT COALESCE(SUM(fare), 0) as prev_revenue
                FROM tickets 
                WHERE cancelled = 0 
                    AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
                    AND bookingDate < DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            """)
        elif period == 'month':
            cursor.execute("""
                SELECT COALESCE(SUM(fare), 0) as prev_revenue
                FROM tickets 
                WHERE cancelled = 0 
                    AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 56 DAY)
                    AND bookingDate < DATE_SUB(CURDATE(), INTERVAL 28 DAY)
            """)
        else:
            cursor.execute("""
                SELECT COALESCE(SUM(fare), 0) as prev_revenue
                FROM tickets 
                WHERE cancelled = 0 
                    AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 24 MONTH)
                    AND bookingDate < DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
            """)
        
        prev_data = cursor.fetchone()
        prev_revenue = float(prev_data['prev_revenue'])
        
        if prev_revenue > 0 and total > 0:
            revenue_growth = round(((total - prev_revenue) / prev_revenue) * 100, 1)
        else:
            revenue_growth = 0 if total == 0 else 100
        
        conn.close()
        
        return jsonify({
            'success': True,
            'labels': labels,
            'data': data,
            'total': round(total, 2),
            'revenue_growth': revenue_growth,
            'tickets_sold': ticket_stats['active_tickets'] if ticket_stats else 0,
            'active_users': user_stats['active_users'] if user_stats else 0,
            'ticket_stats': {
                'active': ticket_stats['active_tickets'] if ticket_stats else 0,
                'cancelled': ticket_stats['cancelled_tickets'] if ticket_stats else 0,
                'total': ticket_stats['total_tickets'] if ticket_stats else 0
            }
        })
        
    except Exception as e:
        conn.close()
        logger.error(f"Revenue analytics error: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'labels': ['No Data'],
            'data': [0],
            'total': 0
        }), 500
# FEATURE 4: LIVE STATION STATUS (Simulated)
@app.route('/api/station/status/<string:station_name>', methods=['GET'])
def get_station_status(station_name):
    # Simulating real-time data
    crowd_levels = ['Low', 'Moderate', 'High', 'Very High']
    next_train = random.randint(2, 15)
    parking = random.randint(0, 50)
    
    return jsonify({
        'success': True,
        'station': station_name,
        'crowd': random.choice(crowd_levels),
        'next_train_min': next_train,
        'parking_slots': parking,
        'lift_status': 'Operational'
    })

# FEATURE 3: SOS ALERT
@app.route('/api/sos/alert', methods=['POST'])
@require_login
def trigger_sos():
    user = get_current_user()
    # In a real app, this would SMS the police. Here we log it.
    logger.warning(f"SOS TRIGGERED BY {user['username']}! Location: Dashboard")
    return jsonify({'success': True, 'message': 'Emergency Alert Sent to Station Control!'})



@app.route('/api/admin/live-feed', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_live_feed():
    return jsonify({'success': True, 'tickets': db.get_recent_global_tickets()})

@app.route('/api/admin/station-stats', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_station_stats():
    return jsonify({'success': True, 'stats': db.get_station_traffic_stats()})

@app.route('/api/admin/top-users', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_top_users():
    return jsonify({'success': True, 'users': db.get_top_users_by_balance()})

@app.route('/api/admin/system/reset', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_system_reset():
    """DANGEROUS: Wipes all data"""
    if db.clear_all_data():
        # Re-initialize default admin/stations if needed here
        return jsonify({'success': True, 'message': 'System Wiped Successfully'})
    return jsonify({'success': False, 'error': 'Reset Failed'}), 500



@app.route('/api/admin/analytics/peak-hours', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_peak_hours():
    return jsonify({'success': True, 'data': db.get_peak_hour_stats()})

@app.route('/api/admin/analytics/sentiment', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_sentiment():
    return jsonify({'success': True, 'data': db.get_feedback_sentiment()})

@app.route('/api/admin/staff/add', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_add_staff():
    data = request.json
    hashed = hash_password(data['password'])
    if db.create_staff_user(data['username'], hashed):
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'User exists'})

@app.route('/api/admin/pricing/surge', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_surge():
    # In a real app, save this to a 'config' table. 
    # Here we just acknowledge it for the UI demo.
    data = request.json
    return jsonify({'success': True, 'multiplier': data['multiplier']})

@app.route('/api/admin/tickets/all', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_all_tickets():
    return jsonify({'success': True, 'tickets': db.get_all_tickets_full()})

@app.route('/api/admin/station/status', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_station_status():
    data = request.json
    db.toggle_station_status(data['name'], data['status'])
    return jsonify({'success': True})
    
# 1. CCTV & INFRASTRUCTURE
@app.route('/api/admin/infra/cctv', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_cctv():
    # Simulating camera status based on real stations
    stations = db.get_all_station_names() # Uses your existing DB function
    cameras = []
    for i, st in enumerate(stations):
        cameras.append({
            'id': f"CAM-{100+i}",
            'location': st,
            'status': 'ONLINE' if i % 5 != 0 else 'MAINTENANCE', # Every 5th cam offline
            'activity': 'HIGH' if i < 3 else 'LOW'
        })
    return jsonify({'success': True, 'cameras': cameras})

# 2. POWER GRID ANALYTICS (Real DB Math)
@app.route('/api/admin/infra/power', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_power():
    # Calculate energy usage based on real ticket volume (More passengers = More trains)
    tickets = db.get_all_tickets_full()
    total_pax = len(tickets)
    base_load = 450 # kWh
    current_load = base_load + (total_pax * 1.5) 
    return jsonify({
        'success': True, 
        'grid_load': current_load,
        'voltage': 240 + (total_pax % 10), # Simulated fluctuation
        'efficiency': 94
    })

# 3. DATABASE BACKUP (Real Feature)
@app.route('/api/admin/system/backup', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_backup():
    # Exports User DB to JSON
    users = db.get_all_users() # Assuming you have a get_all_users fn
    return jsonify({
        'success': True,
        'timestamp': str(datetime.now()),
        'record_count': len(users),
        'data': users 
    })



@app.route('/api/admin/system/health', methods=['GET'])
def api_system_health_unified():
    """Unified System Health Endpoint"""
    try:
        # Get Real System Stats
        # interval=0.5 gives a real measurement (interval=None returns 0.0 on first call)
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory().percent
        # Windows uses 'C:\\', Linux/Mac uses '/'
        disk_path = 'C:\\' if os.name == 'nt' else '/'
        disk = psutil.disk_usage(disk_path).percent
        status = 'Online'
        uptime = 'Running'
    except Exception as e:
        # Fallback (Simulation) if psutil fails or not installed
        import random
        cpu = random.randint(10, 40)
        ram = random.randint(40, 70)
        disk = 55
        status = 'Simulation'
        uptime = 'Simulated'

    # Return keys matching frontend JS exactly (cpu, ram, disk)
    return jsonify({
        'success': True,
        'cpu': round(cpu, 1),
        'ram': round(ram, 1),
        'disk': round(disk, 1),
        'status': status,
        'uptime': uptime
    })

@app.route('/api/ticket/download/<int:ticket_id>')
def download_ticket_pdf(ticket_id):
    if 'user_id' not in session:
        return jsonify({'success': False, 'message': 'Login required'})
    
    # Fetch ticket details
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    cursor.execute("SELECT * FROM tickets WHERE ticket_id = %s AND user_id = %s", 
                   (ticket_id, session['user_id']))
    ticket = cursor.fetchone()
    conn.close()

    if not ticket:
        return jsonify({'success': False, 'message': 'Ticket not found'})

    # Generate PDF in memory
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    
    # Draw Ticket Design
    c.setFont("Helvetica-Bold", 24)
    c.drawString(100, 750, "METRO TICKET")
    c.setFont("Helvetica", 14)
    c.drawString(100, 700, f"Ticket ID: #{ticket['ticket_id']}")
    c.drawString(100, 670, f"Source: {ticket['source'].replace('_', ' ').title()}")
    c.drawString(100, 640, f"Destination: {ticket['destination'].replace('_', ' ').title()}")
    c.drawString(100, 610, f"Date: {ticket['booking_date']}")
    c.drawString(100, 580, f"Fare: Rs. {ticket['fare']}")
    c.drawString(100, 550, f"Status: {ticket['status']}")
    
    # Add Footer
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(100, 500, "Please show this PDF at the station gate.")
    
    c.save()
    buffer.seek(0)
    
    return send_file(buffer, as_attachment=True, download_name=f'ticket_{ticket_id}.pdf', mimetype='application/pdf')



# 1. GLOBAL SEARCH ("God Mode")
@app.route('/api/admin/global_search')
@require_role(Role.ADMIN)
def admin_global_search():
    query = request.args.get('q', '').lower()
    conn = db.get_db_connection()
    cursor = conn.cursor(dictionary=True, buffered=True)
    
    # Search Users
    cursor.execute("SELECT user_id, username, role FROM users WHERE username LIKE %s", (f"%{query}%",))
    users = cursor.fetchall()
    
    # Search Tickets
    cursor.execute("SELECT ticket_id, source, destination, status FROM tickets WHERE ticket_id LIKE %s", (f"%{query}%",))
    tickets = cursor.fetchall()
    
    conn.close()
    return jsonify({'success': True, 'results': {'users': users, 'tickets': tickets}})

# 2. SYSTEM CONTROL (Peak Pricing & Maintenance)
system_config = {'peak_pricing': False, 'maintenance_mode': False}

@app.route('/api/admin/config/update', methods=['POST'])
@require_role(Role.ADMIN)
def update_system_config():
    data = request.json
    if 'peak_pricing' in data: system_config['peak_pricing'] = data['peak_pricing']
    if 'maintenance_mode' in data: system_config['maintenance_mode'] = data['maintenance_mode']
    return jsonify({'success': True, 'config': system_config})

@app.route('/api/admin/config/get')
@require_role(Role.ADMIN)
def get_system_config():
    return jsonify({'success': True, 'config': system_config})

# 3. BULK REFUND ACTION
@app.route('/api/admin/refunds/approve_all', methods=['POST'])
@require_role(Role.ADMIN)
def approve_all_refunds():
    conn = db.get_db_connection()
    cursor = conn.cursor()
    # Approve all pending refunds < Rs 500 (Safe auto-approve limit)
    cursor.execute("UPDATE tickets SET status='REFUNDED' WHERE status='CANCELLED' AND fare < 500")
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': f'Auto-approved {affected} refunds.'})

# 4. USER BAN ACTION
@app.route('/api/admin/users/ban', methods=['POST'])
@require_role(Role.ADMIN)
def ban_user():
    user_id = request.json.get('user_id')
    conn = db.get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET walletBalance = 0 WHERE user_id = %s", (user_id,)) # Punish by draining wallet (Example)
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'User penalized.'})

# 5. SERVER LOGS VIEWER
@app.route('/api/admin/logs')
@require_role(Role.ADMIN)
def get_server_logs():
    # Simulated logs for demo
    logs = [
        {'time': '10:00:01', 'level': 'INFO', 'msg': 'Server started successfully'},
        {'time': '10:05:23', 'level': 'WARN', 'msg': 'High load detected on Station: Rajiv Chowk'},
        {'time': '10:10:45', 'level': 'INFO', 'msg': 'Backup completed'},
        {'time': '10:15:12', 'level': 'ERROR', 'msg': 'Failed payment attempt: User #402'}
    ]
    return jsonify({'success': True, 'logs': logs})

# ============================================================================
# NEW ADMIN DASHBOARD ANALYTICS ENDPOINTS
# ============================================================================

# 1. REAL-TIME DASHBOARD STATISTICS
@app.route('/api/admin/dashboard/stats', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_dashboard_stats():
    """Get comprehensive dashboard statistics"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Total revenue from non-cancelled tickets
        cursor.execute("""
            SELECT COALESCE(SUM(fare), 0) as total_revenue,
                   COUNT(*) as total_tickets
            FROM tickets WHERE cancelled = FALSE
        """)
        revenue_data = cursor.fetchone()
        
        # Total users
        cursor.execute("SELECT COUNT(*) as total_users FROM users WHERE role = 'USER'")
        user_data = cursor.fetchone()
        
        # Today's bookings
        cursor.execute("""
            SELECT COUNT(*) as today_bookings, COALESCE(SUM(fare), 0) as today_revenue
            FROM tickets 
            WHERE DATE(bookingDate) = CURDATE() AND cancelled = FALSE
        """)
        today_data = cursor.fetchone()
        
        # Yesterday's revenue for growth calculation
        cursor.execute("""
            SELECT COALESCE(SUM(fare), 0) as yesterday_revenue
            FROM tickets 
            WHERE DATE(bookingDate) = DATE_SUB(CURDATE(), INTERVAL 1 DAY) AND cancelled = FALSE
        """)
        yesterday_data = cursor.fetchone()
        
        # Calculate growth percentage
        yesterday_rev = float(yesterday_data['yesterday_revenue'] or 0)
        today_rev = float(today_data['today_revenue'] or 0)
        
        if yesterday_rev > 0:
            growth = ((today_rev - yesterday_rev) / yesterday_rev) * 100
        else:
            growth = 100 if today_rev > 0 else 0
        
        # Active tickets (upcoming)
        cursor.execute("""
            SELECT COUNT(*) as active_tickets
            FROM tickets 
            WHERE cancelled = FALSE AND travelDate >= CURDATE()
        """)
        active_data = cursor.fetchone()
        
        # Cancelled tickets count (for cancellation rate widget)
        cursor.execute("""
            SELECT COUNT(*) as cancelled_count
            FROM tickets 
            WHERE cancelled = TRUE
        """)
        cancelled_data = cursor.fetchone()
        
        # Total ALL tickets (both cancelled and not)
        cursor.execute("SELECT COUNT(*) as all_tickets FROM tickets")
        all_tickets_data = cursor.fetchone()
        
        # Today's cancellations
        cursor.execute("""
            SELECT COUNT(*) as today_cancels
            FROM tickets 
            WHERE cancelled = TRUE AND DATE(bookingDate) = CURDATE()
        """)
        today_cancels = cursor.fetchone()
        
        # Metro cards count
        cursor.execute("SELECT COUNT(*) as metro_cards FROM metro_cards")
        metro_cards_data = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'stats': {
                'total_revenue': float(revenue_data['total_revenue']),
                'total_tickets': revenue_data['total_tickets'],
                'total_users': user_data['total_users'],
                'today_bookings': today_data['today_bookings'],
                'today_revenue': float(today_data['today_revenue']),
                'revenue_growth': round(growth, 2),
                'active_tickets': active_data['active_tickets'],
                'cancelled_tickets': cancelled_data['cancelled_count'] if cancelled_data else 0,
                'all_tickets': all_tickets_data['all_tickets'] if all_tickets_data else 0,
                'today_cancellations': today_cancels['today_cancels'] if today_cancels else 0,
                'metro_cards': metro_cards_data['metro_cards'] if metro_cards_data else 0
            }
        })
    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 2. REAL-TIME REVENUE TRACKING
@app.route('/api/admin/revenue/realtime', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_revenue_realtime():
    """Get revenue trends for last 7 days"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Last 7 days revenue
        cursor.execute("""
            SELECT DATE(bookingDate) as date, 
                   COALESCE(SUM(fare), 0) as revenue,
                   COUNT(*) as bookings
            FROM tickets 
            WHERE cancelled = FALSE 
                AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY DATE(bookingDate)
            ORDER BY date ASC
        """)
        daily_revenue = cursor.fetchall()
        
        # Hourly revenue for today
        cursor.execute("""
            SELECT HOUR(bookingDate) as hour, 
                   COALESCE(SUM(fare), 0) as revenue,
                   COUNT(*) as bookings
            FROM tickets 
            WHERE cancelled = FALSE AND DATE(bookingDate) = CURDATE()
            GROUP BY HOUR(bookingDate)
            ORDER BY hour ASC
        """)
        hourly_revenue = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'daily': daily_revenue,
            'hourly': hourly_revenue
        })
    except Exception as e:
        logger.error(f"Revenue tracking error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 3. LIVE BOOKINGS FEED
@app.route('/api/admin/bookings/live', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_bookings_live():
    """Get recent bookings for live feed"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        cursor.execute("""
            SELECT ticketId, username, source, destination, 
                   passengers, fare, bookingDate, cancelled
            FROM tickets 
            ORDER BY bookingDate DESC 
            LIMIT 20
        """)
        bookings = cursor.fetchall()
        
        conn.close()
        
        # include real-time data from the in-memory booking queue (DSA Queue)
        queue_data = list(booking_queue)  # Uses Queue.__iter__
        
        return jsonify({
            'success': True,
            'bookings': bookings,
            'queueSize': booking_queue.size(),
            'recentFromQueue': queue_data[-10:]  # Last 10 from queue
        })
    except Exception as e:
        logger.error(f"Live bookings error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 4. STATION PERFORMANCE ANALYTICS
@app.route('/api/admin/stations/performance', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_stations_performance():
    """Get station usage metrics"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Top source stations
        cursor.execute("""
            SELECT source as station, 
                   COUNT(*) as trips,
                   COALESCE(SUM(passengers), 0) as total_passengers
            FROM tickets 
            WHERE cancelled = FALSE
            GROUP BY source
            ORDER BY trips DESC
            LIMIT 10
        """)
        top_sources = cursor.fetchall()
        
        # Top destination stations
        cursor.execute("""
            SELECT destination as station, 
                   COUNT(*) as trips,
                   COALESCE(SUM(passengers), 0) as total_passengers
            FROM tickets 
            WHERE cancelled = FALSE
            GROUP BY destination
            ORDER BY trips DESC
            LIMIT 10
        """)
        top_destinations = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'sources': top_sources,
            'destinations': top_destinations
        })
    except Exception as e:
        logger.error(f"Station performance error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 5. USER ANALYTICS
# FIXED VERSION - Replace in app.py around line 2154

@app.route('/api/admin/users/analytics', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_users_analytics():
    """Get user behavior insights - FIXED VERSION"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Top users by wallet balance
        cursor.execute("""
            SELECT username, walletBalance
            FROM users 
            WHERE role = 'USER'
            ORDER BY walletBalance DESC
            LIMIT 10
        """)
        top_balance = cursor.fetchall()
        
        # Top users by spending (total fare from tickets)
        cursor.execute("""
            SELECT t.username, 
                   COALESCE(SUM(t.fare), 0) as total_spent,
                   COUNT(*) as total_bookings
            FROM tickets t
            WHERE t.cancelled = FALSE
            GROUP BY t.username
            ORDER BY total_spent DESC
            LIMIT 10
        """)
        top_spenders = cursor.fetchall()
        
        # Active vs inactive users
        cursor.execute("""
            SELECT 
                COUNT(DISTINCT u.username) as total_users,
                COUNT(DISTINCT CASE WHEN t.username IS NOT NULL THEN u.username END) as active_users
            FROM users u
            LEFT JOIN tickets t ON u.username = t.username AND t.cancelled = FALSE
            WHERE u.role = 'USER'
        """)
        activity = cursor.fetchone()
        
        # User growth (count users, since we don't have createdAt column)
        cursor.execute("""
            SELECT COUNT(*) as total_users
            FROM users
            WHERE role = 'USER'
        """)
        growth = cursor.fetchone()
        
        # Most active users by booking count
        cursor.execute("""
            SELECT username, COUNT(*) as booking_count
            FROM tickets
            WHERE cancelled = FALSE
            GROUP BY username
            ORDER BY booking_count DESC
            LIMIT 5
        """)
        most_active = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'top_balance': top_balance,
            'top_spenders': top_spenders,
            'activity': activity,
            'growth': growth,
            'most_active': most_active,
            'total_users': activity['total_users'] if activity else 0,
            'active_users': activity['active_users'] if activity else 0
        })
        
    except Exception as e:
        logger.error(f"Users analytics error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False, 
            'error': str(e),
            'top_balance': [],
            'top_spenders': []
        }), 500

# 6. SYSTEM ALERTS
@app.route('/api/admin/alerts/system', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_system_alerts():
    """Get automated system alerts"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        alerts = []
        
        # Low balance users
        cursor.execute("""
            SELECT username, walletBalance
            FROM users 
            WHERE role = 'USER' AND walletBalance < 50
            ORDER BY walletBalance ASC
            LIMIT 10
        """)
        low_balance = cursor.fetchall()
        
        for user in low_balance:
            alerts.append({
                'type': 'warning',
                'category': 'Low Balance',
                'message': f"User {user['username']} has low balance: Rs. {user['walletBalance']}",
                'data': user
            })
        
        # Pending refunds (cancelled tickets)
        cursor.execute("""
            SELECT COUNT(*) as pending_refunds
            FROM tickets 
            WHERE cancelled = TRUE AND bookingDate >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """)
        refund_count = cursor.fetchone()
        
        if refund_count['pending_refunds'] > 0:
            alerts.append({
                'type': 'info',
                'category': 'Refunds',
                'message': f"{refund_count['pending_refunds']} cancelled tickets in last 7 days",
                'data': refund_count
            })
        
        # Check CPU/RAM
        try:
            cpu = psutil.cpu_percent()
            ram = psutil.virtual_memory().percent
            
            if cpu > 80:
                alerts.append({
                    'type': 'danger',
                    'category': 'System Health',
                    'message': f"High CPU usage: {cpu}%"
                })
            
            if ram > 80:
                alerts.append({
                    'type': 'danger',
                    'category': 'System Health',
                    'message': f"High RAM usage: {ram}%"
                })
        except:
            pass
        
        conn.close()
        
        return jsonify({
            'success': True,
            'alerts': alerts,
            'count': len(alerts)
        })
    except Exception as e:
        logger.error(f"System alerts error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 7. REFUND MANAGEMENT
@app.route('/api/admin/refunds/pending', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_refunds_pending():
    """Get pending refund requests"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        cursor.execute("""
            SELECT ticketId, username, source, destination, 
                   passengers, fare, bookingDate, travelDate
            FROM tickets 
            WHERE cancelled = TRUE
            ORDER BY bookingDate DESC
            LIMIT 50
        """)
        pending = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'refunds': pending
        })
    except Exception as e:
        logger.error(f"Refunds error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 8. ENHANCED LOST & FOUND
@app.route('/api/admin/lostfound/all', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_lostfound_all():
    """Get all lost items with enhanced data"""
    try:
        items = db.get_all_lost_found_items()
        return jsonify({'success': True, 'items': items})
    except Exception as e:
        logger.error(f"Lost & found error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Update lost item status
@app.route('/api/admin/lostfound/<int:item_id>/update', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_lostfound_update(item_id):
    """Update lost item status"""
    try:
        data = request.json
        status = data.get('status', 'SEARCHING')
        
        if db.update_lost_found_status(item_id, status):
            # Notify the user who reported the item
            try:
                conn2 = db.get_db_connection()
                cur2 = conn2.cursor(dictionary=True, buffered=True)
                cur2.execute("SELECT username, item FROM lost_found WHERE id = %s", (item_id,))
                row = cur2.fetchone()
                if row:
                    status_msgs = {
                        'FOUND': f"Great news! Your lost item '{row['item']}' has been FOUND! Visit the Lost & Found desk to collect it.",
                        'CLOSED': f"Your lost item report for '{row['item']}' has been CLOSED.",
                        'SEARCHING': f"We are actively searching for your lost item '{row['item']}'. Stay tuned!"
                    }
                    msg = status_msgs.get(status, f"Your lost item '{row['item']}' status updated to {status}.")
                    cur2.execute("INSERT INTO notifications (username, message) VALUES (%s, %s)", (row['username'], msg))
                    conn2.commit()
                cur2.close()
                conn2.close()
            except Exception as e:
                logger.error(f"Notification error for lost item {item_id}: {e}")
            return jsonify({'success': True, 'message': 'Status updated'})
        return jsonify({'success': False, 'error': 'Update failed'}), 500
    except Exception as e:
        logger.error(f"Lost & found update error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 9. PEAK HOURS ANALYTICS (Enhanced)
@app.route('/api/admin/analytics/peakhours', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_analytics_peakhours():
    """Get hour-by-hour booking distribution"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        cursor.execute("""
            SELECT HOUR(bookingDate) as hour, 
                   COUNT(*) as bookings,
                   COALESCE(SUM(passengers), 0) as passengers,
                   COALESCE(SUM(fare), 0) as revenue
            FROM tickets 
            WHERE cancelled = FALSE
            GROUP BY HOUR(bookingDate)
            ORDER BY hour ASC
        """)
        hourly_data = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'hourly': hourly_data
        })
    except Exception as e:
        logger.error(f"Peak hours error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 10. SUSPICIOUS ACTIVITY DETECTION
@app.route('/api/admin/security/suspicious', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_security_suspicious():
    """Detect potentially fraudulent patterns"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        suspicious = []
        
        # Multiple bookings in short time (>5 tickets in 1 hour)
        cursor.execute("""
            SELECT username, 
                   COUNT(*) as ticket_count,
                   MIN(bookingDate) as first_booking,
                   MAX(bookingDate) as last_booking,
                   COALESCE(SUM(fare), 0) as total_amount
            FROM tickets 
            WHERE bookingDate >= DATE_SUB(NOW(), INTERVAL 1 HOUR)
            GROUP BY username
            HAVING ticket_count > 5
        """)
        rapid_bookings = cursor.fetchall()
        
        for item in rapid_bookings:
            suspicious.append({
                'type': 'Rapid Bookings',
                'username': item['username'],
                'details': f"{item['ticket_count']} tickets in 1 hour",
                'amount': float(item['total_amount'])
            })
        
        # High value single transactions (>Rs. 500)
        cursor.execute("""
            SELECT ticketId, username, fare, bookingDate, source, destination
            FROM tickets 
            WHERE fare > 500 AND bookingDate >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            ORDER BY fare DESC
        """)
        high_value = cursor.fetchall()
        
        for item in high_value:
            suspicious.append({
                'type': 'High Value Transaction',
                'username': item['username'],
                'details': f"Rs. {item['fare']} ticket #{item['ticketId']}",
                'amount': float(item['fare'])
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'suspicious': suspicious,
            'count': len(suspicious)
        })
    except Exception as e:
        logger.error(f"Security check error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================================
# ADMIN ENDPOINTS - ADDITIONAL 10 FEATURES
# ============================================================================

# 11. Station Status Management
@app.route('/api/admin/stations/status', methods=['GET', 'POST'])
@require_role(Role.ADMIN)
def api_admin_stations_status():
    """Get or update station operational status using DB data"""
    try:
        if request.method == 'GET':
            conn = db.get_db_connection()
            cursor = conn.cursor(dictionary=True, buffered=True)
            
            # Use ALL-TIME ticket data to calculate station traffic
            cursor.execute("""
                SELECT 
                    sl.name as station,
                    COALESCE(dep.cnt, 0) as departures,
                    COALESCE(arr.cnt, 0) as arrivals,
                    COALESCE(dep.pax, 0) + COALESCE(arr.pax, 0) as total_passengers
                FROM station_locations sl
                LEFT JOIN (
                    SELECT source as name, COUNT(*) as cnt, SUM(passengers) as pax
                    FROM tickets WHERE cancelled = FALSE
                    GROUP BY source
                ) dep ON sl.name = dep.name
                LEFT JOIN (
                    SELECT destination as name, COUNT(*) as cnt, SUM(passengers) as pax
                    FROM tickets WHERE cancelled = FALSE
                    GROUP BY destination
                ) arr ON sl.name = arr.name
                ORDER BY (COALESCE(dep.pax, 0) + COALESCE(arr.pax, 0)) DESC
            """)
            
            stations = cursor.fetchall()
            
            # Classify traffic levels based on total passengers
            for station in stations:
                passengers = int(station['total_passengers'] or 0)
                station['total_passengers'] = passengers
                station['departures'] = int(station['departures'] or 0)
                station['arrivals'] = int(station['arrivals'] or 0)
                
                if passengers > 20:
                    station['status'] = 'crowded'
                    station['status_text'] = 'High Traffic'
                elif passengers > 8:
                    station['status'] = 'moderate'
                    station['status_text'] = 'Moderate'
                else:
                    station['status'] = 'low'
                    station['status_text'] = 'Low Traffic'
            
            conn.close()
            return jsonify({'success': True, 'stations': stations})
        
        else:  # POST - update station status
            data = request.json
            return jsonify({'success': True, 'message': 'Station status updated'})
            
    except Exception as e:
        logger.error(f"Station status error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# SEED HIGH TRAFFIC DATA FOR 5 STATIONS
@app.route('/api/admin/seed-traffic', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_seed_traffic():
    """Seed the database with high-traffic ticket data for 5 key stations"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor()
        
        # 5 high-traffic stations with realistic booking pairs
        high_traffic_pairs = [
            # (source, destination, passengers, fare)
            ('shahpur', 'kalupur_railway_station', 3, 45.0),
            ('kalupur_railway_station', 'shahpur', 2, 45.0),
            ('shahpur', 'old_high_court', 4, 35.0),
            ('old_high_court', 'shahpur', 3, 35.0),
            ('old_high_court', 'gandhigram', 2, 30.0),
            ('gandhigram', 'old_high_court', 5, 30.0),
            ('gandhigram', 'jivraj', 3, 40.0),
            ('jivraj', 'gandhigram', 4, 40.0),
            ('jivraj', 'vijay_nagar', 2, 25.0),
            ('vijay_nagar', 'jivraj', 3, 25.0),
            ('vijay_nagar', 'shahpur', 5, 55.0),
            ('shahpur', 'vijay_nagar', 4, 55.0),
            ('kalupur_railway_station', 'gandhigram', 3, 50.0),
            ('kalupur_railway_station', 'jivraj', 2, 60.0),
            ('old_high_court', 'vijay_nagar', 4, 45.0),
        ]
        
        # Get a valid username from the database
        cursor.execute("SELECT username FROM users WHERE role = 'USER' LIMIT 1")
        user_row = cursor.fetchone()
        if not user_row:
            return jsonify({'success': False, 'error': 'No users in database'}), 400
        seed_username = user_row[0]
        
        from datetime import datetime as _dt_seed, timedelta as _td_seed
        
        tickets_added = 0
        for pair in high_traffic_pairs:
            # Add multiple bookings per pair (3-5 bookings each) spread over recent dates
            for day_offset in range(5):
                booking_date = _dt_seed.now() - _td_seed(days=day_offset, hours=random.randint(0, 12))
                travel_date = booking_date + _td_seed(hours=random.randint(1, 8))
                passengers = pair[2] + random.randint(-1, 2)
                if passengers < 1:
                    passengers = 1
                fare = pair[3] * passengers
                
                cursor.execute("""
                    INSERT INTO tickets (username, source, destination, passengers, fare, 
                                        travelDate, bookingDate, cancelled, distance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s)
                """, (
                    seed_username, pair[0], pair[1], passengers, fare,
                    travel_date.strftime('%Y-%m-%d'), booking_date.strftime('%Y-%m-%d %H:%M:%S'),
                    round(random.uniform(5, 25), 2)
                ))
                tickets_added += 1
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True, 
            'message': f'Added {tickets_added} high-traffic tickets for 5 key stations',
            'stations': ['shahpur', 'kalupur_railway_station', 'old_high_court', 'gandhigram', 'jivraj', 'vijay_nagar']
        })
        
    except Exception as e:
        logger.error(f"Seed traffic error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# TOP 5 HIGH TRAFFIC STATIONS
@app.route('/api/admin/top-stations', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_top_stations():
    """Get top 5 busiest stations based on ticket data"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Query: Combine source and destination usage, count total passengers and revenue
        cursor.execute("""
            SELECT 
                station_name,
                SUM(departures) as departures,
                SUM(arrivals) as arrivals,
                SUM(total_passengers) as total_passengers,
                SUM(trips) as total_trips,
                SUM(revenue) as total_revenue
            FROM (
                SELECT 
                    source as station_name,
                    COUNT(*) as departures,
                    0 as arrivals,
                    COALESCE(SUM(passengers), 0) as total_passengers,
                    COUNT(*) as trips,
                    COALESCE(SUM(fare), 0) as revenue
                FROM tickets 
                WHERE cancelled = FALSE
                GROUP BY source
                
                UNION ALL
                
                SELECT 
                    destination as station_name,
                    0 as departures,
                    COUNT(*) as arrivals,
                    COALESCE(SUM(passengers), 0) as total_passengers,
                    COUNT(*) as trips,
                    COALESCE(SUM(fare), 0) as revenue
                FROM tickets 
                WHERE cancelled = FALSE
                GROUP BY destination
            ) as combined
            GROUP BY station_name
            ORDER BY total_passengers DESC
            LIMIT 5
        """)
        
        stations = cursor.fetchall()
        
        # Add rank and traffic level
        for i, station in enumerate(stations):
            station['rank'] = i + 1
            pax = station['total_passengers']
            if pax > 500:
                station['level'] = 'critical'
                station['level_text'] = 'Very High'
            elif pax > 200:
                station['level'] = 'high'
                station['level_text'] = 'High'
            elif pax > 50:
                station['level'] = 'moderate'
                station['level_text'] = 'Moderate'
            else:
                station['level'] = 'low'
                station['level_text'] = 'Low'
            # Convert Decimal to float for JSON
            station['total_revenue'] = float(station['total_revenue'] or 0)
            station['total_passengers'] = int(station['total_passengers'] or 0)
            station['total_trips'] = int(station['total_trips'] or 0)
            station['departures'] = int(station['departures'] or 0)
            station['arrivals'] = int(station['arrivals'] or 0)
        
        conn.close()
        return jsonify({'success': True, 'stations': stations})
        
    except Exception as e:
        logger.error(f"Top stations error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# 12. Route Analytics
@app.route('/api/admin/routes/analytics', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_routes_analytics():
    """Get route popularity and profitability analysis"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Top routes by bookings
        cursor.execute("""
            SELECT 
                CONCAT(source, ' → ', destination) as route,
                COUNT(*) as bookings,
                SUM(passengers) as total_passengers,
                SUM(fare) as total_revenue,
                AVG(fare) as avg_fare,
                AVG(distance) as avg_distance
            FROM tickets
            WHERE cancelled = FALSE
            GROUP BY source, destination
            ORDER BY bookings DESC
            LIMIT 10
        """)
        
        top_routes = cursor.fetchall()
        
        # Route profitability (revenue per km)
        cursor.execute("""
            SELECT 
                CONCAT(source, ' → ', destination) as route,
                SUM(fare) / NULLIF(SUM(distance), 0) as revenue_per_km,
                COUNT(*) as trips
            FROM tickets
            WHERE cancelled = FALSE AND distance > 0
            GROUP BY source, destination
            ORDER BY revenue_per_km DESC
            LIMIT 10
        """)
        
        profitable_routes = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'top_routes': top_routes,
            'profitable_routes': profitable_routes
        })
        
    except Exception as e:
        logger.error(f"Route analytics error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
# 13. Monthly Pass Management
@app.route('/api/admin/passes/management', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_passes_management():
    """Get monthly pass statistics and active passes"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Active passes
        cursor.execute("""
            SELECT 
                mp.*,
                u.walletBalance,
                DATEDIFF(mp.expiryDate, CURDATE()) as days_remaining
            FROM monthly_passes mp
            JOIN users u ON mp.username = u.username
            WHERE mp.expiryDate >= CURDATE()
            ORDER BY mp.expiryDate ASC
        """)
        
        active_passes = cursor.fetchall()
        
        # Pass statistics
        cursor.execute("""
            SELECT 
                COUNT(*) as total_active,
                SUM(price) as total_revenue,
                AVG(price) as avg_price,
                COUNT(CASE WHEN DATEDIFF(expiryDate, CURDATE()) <= 7 THEN 1 END) as expiring_soon
            FROM monthly_passes
            WHERE expiryDate >= CURDATE()
        """)
        
        stats = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            'success': True,
            'active_passes': active_passes,
            'statistics': stats
        })
        
    except Exception as e:
        logger.error(f"Pass management error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 14. Feedback Dashboard
@app.route('/api/admin/feedback/dashboard', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_feedback_dashboard():
    """Get feedback categorization and sentiment analysis"""
    try:
        feedbacks = db.get_all_feedbacks()
        
        # Categorize by type
        feedback_count = sum(1 for f in feedbacks if f['type'] == 'feedback')
        complaint_count = sum(1 for f in feedbacks if f['type'] == 'complaint')
        
        # Simple sentiment analysis
        sentiment = {'positive': 0, 'negative': 0, 'neutral': 0}
        pos_words = ['good', 'great', 'excellent', 'amazing', 'best', 'love', 'fast', 'clean']
        neg_words = ['bad', 'worst', 'terrible', 'slow', 'dirty', 'late', 'rude', 'poor']
        
        for f in feedbacks:
            text = f['text'].lower()
            if any(word in text for word in pos_words):
                sentiment['positive'] += 1
            elif any(word in text for word in neg_words):
                sentiment['negative'] += 1
            else:
                sentiment['neutral'] += 1
        
        # Recent feedback
        recent = feedbacks[:10] if len(feedbacks) > 10 else feedbacks
        
        return jsonify({
            'success': True,
            'total': len(feedbacks),
            'feedback_count': feedback_count,
            'complaint_count': complaint_count,
            'sentiment': sentiment,
            'recent': recent
        })
        
    except Exception as e:
        logger.error(f"Feedback dashboard error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 15. Promotions Management
@app.route('/api/admin/promotions/all', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_promotions_all():
    """Get all promotional campaigns"""
    try:
        # Mock data for promotions (in real app, create promotions table)
        promotions = [
            {
                'id': 1,
                'code': 'METRO50',
                'discount': 50,
                'type': 'percentage',
                'active': True,
                'used': 156,
                'created': '2026-01-01'
            },
            {
                'id': 2,
                'code': 'NEWUSER',
                'discount': 100,
                'type': 'flat',
                'active': True,
                'used': 89,
                'created': '2026-01-15'
            }
        ]
        
        return jsonify({
            'success': True,
            'promotions': promotions,
            'count': len(promotions)
        })
        
    except Exception as e:
        logger.error(f"Promotions error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
@app.route('/api/admin/announcements/<int:announcement_id>', methods=['DELETE'])
@require_role(Role.ADMIN)
def api_admin_delete_announcement(announcement_id):
    """Delete an announcement"""
    try:
        if db.delete_announcement(announcement_id):
            return jsonify({
                'success': True,
                'message': f'Announcement {announcement_id} deleted successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Announcement not found or already deleted'
            }), 404
            
    except Exception as e:
        logger.error(f"Delete announcement error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/promotions/create', methods=['POST'])
@require_role(Role.ADMIN)
def api_admin_promotions_create():
    """Create new promotional campaign"""
    try:
        data = request.json
        # In real app, insert into promotions table
        return jsonify({
            'success': True,
            'message': 'Promotion created successfully',
            'promotion_id': 3
        })
        
    except Exception as e:
        logger.error(f"Create promotion error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 16. Staff Metrics
@app.route('/api/admin/staff/metrics', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_staff_metrics():
    """Get staff performance metrics"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Get support staff
        cursor.execute("""
            SELECT username, walletBalance, role
            FROM users
            WHERE role = 'SUPPORT_STAFF'
        """)
        
        staff = cursor.fetchall()
        
        # Mock performance data
        for member in staff:
            member['tickets_resolved'] = random.randint(10, 50)
            member['avg_response_time'] = f"{random.randint(5, 30)} min"
            member['satisfaction_score'] = round(random.uniform(4.0, 5.0), 1)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'staff': staff,
            'total_staff': len(staff)
        })
        
    except Exception as e:
        logger.error(f"Staff metrics error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 17. Financial Reports
@app.route('/api/admin/reports/financial', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_reports_financial():
    """Generate financial reports"""
    try:
        period = request.args.get('period', 'daily')  # daily, weekly, monthly
        
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        if period == 'daily':
            # Last 7 days
            cursor.execute("""
                SELECT 
                    DATE(bookingDate) as date,
                    COUNT(*) as tickets,
                    SUM(fare) as revenue,
                    SUM(passengers) as passengers
                FROM tickets
                WHERE cancelled = FALSE AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
                GROUP BY DATE(bookingDate)
                ORDER BY date DESC
            """)
        elif period == 'weekly':
            # Last 8 weeks
            cursor.execute("""
                SELECT 
                    YEARWEEK(bookingDate) as week,
                    COUNT(*) as tickets,
                    SUM(fare) as revenue,
                    SUM(passengers) as passengers
                FROM tickets
                WHERE cancelled = FALSE AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 56 DAY)
                GROUP BY YEARWEEK(bookingDate)
                ORDER BY week DESC
            """)
        else:  # monthly
            # Last 6 months
            cursor.execute("""
                SELECT 
                    DATE_FORMAT(bookingDate, '%Y-%m') as month,
                    COUNT(*) as tickets,
                    SUM(fare) as revenue,
                    SUM(passengers) as passengers
                FROM tickets
                WHERE cancelled = FALSE AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 6 MONTH)
                GROUP BY DATE_FORMAT(bookingDate, '%Y-%m')
                ORDER BY month DESC
            """)
        
        data = cursor.fetchall()
        conn.close()
        
        return jsonify({
            'success': True,
            'period': period,
            'data': data
        })
        
    except Exception as e:
        logger.error(f"Financial reports error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 18. Notifications Management
@app.route('/api/admin/notifications/manage', methods=['GET', 'POST'])
@require_role(Role.ADMIN)
def api_admin_notifications_manage():
    """Manage system-wide notifications"""
    try:
        if request.method == 'GET':
            announcements = db.get_all_announcements()
            return jsonify({
                'success': True,
                'announcements': announcements,
                'count': len(announcements)
            })
        else:  # POST - create new announcement
            data = request.json
            message = data.get('message', '')
            
            if db.insert_announcement(message):
                return jsonify({
                    'success': True,
                    'message': 'Announcement created successfully'
                })
            else:
                return jsonify({'success': False, 'error': 'Failed to create announcement'}), 500
                
    except Exception as e:
        logger.error(f"Notifications error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 19. Capacity Planning
@app.route('/api/admin/capacity/analysis', methods=['GET'])
@require_role(Role.ADMIN)
def api_admin_capacity_analysis():
    """Get capacity planning and load analysis data"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Hourly passenger distribution
        cursor.execute("""
            SELECT 
                HOUR(bookingDate) as hour,
                SUM(passengers) as total_passengers,
                COUNT(*) as bookings,
                AVG(passengers) as avg_passengers_per_booking
            FROM tickets
            WHERE bookingDate >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            GROUP BY HOUR(bookingDate)
            ORDER BY hour
        """)
        
        hourly_load = cursor.fetchall()
        
        # Station capacity utilization
        cursor.execute("""
            SELECT 
                source as station,
                SUM(passengers) as passengers_out,
                COUNT(*) as trips_out
            FROM tickets
            WHERE bookingDate >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            GROUP BY source
            ORDER BY passengers_out DESC
            LIMIT 10
        """)
        
        station_load = cursor.fetchall()
        
        # Calculate capacity recommendations
        for item in hourly_load:
            passengers = item['total_passengers']
            if passengers > 200:
                item['recommendation'] = 'Add extra trains'
            elif passengers > 100:
                item['recommendation'] = 'Monitor closely'
            else:
                item['recommendation'] = 'Normal capacity'
        
        conn.close()
        
        return jsonify({
            'success': True,
            'hourly_load': hourly_load,
            'station_load': station_load
        })
        
    except Exception as e:
        logger.error(f"Capacity analysis error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 20. Emergency Management
@app.route('/api/admin/emergency/alerts', methods=['GET', 'POST'])
@require_role(Role.ADMIN)
def api_admin_emergency_alerts():
    """Emergency alert and incident management"""
    try:
        if request.method == 'GET':
            # Fetch real emergency announcements from DB
            all_announcements = db.get_all_announcements()
            emergency_alerts = []
            for a in all_announcements:
                msg = a.get('message', '')
                if msg.upper().startswith('EMERGENCY:'):
                    created = a.get('createdDate', '')
                    if isinstance(created, datetime):
                        created = created.strftime('%Y-%m-%d %H:%M:%S')
                    emergency_alerts.append({
                        'id': a['id'],
                        'message': msg.replace('EMERGENCY: ', '').replace('EMERGENCY:', ''),
                        'createdDate': str(created),
                        'status': 'active'
                    })
            
            return jsonify({
                'success': True,
                'incidents': emergency_alerts,
                'active_alerts': len(emergency_alerts)
            })
        
        else:  # POST - create emergency alert
            data = request.json
            message = data.get('message', '')
            
            # Broadcast to all users
            db.insert_announcement(f"EMERGENCY: {message}")
            
            return jsonify({
                'success': True,
                'message': 'Emergency alert broadcasted',
            })
            
    except Exception as e:
        logger.error(f"Emergency alerts error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/admin/emergency/alerts/<int:alert_id>', methods=['DELETE'])
@require_role(Role.ADMIN)
def api_admin_resolve_emergency(alert_id):
    """Resolve/dismiss an emergency alert"""
    try:
        db.delete_announcement(alert_id)
        return jsonify({'success': True, 'message': 'Alert resolved'})
    except Exception as e:
        logger.error(f"Resolve alert error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
    
    # In app.py


@app.route('/api/stations/info/<string:station_name>', methods=['GET'])
def api_get_station_info(station_name):
    """Get station info. If facilities are missing, AUTO-GENERATE them randomly."""
    try:
        # 1. Fetch existing details
        station = db.get_station_details(station_name)
        
        # 2. Check if station needs a facility update 
        # (If it exists but has no WiFi/ATM/Parking set, it's likely a fresh/blank entry)
        if station and not (station.get('has_wifi') or station.get('has_atm')):
            import random
            
            # Generate Random Facilities
            updates = {
                'has_wifi': random.choice([1, 1, 0]),      # 66% chance
                'has_parking': random.choice([1, 0]),      # 50% chance
                'has_restroom': 1,                         # Always True
                'has_atm': random.choice([1, 1, 0]),       # 66% chance
                'is_accessible': random.choice([1, 1, 0])  # 66% chance
            }
            
            # Update the Database immediately
            try:
                conn = db.get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE station_locations 
                    SET has_wifi=%s, has_parking=%s, has_restroom=%s, has_atm=%s, is_accessible=%s
                    WHERE name=%s
                """, (
                    updates['has_wifi'], updates['has_parking'], 
                    updates['has_restroom'], updates['has_atm'], 
                    updates['is_accessible'], station_name
                ))
                conn.commit()
                conn.close()
                
                # Update the station object to return to frontend
                station.update(updates)
                
            except Exception as e:
                logger.error(f"Auto-update error: {e}")

        # 3. Fallback for completely missing stations (Simulated Data)
        if not station:

            station = {
                'name': station_name,
                'has_wifi': random.choice([1, 0]),
                'has_parking': random.choice([1, 0]),
                'has_restroom': 1,
                'has_atm': random.choice([1, 0]),
                'is_accessible': 1,
                'contact_number': '1800-METRO-HELP',
                'status': 'Operational'
            }

        return jsonify({'success': True, 'station': station})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500    
    
@app.after_request
def add_header(response):
    """
    Add headers to force the browser to NOT cache any page.
    This prevents the 'Back' button from showing sensitive data after logout.
    """
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
    


# Helper to generate a realistic 16-digit card number
def generate_unique_card_number():
    # Starts with '9' to look like a transit card
    prefix = "9"
    # Generate 15 random digits
    suffix = ''.join([str(random.randint(0, 9)) for _ in range(15)])
    return prefix + suffix

@app.route('/api/metrocard/create', methods=['POST'])
@require_login
def api_issue_metro_card():
    """
    Manually register/issue a new MetroCard for the user.
    """
    try:
        user = get_current_user()
        username = user['username']
        
        # 1. Check if user already has a card
        existing_card = db.get_metro_card_by_username(username)
        if existing_card:
            return jsonify({
                'success': False, 
                'error': 'You already have a MetroCard registered.'
            }), 400

        # 2. Generate a new Card Number
        new_card_number = generate_unique_card_number()
        
        # 3. Insert into Database
        # Note: We use the card_number we just generated
        if db.insert_metro_card(username, 0.0, 0, 50.0, new_card_number):
            return jsonify({
                'success': True,
                'message': 'MetroCard issued successfully!',
                'card': {
                    'cardNumber': new_card_number,
                    'balance': 0.0,
                    'status': 'ACTIVE'
                }
            }), 201
        else:
            return jsonify({'success': False, 'error': 'Database failed to issue card'}), 500

    except Exception as e:
        logger.error(f"Card Issue Error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# PHASE 1-11: PLATFORM-INSPIRED IMPROVEMENT ENDPOINTS
# ============================================================================

# ── Phase 1: Notification Center ──────────────────────────────────────────────
@app.route('/api/notifications/center', methods=['GET'])
@require_login
def api_notifications_center():
    """Get grouped & categorized notifications for the notification drawer"""
    try:
        user = get_current_user()
        username = user['username']
        notifications = []

        # 1. Recent bookings → booking notifications
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("""
            SELECT ticketId, source, destination, fare, bookingDate, cancelled
            FROM tickets WHERE username=%s ORDER BY bookingDate DESC LIMIT 5
        """, (username,))
        for t in cursor.fetchall():
            bd = t['bookingDate']
            if isinstance(bd, datetime):
                bd = bd.strftime('%Y-%m-%d %H:%M')
            if t['cancelled']:
                notifications.append({
                    'id': f"tkt-{t['ticketId']}", 'category': 'booking',
                    'icon': '🚫', 'title': 'Ticket Cancelled',
                    'message': f"{t['source']} → {t['destination']} — ₹{t['fare']} refunded",
                    'time': str(bd), 'read': True
                })
            else:
                notifications.append({
                    'id': f"tkt-{t['ticketId']}", 'category': 'booking',
                    'icon': '🎫', 'title': 'Booking Confirmed',
                    'message': f"{t['source']} → {t['destination']} — ₹{t['fare']}",
                    'time': str(bd), 'read': True
                })

        # 2. Wallet activity
        cursor.execute("""
            SELECT walletBalance FROM users WHERE username=%s
        """, (username,))
        ub = cursor.fetchone()
        balance = float(ub['walletBalance']) if ub else 0
        if balance < 50:
            notifications.append({
                'id': 'wallet-low', 'category': 'wallet',
                'icon': '⚠️', 'title': 'Low Balance Alert',
                'message': f'Your wallet balance is ₹{balance:.0f}. Top up to continue booking.',
                'time': 'Now', 'read': False
            })

        # 3. System announcements
        try:
            announcements = db.get_all_announcements()
            for a in announcements[:3]:
                created = a.get('createdDate', '')
                if isinstance(created, datetime):
                    created = created.strftime('%Y-%m-%d %H:%M')
                notifications.append({
                    'id': f"ann-{a['id']}", 'category': 'system',
                    'icon': '📢', 'title': 'System Announcement',
                    'message': a['message'],
                    'time': str(created), 'read': True
                })
        except Exception:
            pass

        # 4. Monthly pass expiry warnings
        cursor.execute("""
            SELECT source, destination, expiryDate, DATEDIFF(expiryDate, CURDATE()) as days_left
            FROM monthly_passes WHERE username=%s AND expiryDate >= CURDATE()
            ORDER BY expiryDate ASC
        """, (username,))
        for mp in cursor.fetchall():
            days = mp['days_left']
            if days <= 7:
                notifications.append({
                    'id': f"pass-exp-{mp['source']}", 'category': 'alert',
                    'icon': '⏰', 'title': f'Pass Expiring in {days} day{"s" if days != 1 else ""}',
                    'message': f"{mp['source']} → {mp['destination']}",
                    'time': str(mp['expiryDate']), 'read': False
                })

        conn.close()

        unread = sum(1 for n in notifications if not n['read'])
        return jsonify({'success': True, 'notifications': notifications, 'unread_count': unread})
    except Exception as e:
        logger.error(f"Notification center error: {e}")
        return jsonify({'success': True, 'notifications': [], 'unread_count': 0})


# ── Phase 2: User Profile & Settings ─────────────────────────────────────────
@app.route('/api/user/profile', methods=['GET'])
@require_login
def api_user_profile():
    """Get comprehensive user profile with tier, stats, favorites"""
    try:
        user = get_current_user()
        username = user['username']
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        # Total trips & spending
        cursor.execute("""
            SELECT COUNT(*) as total_trips, COALESCE(SUM(fare),0) as total_spent,
                   COALESCE(SUM(distance),0) as total_km,
                   MIN(bookingDate) as first_trip
            FROM tickets WHERE username=%s AND cancelled=FALSE
        """, (username,))
        stats = cursor.fetchone()
        total_trips = int(stats['total_trips'] or 0)
        total_spent = float(stats['total_spent'] or 0)
        total_km = float(stats['total_km'] or 0)

        # Member tier
        if total_trips >= 50:
            tier = {'name': 'Gold', 'icon': '🥇', 'color': '#f59e0b'}
        elif total_trips >= 20:
            tier = {'name': 'Silver', 'icon': '🥈', 'color': '#94a3b8'}
        else:
            tier = {'name': 'Bronze', 'icon': '🥉', 'color': '#d97706'}

        # Top 3 stations
        cursor.execute("""
            SELECT station, COUNT(*) as trips FROM (
                SELECT source as station FROM tickets WHERE username=%s AND cancelled=FALSE
                UNION ALL
                SELECT destination FROM tickets WHERE username=%s AND cancelled=FALSE
            ) s GROUP BY station ORDER BY trips DESC LIMIT 3
        """, (username, username))
        fav_stations = [{'name': r['station'], 'trips': int(r['trips'])} for r in cursor.fetchall()]

        # Loyalty points & join date (handle missing columns gracefully)
        loyalty = 0
        join_date = ''
        balance = 0
        try:
            cursor.execute("SELECT walletBalance, createdAt FROM users WHERE username=%s", (username,))
            u = cursor.fetchone()
            if u:
                balance = float(u.get('walletBalance', 0) or 0)
                join_date = str(u.get('createdAt', '') or '')
            # Try to get loyaltyPoints if column exists
            try:
                cursor.execute("SELECT loyaltyPoints FROM users WHERE username=%s", (username,))
                lp = cursor.fetchone()
                if lp:
                    loyalty = int(lp.get('loyaltyPoints', 0) or 0)
            except Exception:
                loyalty = total_trips * 10  # Estimate from trips
        except Exception:
            pass

        # Preferences (handle missing column gracefully)
        prefs = {'theme': 'auto', 'notif_booking': True, 'notif_wallet': True, 'notif_system': True}
        try:
            cursor.execute("SELECT user_preferences FROM users WHERE username=%s", (username,))
            pref_row = cursor.fetchone()
            if pref_row and pref_row.get('user_preferences'):
                import json as _json
                prefs.update(_json.loads(pref_row['user_preferences']))
        except Exception:
            pass


        conn.close()

        co2_saved = round(total_km * 0.12, 1)

        return jsonify({
            'success': True,
            'profile': {
                'username': username,
                'join_date': join_date,
                'balance': balance,
                'loyalty_points': loyalty,
                'tier': tier,
                'total_trips': total_trips,
                'total_spent': round(total_spent, 2),
                'total_km': round(total_km, 1),
                'co2_saved': co2_saved,
                'favorite_stations': fav_stations,
                'preferences': prefs
            }
        })
    except Exception as e:
        logger.error(f"Profile error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/profile/preferences', methods=['PUT'])
@require_login
def api_user_preferences():
    """Save user preferences (theme, notification settings)"""
    try:
        user = get_current_user()
        data = request.json
        import json as _json
        prefs_json = _json.dumps(data)
        conn = db.get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("UPDATE users SET user_preferences=%s WHERE username=%s",
                           (prefs_json, user['username']))
            conn.commit()
        except Exception:
            # Column might not exist, add it
            cursor.execute("ALTER TABLE users ADD COLUMN user_preferences TEXT DEFAULT NULL")
            conn.commit()
            cursor.execute("UPDATE users SET user_preferences=%s WHERE username=%s",
                           (prefs_json, user['username']))
            conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Preferences saved'})
    except Exception as e:
        logger.error(f"Preferences error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Phase 3: Achievements ────────────────────────────────────────────────────
@app.route('/api/user/achievements', methods=['GET'])
@require_login
def api_user_achievements():
    """Compute and return 8 achievement badges from real user data"""
    try:
        user = get_current_user()
        username = user['username']
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        # Core stats
        cursor.execute("""
            SELECT COUNT(*) as trips, COALESCE(SUM(fare),0) as spent,
                   COALESCE(SUM(distance),0) as km,
                   COUNT(DISTINCT source) + COUNT(DISTINCT destination) as unique_stations
            FROM tickets WHERE username=%s AND cancelled=FALSE
        """, (username,))
        s = cursor.fetchone()
        trips = int(s['trips'] or 0)
        spent = float(s['spent'] or 0)
        km = float(s['km'] or 0)
        stations = int(s['unique_stations'] or 0)
        co2 = km * 0.12

        # Streak: consecutive days with bookings
        cursor.execute("""
            SELECT DISTINCT DATE(bookingDate) as d FROM tickets
            WHERE username=%s AND cancelled=FALSE ORDER BY d DESC
        """, (username,))
        dates = [r['d'] for r in cursor.fetchall()]
        streak = 0
        if dates:
            from datetime import timedelta
            streak = 1
            for i in range(1, len(dates)):
                if dates[i-1] - dates[i] == timedelta(days=1):
                    streak += 1
                else:
                    break

        # Has monthly pass?
        cursor.execute("SELECT COUNT(*) as c FROM monthly_passes WHERE username=%s", (username,))
        has_pass = int(cursor.fetchone()['c'] or 0) > 0

        # Off-peak trips count (for Night Owl badge)
        cursor.execute("""
            SELECT COUNT(*) as c FROM tickets
            WHERE username=%s AND cancelled=FALSE
            AND (HOUR(bookingDate) < 8 OR HOUR(bookingDate) > 20)
        """, (username,))
        offpeak_trips = int(cursor.fetchone()['c'] or 0)

        # Early bird trips (before 9 AM)
        cursor.execute("""
            SELECT COUNT(*) as c FROM tickets
            WHERE username=%s AND cancelled=FALSE
            AND HOUR(bookingDate) < 9
        """, (username,))
        early_trips = int(cursor.fetchone()['c'] or 0)

        # Wallet recharges count
        cursor.execute("""
            SELECT COUNT(*) as c FROM wallet_history
            WHERE username=%s AND type='CREDIT'
        """, (username,))
        recharges = int(cursor.fetchone()['c'] or 0)

        # Weekend trips
        cursor.execute("""
            SELECT COUNT(*) as c FROM tickets
            WHERE username=%s AND cancelled=FALSE
            AND DAYOFWEEK(bookingDate) IN (1, 7)
        """, (username,))
        weekend_trips = int(cursor.fetchone()['c'] or 0)

        conn.close()

        badges = [
            {'id': 'first_trip', 'name': 'First Trip', 'icon': '🚀',
             'desc': 'Book your first ticket', 'unlocked': trips >= 1,
             'progress': min(trips, 1), 'target': 1},
            {'id': 'streak', 'name': 'Streak Runner', 'icon': '🔥',
             'desc': '3+ consecutive travel days', 'unlocked': streak >= 3,
             'progress': min(streak, 3), 'target': 3},
            {'id': 'big_spender', 'name': 'Big Spender', 'icon': '💰',
             'desc': 'Spend ₹5,000+ total', 'unlocked': spent >= 5000,
             'progress': min(int(spent), 5000), 'target': 5000},
            {'id': 'explorer', 'name': 'Explorer', 'icon': '🌍',
             'desc': 'Visit 10+ unique stations', 'unlocked': stations >= 10,
             'progress': min(stations, 10), 'target': 10},
            {'id': 'eco_warrior', 'name': 'Eco Warrior', 'icon': '🌿',
             'desc': 'Save 50+ kg CO₂', 'unlocked': co2 >= 50,
             'progress': min(round(co2), 50), 'target': 50},
            {'id': 'pass_holder', 'name': 'Pass Holder', 'icon': '🎫',
             'desc': 'Purchase a monthly pass', 'unlocked': has_pass,
             'progress': 1 if has_pass else 0, 'target': 1},
            {'id': 'loyal_rider', 'name': 'Loyal Rider', 'icon': '⭐',
             'desc': 'Complete 50+ trips', 'unlocked': trips >= 50,
             'progress': min(trips, 50), 'target': 50},
            {'id': 'champion', 'name': 'Metro Champion', 'icon': '🏆',
             'desc': 'Complete 100+ trips', 'unlocked': trips >= 100,
             'progress': min(trips, 100), 'target': 100},
            {'id': 'night_owl', 'name': 'Night Owl', 'icon': '🦉',
             'desc': '5+ off-peak night trips', 'unlocked': offpeak_trips >= 5,
             'progress': min(offpeak_trips, 5), 'target': 5},
            {'id': 'early_bird', 'name': 'Early Bird', 'icon': '🐦',
             'desc': '10+ early morning trips', 'unlocked': early_trips >= 10,
             'progress': min(early_trips, 10), 'target': 10},
            {'id': 'wallet_warrior', 'name': 'Wallet Warrior', 'icon': '💳',
             'desc': 'Recharge wallet 5+ times', 'unlocked': recharges >= 5,
             'progress': min(recharges, 5), 'target': 5},
            {'id': 'weekend_explorer', 'name': 'Weekend Explorer', 'icon': '🎉',
             'desc': '10+ weekend trips', 'unlocked': weekend_trips >= 10,
             'progress': min(weekend_trips, 10), 'target': 10},
        ]
        unlocked = sum(1 for b in badges if b['unlocked'])
        return jsonify({'success': True, 'badges': badges, 'unlocked': unlocked, 'total': len(badges)})
    except Exception as e:
        logger.error(f"Achievements error: {e}")
        return jsonify({'success': True, 'badges': [], 'unlocked': 0, 'total': 12})


# ── Phase 5: Trip Comparison & Fare Calculator ───────────────────────────────
@app.route('/api/fare/compare', methods=['GET'])
@require_login
def api_fare_compare():
    """Compare metro vs cab vs auto fare for any route"""
    try:
        source = request.args.get('source', '')
        destination = request.args.get('destination', '')
        if not source or not destination or source == destination:
            return jsonify({'success': False, 'error': 'Select different source and destination'}), 400

        metro_fare, distance, travel_time_min, is_peak = calculate_dynamic_fare(source, destination, 1)
        travel_time = f'{travel_time_min} min'

        # Estimate cab/auto fares
        cab_fare = round(max(80, distance * 15 + 50), 0)  # base 50 + 15/km, min 80
        auto_fare = round(max(40, distance * 10 + 25), 0)  # base 25 + 10/km, min 40
        cab_time = round(distance * 4 + 10)  # ~4 min/km + 10 min traffic
        auto_time = round(distance * 4.5 + 12)

        metro_co2 = round(distance * 0.03, 2)   # 30g/km for metro
        cab_co2 = round(distance * 0.21, 2)      # 210g/km for car
        auto_co2 = round(distance * 0.12, 2)     # 120g/km for auto

        # Monthly pass savings
        daily_savings = round(cab_fare - metro_fare, 0)
        monthly_savings = round(daily_savings * 22, 0)  # 22 working days

        return jsonify({
            'success': True,
            'route': {'source': source, 'destination': destination, 'distance': distance},
            'metro': {'fare': metro_fare, 'time': travel_time, 'co2': metro_co2, 'is_peak': is_peak},
            'cab': {'fare': cab_fare, 'time': f'{cab_time} min', 'co2': cab_co2},
            'auto': {'fare': auto_fare, 'time': f'{auto_time} min', 'co2': auto_co2},
            'savings': {
                'vs_cab': round(cab_fare - metro_fare, 0),
                'vs_auto': round(auto_fare - metro_fare, 0),
                'monthly_vs_cab': monthly_savings,
                'co2_saved_vs_cab': round(cab_co2 - metro_co2, 2)
            }
        })
    except Exception as e:
        logger.error(f"Fare compare error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Phase 6: Group Booking ───────────────────────────────────────────────────
@app.route('/api/tickets/book-group', methods=['POST'])
@require_login
def api_book_group():
    """Book tickets for multiple named passengers in one transaction"""
    try:
        user = get_current_user()
        username = user['username']
        data = request.json
        source = data.get('source', '')
        destination = data.get('destination', '')
        travel_date = data.get('travelDate', '')
        passengers = data.get('passengers', [])  # list of {name: "..."}

        if not source or not destination or not travel_date:
            return jsonify({'success': False, 'error': 'Missing required fields'}), 400
        if not passengers or len(passengers) < 1 or len(passengers) > 5:
            return jsonify({'success': False, 'error': 'Add 1-5 passengers'}), 400

        # Calculate fare per person
        from datetime import datetime as _dt
        travel_dt = _dt.strptime(travel_date, '%Y-%m-%d').date()
        fare_per_person, distance, _time_est, _is_peak = calculate_dynamic_fare(source, destination, 1)
        total_fare = fare_per_person * len(passengers)

        # Check wallet balance
        user_obj = datastore.get_user(username)
        if not user_obj or user_obj.wallet_balance < total_fare:
            return jsonify({'success': False, 'error': f'Insufficient balance. Need ₹{total_fare}'}), 400

        # Book tickets for each passenger
        booking_ref = f"GRP-{random.randint(10000, 99999)}"
        tickets = []
        for p in passengers:
            ticket = user_obj.book_ticket(source, destination, 1, fare_per_person, travel_dt)
            if ticket:
                tickets.append({
                    'ticketId': ticket.ticket_id,
                    'passenger': p.get('name', username),
                    'source': source,
                    'destination': destination,
                    'fare': fare_per_person,
                    'travelDate': travel_date
                })

        return jsonify({
            'success': True,
            'booking_ref': booking_ref,
            'total_fare': total_fare,
            'tickets': tickets,
            'message': f'{len(tickets)} tickets booked successfully!'
        }), 201
    except Exception as e:
        logger.error(f"Group booking error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Phase 7: Spending Insights & Budget ──────────────────────────────────────
@app.route('/api/user/spending-insights', methods=['GET'])
@require_login
def api_spending_insights():
    """Get spending breakdown, trends, and savings data"""
    try:
        user = get_current_user()
        username = user['username']
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)

        # Monthly spending
        cursor.execute("""
            SELECT COALESCE(SUM(fare),0) as month_spent, COUNT(*) as month_trips,
                   COALESCE(AVG(fare),0) as avg_trip
            FROM tickets WHERE username=%s AND cancelled=FALSE
            AND MONTH(bookingDate) = MONTH(CURDATE()) AND YEAR(bookingDate) = YEAR(CURDATE())
        """, (username,))
        monthly = cursor.fetchone()

        # Daily spending last 30 days
        cursor.execute("""
            SELECT DATE(bookingDate) as day, SUM(fare) as spent
            FROM tickets WHERE username=%s AND cancelled=FALSE
            AND bookingDate >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)
            GROUP BY DATE(bookingDate) ORDER BY day
        """, (username,))
        daily_trend = [{'day': str(r['day']), 'spent': float(r['spent'])} for r in cursor.fetchall()]

        # Category breakdown
        cursor.execute("SELECT COALESCE(SUM(fare),0) as t FROM tickets WHERE username=%s AND cancelled=FALSE", (username,))
        ticket_total = float(cursor.fetchone()['t'] or 0)
        cursor.execute("SELECT COALESCE(SUM(price),0) as p FROM monthly_passes WHERE username=%s", (username,))
        pass_total = float(cursor.fetchone()['p'] or 0)

        # Off-peak savings
        cursor.execute("""
            SELECT COUNT(*) as offpeak FROM tickets
            WHERE username=%s AND cancelled=FALSE
            AND HOUR(bookingDate) NOT BETWEEN 8 AND 10
            AND HOUR(bookingDate) NOT BETWEEN 17 AND 20
        """, (username,))
        offpeak_trips = int(cursor.fetchone()['offpeak'] or 0)
        offpeak_savings = round(offpeak_trips * 5, 0)  # ~₹5 saved per off-peak trip

        # Budget
        budget = 0
        try:
            cursor.execute("SELECT user_preferences FROM users WHERE username=%s", (username,))
            pr = cursor.fetchone()
            if pr and pr.get('user_preferences'):
                import json as _json
                prefs = _json.loads(pr['user_preferences'])
                budget = prefs.get('monthly_budget', 0)
        except Exception:
            pass

        conn.close()

        return jsonify({
            'success': True,
            'month_spent': float(monthly['month_spent'] or 0),
            'month_trips': int(monthly['month_trips'] or 0),
            'avg_trip_cost': round(float(monthly['avg_trip'] or 0), 1),
            'daily_trend': daily_trend,
            'categories': {
                'tickets': round(ticket_total, 2),
                'passes': round(pass_total, 2),
                'recharges': round(ticket_total + pass_total, 2)
            },
            'budget': budget,
            'offpeak_savings': offpeak_savings
        })
    except Exception as e:
        logger.error(f"Spending insights error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/user/budget', methods=['PUT'])
@require_login
def api_set_budget():
    """Set monthly metro budget goal"""
    try:
        user = get_current_user()
        data = request.json
        budget = data.get('budget', 0)
        import json as _json

        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        try:
            cursor.execute("SELECT user_preferences FROM users WHERE username=%s", (user['username'],))
            row = cursor.fetchone()
            prefs = {}
            if row and row.get('user_preferences'):
                prefs = _json.loads(row['user_preferences'])
            prefs['monthly_budget'] = budget
            cursor.execute("UPDATE users SET user_preferences=%s WHERE username=%s",
                           (_json.dumps(prefs), user['username']))
            conn.commit()
        except Exception:
            cursor.execute("ALTER TABLE users ADD COLUMN user_preferences TEXT DEFAULT NULL")
            conn.commit()
            cursor.execute("UPDATE users SET user_preferences=%s WHERE username=%s",
                           (_json.dumps({'monthly_budget': budget}), user['username']))
            conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': f'Budget set to ₹{budget}'})
    except Exception as e:
        logger.error(f"Budget error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Phase 8: Metro Map Data ──────────────────────────────────────────────────
@app.route('/api/metro/map-data', methods=['GET'])
@require_login
def api_metro_map_data():
    """Return all stations with coordinates for SVG metro map rendering"""
    try:
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT name, x, y FROM station_locations ORDER BY name")
        stations = cursor.fetchall()

        # Group into lines based on coordinates
        blue_line = []
        red_line = []
        phase2 = []
        for s in stations:
            s['x'] = float(s['x'])
            s['y'] = float(s['y'])
            # Blue line: east-west (y varies, x ~23.03-23.05)
            if s['x'] >= 23.02 and s['x'] <= 23.06 and s['y'] >= 72.48 and s['y'] <= 72.66:
                blue_line.append(s)
            # Red line: north-south (y~72.56, x varies)
            elif s['y'] >= 72.55 and s['y'] <= 72.57:
                red_line.append(s)
            else:
                phase2.append(s)

        conn.close()
        return jsonify({
            'success': True,
            'lines': {
                'blue': sorted(blue_line, key=lambda s: s['y']),
                'red': sorted(red_line, key=lambda s: s['x']),
                'phase2': sorted(phase2, key=lambda s: s['x'])
            },
            'total_stations': len(stations)
        })
    except Exception as e:
        logger.error(f"Map data error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── Phase 9: Crowd & Weather ─────────────────────────────────────────────────
@app.route('/api/stations/crowd-status', methods=['GET'])
@require_login
def api_crowd_status():
    """Simulated crowd levels based on time-of-day and booking volume"""
    try:
        now = datetime.now()
        hour = now.hour
        is_weekday = now.weekday() < 5

        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT DISTINCT name FROM station_locations")
        stations = [r['name'] for r in cursor.fetchall()]

        # Booking volume per station (last 24h)
        cursor.execute("""
            SELECT source as station, COUNT(*) as vol FROM tickets
            WHERE bookingDate >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            AND cancelled=FALSE GROUP BY source
        """)
        volume = {r['station']: int(r['vol']) for r in cursor.fetchall()}
        conn.close()

        results = []
        for st in stations:
            vol = volume.get(st, 0)
            # Peak hours: 8-10 AM, 5-8 PM on weekdays
            if is_weekday and (8 <= hour <= 10 or 17 <= hour <= 20):
                base = 'high' if vol > 5 else 'medium'
            elif is_weekday and (7 <= hour <= 21):
                base = 'medium' if vol > 3 else 'low'
            else:
                base = 'low'

            level_map = {'low': ('🟢', '#22c55e', 'Quiet'), 'medium': ('🟡', '#f59e0b', 'Moderate'), 'high': ('🔴', '#ef4444', 'Crowded')}
            icon, color, text = level_map[base]
            results.append({'station': st, 'level': base, 'icon': icon, 'color': color, 'text': text})

        return jsonify({'success': True, 'stations': results})
    except Exception as e:
        logger.error(f"Crowd status error: {e}")
        return jsonify({'success': True, 'stations': []})


@app.route('/api/travel/weather-advisory', methods=['GET'])
@require_login
def api_weather_advisory():
    """Simulated weather-aware travel advisory"""
    try:
        now = datetime.now()
        hour = now.hour
        month = now.month

        # Simulate weather by season (Ahmedabad climate)
        if month in [6, 7, 8, 9]:  # Monsoon
            conditions = [
                ('🌧️', 'Rainy', 28, 'Heavy rain expected — metro is a great dry commute!', ''),
                ('⛈️', 'Thunderstorm', 26, 'Stormy weather — skip the traffic, take metro!', ''),
                ('🌦️', 'Light Rain', 30, 'Mild showers — metro keeps you dry and on time.', ''),
            ]
        elif month in [11, 12, 1, 2]:  # Winter
            conditions = [
                ('🌫️', 'Foggy', 18, 'Foggy morning — metro runs unaffected!', 'Expect minor road delays'),
                ('☀️', 'Clear', 22, 'Perfect winter day for your commute.', ''),
                ('🌤️', 'Pleasant', 20, 'Great weather! Enjoy your metro ride.', ''),
            ]
        else:  # Summer
            conditions = [
                ('☀️', 'Sunny & Hot', 42, 'Beat the heat — cool AC metro rides await!', 'Stay hydrated'),
                ('🔥', 'Very Hot', 45, 'Extreme heat outside — metro is fully air-conditioned.', 'Avoid outdoor travel'),
                ('🌤️', 'Warm', 38, 'Warm day — metro is the comfortable choice.', ''),
            ]

        weather = random.choice(conditions)
        # Best travel time suggestion
        if 8 <= hour <= 10 or 17 <= hour <= 20:
            best_time = 'Off-peak: Before 8 AM or after 8 PM'
        else:
            best_time = 'You\'re traveling at a great time! ✅'

        return jsonify({
            'success': True,
            'weather': {
                'icon': weather[0], 'condition': weather[1],
                'temp': weather[2], 'advisory': weather[3],
                'warning': weather[4], 'best_time': best_time
            }
        })
    except Exception as e:
        logger.error(f"Weather error: {e}")
        return jsonify({'success': True, 'weather': {'icon': '☀️', 'condition': 'Clear', 'temp': 30, 'advisory': 'Great day to travel!', 'warning': '', 'best_time': ''}})


# ============================================================================
# UNIQUE FEATURES — REAL APPLICATION ENHANCEMENTS
# ============================================================================

# ── 1. LIVE BOOKING FEED (Queue from ds.py) ──────────────────────────────────
@app.route('/api/bookings/live-feed', methods=['GET'])
def api_live_booking_feed():
    """
    Get recent bookings from the live queue (ds.py Queue).
    Returns the last N bookings for an animated ticker feed.
    """
    try:
        # Read from booking_queue without dequeuing (peek all items)
        items = []
        current = booking_queue.front
        while current:
            items.append(current.data)
            current = current.next
        
        # Return most recent first (last N items reversed)
        recent = list(reversed(items[-15:]))
        
        # Anonymize usernames for public feed
        feed = []
        for b in recent:
            uname = b.get('username', 'User')
            masked = uname[0] + '*' * (len(uname) - 2) + uname[-1] if len(uname) > 2 else uname
            feed.append({
                'id': b.get('ticketId', 0),
                'user': masked,
                'source': b.get('source', '').replace('_', ' ').title(),
                'destination': b.get('destination', '').replace('_', ' ').title(),
                'passengers': b.get('passengers', 1),
                'fare': b.get('fare', 0),
                'time': b.get('bookedAt', ''),
            })
        
        return jsonify({
            'success': True,
            'feed': feed,
            'queueSize': booking_queue.size(),
            'maxQueueSize': MAX_QUEUE_SIZE
        }), 200
    except Exception as e:
        logger.error(f"Live feed error: {e}")
        return jsonify({'success': True, 'feed': [], 'queueSize': 0}), 200


# ── 2. JOURNEY PLANNER (BFS Shortest Path using StationInfo from ds.py) ──────
@app.route('/api/journey/plan', methods=['POST'])
def api_plan_journey():
    """
    Plan a journey between two stations using station coordinates.
    Calculates intermediate stations, total distance, estimated time, and fare.
    Uses StationInfo objects from MetroDataStore.
    """
    try:
        data = request.json
        source = data.get('source', '').lower().strip()
        destination = data.get('destination', '').lower().strip()
        
        if not source or not destination:
            return jsonify({'success': False, 'error': 'Source and destination required'}), 400
        if source == destination:
            return jsonify({'success': False, 'error': 'Source and destination must be different'}), 400
        
        # Get all stations from DB with coordinates
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT name, x, y FROM station_locations ORDER BY name")
        all_stations = cursor.fetchall()
        cursor.close()
        conn.close()
        
        station_map = {s['name']: (float(s['x']), float(s['y'])) for s in all_stations}
        
        if source not in station_map:
            return jsonify({'success': False, 'error': f'Station "{source}" not found'}), 404
        if destination not in station_map:
            return jsonify({'success': False, 'error': f'Station "{destination}" not found'}), 404
        
        # Build adjacency by corridor (stations on same line = adjacent if within ~0.02 degrees)
        # East-West: similar y (latitude ~23.02-23.05), sorted by x (longitude)
        # North-South: similar x (longitude ~72.56), sorted by y (latitude)
        station_names = sorted(station_map.keys(), key=lambda s: (station_map[s][1], station_map[s][0]))
        
        # Build graph: connect each station to its nearest neighbors on the same line
        import math
        def dist(a, b):
            ax, ay = station_map[a]
            bx, by = station_map[b]
            return math.sqrt((ax - bx)**2 + (ay - by)**2)
        
        # Simple adjacency: connect each station to nearest 2-3 stations within threshold
        adjacency = {s: [] for s in station_map}
        threshold = 0.025  # ~2.5 km in coordinate difference
        
        for s1 in station_map:
            distances = []
            for s2 in station_map:
                if s1 != s2:
                    d = dist(s1, s2)
                    if d < threshold:
                        distances.append((d, s2))
            distances.sort()
            for d, s2 in distances[:3]:  # Max 3 nearest neighbors
                if s2 not in adjacency[s1]:
                    adjacency[s1].append(s2)
                if s1 not in adjacency[s2]:
                    adjacency[s2].append(s1)
        
        # BFS shortest path
        from collections import deque
        queue_bfs = deque()
        queue_bfs.append([source])
        visited = {source}
        path = None
        
        while queue_bfs:
            current_path = queue_bfs.popleft()
            current_station = current_path[-1]
            
            if current_station == destination:
                path = current_path
                break
            
            for neighbor in adjacency.get(current_station, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue_bfs.append(current_path + [neighbor])
        
        if not path:
            return jsonify({'success': False, 'error': 'No route found between these stations'}), 404
        
        # Calculate total distance (Haversine approximation)
        total_distance_km = 0
        for i in range(len(path) - 1):
            lat1, lon1 = station_map[path[i]]
            lat2, lon2 = station_map[path[i+1]]
            # Simple distance: 1 degree ≈ 111 km
            d = math.sqrt(((lat1 - lat2) * 111)**2 + (((lon1 - lon2) * 111 * math.cos(math.radians(lat1))))**2)
            total_distance_km += d
        
        # Estimate time (avg 35 km/h + 30 sec per station stop)
        travel_time_min = (total_distance_km / 35) * 60 + len(path) * 0.5
        
        # Calculate fare (base 10 + 3 per km)
        fare = round(10 + total_distance_km * 3, 2)
        
        # Format path with coordinates for visualization
        route_stations = []
        for s in path:
            coords = station_map[s]
            route_stations.append({
                'name': s.replace('_', ' ').title(),
                'id': s,
                'lat': coords[0],
                'lon': coords[1]
            })
        
        return jsonify({
            'success': True,
            'route': route_stations,
            'totalStops': len(path),
            'interchanges': 1 if 'old_high_court' in path and source != 'old_high_court' and destination != 'old_high_court' else 0,
            'distanceKm': round(total_distance_km, 2),
            'estimatedTimeMin': round(travel_time_min, 1),
            'fare': fare,
            'algorithm': 'BFS Shortest Path',
            'dataSource': 'MetroDataStore (ds.py)'
        }), 200
        
    except Exception as e:
        logger.error(f"Journey planner error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── 3. CARBON FOOTPRINT TRACKER ─────────────────────────────────────────────
@app.route('/api/eco/footprint', methods=['GET'])
@require_login
def api_eco_footprint():
    """
    Calculate user's environmental impact by choosing metro over cars/autos.
    Uses Ticket model to compute CO₂ savings per trip.
    """
    try:
        user = get_current_user()
        username = user['username']
        
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all non-cancelled tickets with distance
        cursor.execute("""
            SELECT ticketId, source, destination, passengers, fare, 
                   COALESCE(distance, 0) as distance, travelDate
            FROM tickets 
            WHERE username = %s AND cancelled = FALSE
            ORDER BY bookingDate DESC
        """, (username,))
        tickets = cursor.fetchall()
        
        # Get station distances for tickets without distance field
        cursor.execute("SELECT name, x, y FROM station_locations")
        stations = {s['name']: (float(s['x']), float(s['y'])) for s in cursor.fetchall()}
        cursor.close()
        conn.close()
        
        import math
        
        total_trips = len(tickets)
        total_distance_km = 0
        total_co2_saved_kg = 0
        total_fuel_saved_liters = 0
        monthly_breakdown = {}
        
        for t in tickets:
            dist_km = float(t['distance']) if t['distance'] > 0 else 0
            
            # Calculate distance from coordinates if not stored
            if dist_km == 0 and t['source'] in stations and t['destination'] in stations:
                lat1, lon1 = stations[t['source']]
                lat2, lon2 = stations[t['destination']]
                dist_km = math.sqrt(((lat1 - lat2) * 111)**2 + (((lon1 - lon2) * 111 * math.cos(math.radians(lat1))))**2)
            
            passengers = max(t['passengers'], 1)
            
            # CO₂ emissions per km:
            # Car: 0.21 kg/km per passenger, Metro: 0.04 kg/km per passenger
            # Savings = (car_emission - metro_emission) * distance * passengers
            car_co2 = 0.21 * dist_km * passengers
            metro_co2 = 0.04 * dist_km * passengers
            saved = car_co2 - metro_co2
            
            # Fuel savings: car averages 12 km/liter
            fuel_saved = (dist_km * passengers) / 12
            
            total_distance_km += dist_km * passengers
            total_co2_saved_kg += saved
            total_fuel_saved_liters += fuel_saved
            
            # Monthly breakdown
            travel_date = t['travelDate']
            if hasattr(travel_date, 'strftime'):
                month_key = travel_date.strftime('%Y-%m')
            else:
                month_key = str(travel_date)[:7]
            
            if month_key not in monthly_breakdown:
                monthly_breakdown[month_key] = {'co2': 0, 'trips': 0}
            monthly_breakdown[month_key]['co2'] += saved
            monthly_breakdown[month_key]['trips'] += 1
        
        # Fun equivalents
        trees_equivalent = total_co2_saved_kg / 22  # 1 tree absorbs ~22 kg CO₂/year
        phone_charges = total_co2_saved_kg / 0.008  # 1 charge ≈ 8g CO₂
        
        # Eco rank based on CO₂ saved
        if total_co2_saved_kg >= 100:
            eco_rank = '🌍 Eco Champion'
            eco_level = 5
        elif total_co2_saved_kg >= 50:
            eco_rank = '🌳 Green Warrior'
            eco_level = 4
        elif total_co2_saved_kg >= 20:
            eco_rank = '🌿 Nature Friend'
            eco_level = 3
        elif total_co2_saved_kg >= 5:
            eco_rank = '🌱 Eco Starter'
            eco_level = 2
        else:
            eco_rank = '🌾 Green Sprout'
            eco_level = 1
        
        # Monthly trend (last 6 months)
        sorted_months = sorted(monthly_breakdown.items(), reverse=True)[:6]
        trend = [{'month': m, 'co2Saved': round(d['co2'], 2), 'trips': d['trips']} 
                 for m, d in reversed(sorted_months)]
        
        return jsonify({
            'success': True,
            'eco': {
                'totalTrips': total_trips,
                'totalDistanceKm': round(total_distance_km, 1),
                'co2SavedKg': round(total_co2_saved_kg, 2),
                'fuelSavedLiters': round(total_fuel_saved_liters, 1),
                'treesEquivalent': round(trees_equivalent, 1),
                'phoneCharges': int(phone_charges),
                'ecoRank': eco_rank,
                'ecoLevel': eco_level,
                'monthlyTrend': trend
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Eco footprint error: {e}")
        return jsonify({'success': True, 'eco': {
            'totalTrips': 0, 'totalDistanceKm': 0, 'co2SavedKg': 0,
            'fuelSavedLiters': 0, 'treesEquivalent': 0, 'phoneCharges': 0,
            'ecoRank': '🌾 Green Sprout', 'ecoLevel': 1, 'monthlyTrend': []
        }}), 200


# ── 4. SMART TRAVEL RECOMMENDATIONS ────────────────────────────────────────
@app.route('/api/recommendations', methods=['GET'])
@require_login
def api_smart_recommendations():
    """
    Analyze user's booking history and provide personalized travel recommendations.
    Suggests: best times, pass savings, frequent routes, wallet tips.
    """
    try:
        user = get_current_user()
        username = user['username']
        
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get booking patterns
        cursor.execute("""
            SELECT source, destination, fare, passengers, travelDate, bookingDate,
                   HOUR(bookingDate) as booking_hour,
                   DAYNAME(travelDate) as travel_day
            FROM tickets 
            WHERE username = %s AND cancelled = FALSE
            ORDER BY bookingDate DESC
            LIMIT 100
        """, (username,))
        tickets = cursor.fetchall()
        
        # Get active monthly passes
        cursor.execute("""
            SELECT source, destination, planType, expiryDate 
            FROM monthly_passes 
            WHERE username = %s AND status = 'active' AND expiryDate >= CURRENT_DATE
        """, (username,))
        active_passes = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        tips = []
        
        if not tickets:
            tips.append({
                'icon': '🎫', 'title': 'Book Your First Trip!',
                'desc': 'Start your metro journey by booking a ticket from the dashboard.',
                'type': 'action', 'priority': 'high'
            })
            return jsonify({'success': True, 'tips': tips}), 200
        
        # 1. Find most frequent route
        route_counts = {}
        total_spent = 0
        for t in tickets:
            route = f"{t['source']}→{t['destination']}"
            route_counts[route] = route_counts.get(route, 0) + 1
            total_spent += float(t['fare'])
        
        top_route = max(route_counts, key=route_counts.get)
        top_count = route_counts[top_route]
        src, dst = top_route.split('→')
        
        # 2. Check if frequent route has a monthly pass
        has_pass_for_top = any(
            (p['source'].lower() == src.lower() and p['destination'].lower() == dst.lower()) or
            (p['source'] == 'ALL')
            for p in active_passes
        )
        
        if top_count >= 8 and not has_pass_for_top:
            avg_fare = total_spent / len(tickets)
            monthly_cost = avg_fare * top_count
            tips.append({
                'icon': '💳', 'title': 'Save with Monthly Pass!',
                'desc': f'You travel {src.replace("_"," ").title()} → {dst.replace("_"," ").title()} {top_count} times. A Basic Pass (₹999) could save you ₹{max(0, monthly_cost - 999):.0f}/month!',
                'type': 'savings', 'priority': 'high'
            })
        
        # 3. Peak hour analysis
        peak_bookings = sum(1 for t in tickets if t.get('booking_hour') and 8 <= t['booking_hour'] <= 10 or 17 <= t.get('booking_hour', 0) <= 19)
        if peak_bookings > len(tickets) * 0.6:
            tips.append({
                'icon': '⏰', 'title': 'Beat the Rush!',
                'desc': f'{int(peak_bookings/len(tickets)*100)}% of your trips are during peak hours (8-10 AM, 5-7 PM). Travel between 11 AM-4 PM for 15% lower fares and less crowding.',
                'type': 'timing', 'priority': 'medium'
            })
        
        # 4. Weekend travel pattern
        weekend_trips = sum(1 for t in tickets if t.get('travel_day') in ['Saturday', 'Sunday'])
        if weekend_trips < 2 and len(tickets) > 10:
            tips.append({
                'icon': '🌅', 'title': 'Weekend Explorer Discount',
                'desc': 'You rarely travel on weekends. Weekend fares are typically 20% lower — great for exploring the city!',
                'type': 'discovery', 'priority': 'low'
            })
        
        # 5. Wallet management
        wallet_balance = float(user.get('walletBalance', 0))
        if wallet_balance < 50:
            tips.append({
                'icon': '💰', 'title': 'Low Wallet Balance',
                'desc': f'Your balance is ₹{wallet_balance:.0f}. Recharge ₹500+ to avoid booking delays and enable auto-recharge for seamless trips.',
                'type': 'wallet', 'priority': 'high'
            })
        elif wallet_balance > 5000:
            tips.append({
                'icon': '🎁', 'title': 'Earn Rewards on Balance!',
                'desc': f'You have ₹{wallet_balance:.0f} in your wallet. Consider a Premium Pass to maximize value with unlimited trips!',
                'type': 'upgrade', 'priority': 'medium'
            })
        
        # 6. Green points reminder
        cursor2 = None
        try:
            conn2 = db.get_db_connection()
            cursor2 = conn2.cursor(dictionary=True)
            cursor2.execute("SELECT loyaltyPoints FROM users WHERE username = %s", (username,))
            row = cursor2.fetchone()
            points = row.get('loyaltyPoints', 0) if row else 0
            cursor2.close()
            conn2.close()
            
            if points >= 50:
                tips.append({
                    'icon': '🏆', 'title': f'Redeem {points} Green Points!',
                    'desc': f'You have {points} Green Points. Redeem 50 points for ₹20 wallet credit from your dashboard!',
                    'type': 'rewards', 'priority': 'high'
                })
        except:
            pass
        
        # 7. Favorite route suggestion
        if top_count >= 3:
            tips.append({
                'icon': '⭐', 'title': 'Quick Rebook',
                'desc': f'Your most traveled route is {src.replace("_"," ").title()} → {dst.replace("_"," ").title()} ({top_count} trips). Save it as a favorite for 1-tap booking!',
                'type': 'convenience', 'priority': 'low'
            })
        
        # Sort by priority
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        tips.sort(key=lambda t: priority_order.get(t['priority'], 9))
        
        return jsonify({'success': True, 'tips': tips[:6]}), 200
        
    except Exception as e:
        logger.error(f"Recommendations error: {e}")
        return jsonify({'success': True, 'tips': []}), 200


# ── 5. TRAVEL STREAKS & GAMIFICATION ────────────────────────────────────────
@app.route('/api/streaks', methods=['GET'])
@require_login
def api_travel_streaks():
    """
    Calculate user's travel streaks and gamification stats.
    Consecutive days traveled, longest streak, current streak, milestones.
    """
    try:
        user = get_current_user()
        username = user['username']
        
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Get all travel dates (unique days with bookings)
        cursor.execute("""
            SELECT DISTINCT DATE(bookingDate) as travel_day
            FROM tickets 
            WHERE username = %s AND cancelled = FALSE
            ORDER BY travel_day DESC
        """, (username,))
        travel_days = [row['travel_day'] for row in cursor.fetchall()]
        
        # Get total stats
        cursor.execute("""
            SELECT COUNT(*) as total_tickets,
                   SUM(fare) as total_spent,
                   SUM(passengers) as total_passengers,
                   COUNT(DISTINCT source) as unique_sources,
                   COUNT(DISTINCT destination) as unique_destinations
            FROM tickets WHERE username = %s AND cancelled = FALSE
        """, (username,))
        stats = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        # Calculate streaks
        current_streak = 0
        longest_streak = 0
        temp_streak = 1
        
        today = date.today()
        
        if travel_days:
            # Check if user traveled today or yesterday (for current streak)
            if travel_days[0] == today or travel_days[0] == today - timedelta(days=1):
                current_streak = 1
                for i in range(1, len(travel_days)):
                    if (travel_days[i-1] - travel_days[i]).days == 1:
                        current_streak += 1
                    else:
                        break
            
            # Calculate longest streak
            temp_streak = 1
            for i in range(1, len(travel_days)):
                if (travel_days[i-1] - travel_days[i]).days == 1:
                    temp_streak += 1
                else:
                    longest_streak = max(longest_streak, temp_streak)
                    temp_streak = 1
            longest_streak = max(longest_streak, temp_streak)
        
        total_tickets = int(stats['total_tickets'] or 0)
        total_spent = float(stats['total_spent'] or 0)
        unique_stations = int(stats.get('unique_sources', 0) or 0) + int(stats.get('unique_destinations', 0) or 0)
        
        # Milestones
        milestones = [
            {'name': 'First Ride', 'icon': '🎫', 'target': 1, 'current': total_tickets, 'unlocked': total_tickets >= 1},
            {'name': '10 Trips Club', 'icon': '🔥', 'target': 10, 'current': min(total_tickets, 10), 'unlocked': total_tickets >= 10},
            {'name': 'Century Rider', 'icon': '💯', 'target': 100, 'current': min(total_tickets, 100), 'unlocked': total_tickets >= 100},
            {'name': '3-Day Streak', 'icon': '⚡', 'target': 3, 'current': min(longest_streak, 3), 'unlocked': longest_streak >= 3},
            {'name': 'Week Warrior', 'icon': '🗓️', 'target': 7, 'current': min(longest_streak, 7), 'unlocked': longest_streak >= 7},
            {'name': 'Station Explorer', 'icon': '🗺️', 'target': 10, 'current': min(unique_stations, 10), 'unlocked': unique_stations >= 10},
            {'name': 'Big Spender', 'icon': '💎', 'target': 5000, 'current': min(int(total_spent), 5000), 'unlocked': total_spent >= 5000},
            {'name': 'Metro Legend', 'icon': '👑', 'target': 500, 'current': min(total_tickets, 500), 'unlocked': total_tickets >= 500},
        ]
        
        unlocked_count = sum(1 for m in milestones if m['unlocked'])
        
        return jsonify({
            'success': True,
            'streaks': {
                'currentStreak': current_streak,
                'longestStreak': longest_streak,
                'totalTravelDays': len(travel_days),
                'totalTickets': total_tickets,
                'totalSpent': round(total_spent, 2),
                'uniqueStations': unique_stations,
                'milestones': milestones,
                'unlockedCount': unlocked_count,
                'totalMilestones': len(milestones)
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Streaks error: {e}")
        return jsonify({'success': True, 'streaks': {
            'currentStreak': 0, 'longestStreak': 0, 'totalTravelDays': 0,
            'totalTickets': 0, 'totalSpent': 0, 'uniqueStations': 0,
            'milestones': [], 'unlockedCount': 0, 'totalMilestones': 0
        }}), 200


# ============================================================================
# PHASE 3: NEW FEATURE IMPROVEMENTS
# ============================================================================

# ── 3.1: RATE LIMITING ON AUTH ENDPOINTS ─────────────────────────────────────
_login_attempts = {}  # {ip: {'count': int, 'locked_until': datetime}}
_RATE_LIMIT_MAX = 5
_RATE_LIMIT_WINDOW = 300  # 5 minutes in seconds

def _check_rate_limit(ip_address):
    """Check if IP is rate-limited. Returns (is_blocked, remaining_seconds)."""
    now = datetime.now()
    entry = _login_attempts.get(ip_address)
    if not entry:
        return False, 0
    
    locked_until = entry.get('locked_until')
    if locked_until and now < locked_until:
        remaining = int((locked_until - now).total_seconds())
        return True, remaining
    
    # Reset if window expired
    if locked_until and now >= locked_until:
        _login_attempts.pop(ip_address, None)
        return False, 0
    
    return False, 0

def _record_failed_attempt(ip_address):
    """Record a failed login attempt for an IP."""
    now = datetime.now()
    entry = _login_attempts.get(ip_address, {'count': 0, 'locked_until': None})
    entry['count'] = entry.get('count', 0) + 1
    
    if entry['count'] >= _RATE_LIMIT_MAX:
        entry['locked_until'] = now + timedelta(seconds=_RATE_LIMIT_WINDOW)
        logger.warning(f"🔒 IP {ip_address} rate-limited after {entry['count']} failed attempts")
    
    _login_attempts[ip_address] = entry

def _clear_attempts(ip_address):
    """Clear attempts on successful login."""
    _login_attempts.pop(ip_address, None)

@app.route('/api/auth/rate-limit-status', methods=['GET'])
def api_rate_limit_status():
    """Check current rate limit status for the requesting IP."""
    ip = request.remote_addr or 'unknown'
    is_blocked, remaining = _check_rate_limit(ip)
    return jsonify({
        'success': True,
        'blocked': is_blocked,
        'remaining_seconds': remaining,
        'message': f'Try again in {remaining}s' if is_blocked else 'OK'
    }), 200


# ── 3.2: WALLET TRANSACTION HISTORY ENDPOINT ────────────────────────────────
@app.route('/api/user/wallet/history', methods=['GET'])
@require_login
def api_wallet_history():
    """Get user's full wallet transaction history with pagination."""
    try:
        user = get_current_user()
        username = user['username']
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        offset = (page - 1) * per_page
        
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Total count
        cursor.execute(
            "SELECT COUNT(*) as total FROM wallet_history WHERE username = %s",
            (username,)
        )
        total = int(cursor.fetchone()['total'] or 0)
        
        # Paginated transactions
        cursor.execute("""
            SELECT id, amount, type, description, createdAt
            FROM wallet_history 
            WHERE username = %s 
            ORDER BY createdAt DESC 
            LIMIT %s OFFSET %s
        """, (username, per_page, offset))
        
        transactions = []
        for row in cursor.fetchall():
            created = row.get('createdAt', '')
            if hasattr(created, 'strftime'):
                created = created.strftime('%Y-%m-%d %H:%M:%S')
            transactions.append({
                'id': row['id'],
                'amount': float(row['amount']),
                'type': row['type'],
                'description': row['description'],
                'date': str(created)
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'transactions': transactions,
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': max(1, (total + per_page - 1) // per_page)
        }), 200
        
    except Exception as e:
        logger.error(f"Wallet history error: {e}")
        return jsonify({'success': True, 'transactions': [], 'total': 0}), 200


# ── 3.4: TICKET QR CODE & GATE VALIDATION ───────────────────────────────────
@app.route('/api/tickets/<int:ticket_id>/qr', methods=['GET'])
@require_login
def api_ticket_qr(ticket_id):
    """Generate a scannable QR code for a ticket with validation metadata."""
    try:
        user = get_current_user()
        ticket = db.get_ticket_by_id(ticket_id)
        
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        if ticket['username'] != user['username']:
            return jsonify({'success': False, 'error': 'Not your ticket'}), 403
        
        # Build validation payload
        import hashlib
        validation_code = hashlib.sha256(
            f"{ticket_id}:{ticket['username']}:{ticket['source']}:{ticket['destination']}:metroflow_secret".encode()
        ).hexdigest()[:16].upper()
        
        qr_payload = json.dumps({
            'ticketId': ticket_id,
            'code': validation_code,
            'source': ticket['source'],
            'destination': ticket['destination'],
            'passengers': ticket['passengers'],
            'travelDate': str(ticket['travelDate']),
            'status': 'CANCELLED' if ticket['cancelled'] else 'ACTIVE',
            'validate': f'/api/tickets/validate/{validation_code}'
        })
        
        # Generate QR image
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(qr_payload)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'qr_image': f'data:image/png;base64,{qr_base64}',
            'validation_code': validation_code,
            'ticket_info': {
                'ticketId': ticket_id,
                'source': ticket['source'],
                'destination': ticket['destination'],
                'passengers': ticket['passengers'],
                'fare': float(ticket['fare']),
                'travelDate': str(ticket['travelDate']),
                'status': 'CANCELLED' if ticket['cancelled'] else 'ACTIVE'
            }
        }), 200
        
    except Exception as e:
        logger.error(f"QR generation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/tickets/validate/<string:code>', methods=['GET'])
def api_validate_ticket(code):
    """Gate validation endpoint — validates a ticket QR code."""
    try:
        import hashlib
        
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Find the ticket by regenerating validation codes
        cursor.execute("""
            SELECT ticketId, username, source, destination, passengers, 
                   fare, travelDate, cancelled, status
            FROM tickets
            WHERE cancelled = FALSE AND travelDate >= CURDATE()
            ORDER BY ticketId DESC
            LIMIT 500
        """)
        
        for ticket in cursor.fetchall():
            expected_code = hashlib.sha256(
                f"{ticket['ticketId']}:{ticket['username']}:{ticket['source']}:{ticket['destination']}:metroflow_secret".encode()
            ).hexdigest()[:16].upper()
            
            if expected_code == code.upper():
                cursor.close()
                conn.close()
                
                travel_date = ticket['travelDate']
                is_valid_today = (travel_date == date.today()) if hasattr(travel_date, '__eq__') else False
                
                return jsonify({
                    'success': True,
                    'valid': True,
                    'ticket': {
                        'ticketId': ticket['ticketId'],
                        'source': ticket['source'].replace('_', ' ').title(),
                        'destination': ticket['destination'].replace('_', ' ').title(),
                        'passengers': ticket['passengers'],
                        'fare': float(ticket['fare']),
                        'travelDate': str(travel_date),
                        'status': ticket.get('status', 'ACTIVE')
                    },
                    'validToday': is_valid_today,
                    'message': '✅ Valid ticket' if is_valid_today else '⚠️ Not valid today'
                }), 200
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'valid': False,
            'message': '❌ Invalid or expired ticket code'
        }), 404
        
    except Exception as e:
        logger.error(f"Ticket validation error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ── 3.5: ENHANCED DASHBOARD QUICK STATS ─────────────────────────────────────
@app.route('/api/user/dashboard-stats', methods=['GET'])
@require_login
def api_dashboard_stats():
    """Comprehensive dashboard stats for the greeting card — saves multiple API calls."""
    try:
        user = get_current_user()
        username = user['username']
        
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Weekly trips (last 7 days)
        cursor.execute("""
            SELECT COUNT(*) as weekly_trips, COALESCE(SUM(fare), 0) as weekly_spend
            FROM tickets 
            WHERE username = %s AND cancelled = FALSE 
            AND bookingDate >= DATE_SUB(NOW(), INTERVAL 7 DAY)
        """, (username,))
        weekly = cursor.fetchone()
        
        # Monthly spend
        cursor.execute("""
            SELECT COALESCE(SUM(fare), 0) as monthly_spend, COUNT(*) as monthly_trips
            FROM tickets 
            WHERE username = %s AND cancelled = FALSE 
            AND MONTH(bookingDate) = MONTH(CURDATE()) 
            AND YEAR(bookingDate) = YEAR(CURDATE())
        """, (username,))
        monthly = cursor.fetchone()
        
        # Next upcoming trip
        cursor.execute("""
            SELECT ticketId, source, destination, travelDate, passengers, fare
            FROM tickets 
            WHERE username = %s AND cancelled = FALSE 
            AND travelDate >= CURDATE()
            ORDER BY travelDate ASC
            LIMIT 1
        """, (username,))
        next_trip = cursor.fetchone()
        
        # Total eco stats
        cursor.execute("""
            SELECT COALESCE(SUM(distance), 0) as total_km
            FROM tickets 
            WHERE username = %s AND cancelled = FALSE
        """, (username,))
        eco = cursor.fetchone()
        total_km = float(eco['total_km'] or 0)
        co2_saved = round(total_km * 0.17, 1)  # 170g CO2/km saved vs car
        
        # Active monthly passes count
        cursor.execute("""
            SELECT COUNT(*) as active_passes
            FROM monthly_passes 
            WHERE username = %s AND status = 'active' AND expiryDate >= CURDATE()
        """, (username,))
        passes = cursor.fetchone()
        
        # Loyalty points
        loyalty = 0
        try:
            cursor.execute("SELECT loyaltyPoints FROM users WHERE username = %s", (username,))
            lp = cursor.fetchone()
            loyalty = int(lp.get('loyaltyPoints', 0) or 0) if lp else 0
        except Exception:
            pass
        
        cursor.close()
        conn.close()
        
        # Format next trip
        next_trip_data = None
        if next_trip:
            td = next_trip['travelDate']
            days_until = (td - date.today()).days if hasattr(td, '__sub__') else 0
            next_trip_data = {
                'ticketId': next_trip['ticketId'],
                'source': next_trip['source'].replace('_', ' ').title(),
                'destination': next_trip['destination'].replace('_', ' ').title(),
                'travelDate': str(td),
                'daysUntil': days_until,
                'passengers': next_trip['passengers'],
                'fare': float(next_trip['fare'])
            }
        
        # Time-aware greeting
        hour = datetime.now().hour
        if hour < 5:
            greeting = ("🌙 Late Night Owl!", "Metro runs all night for you.")
        elif hour < 12:
            greeting = ("☀️ Good Morning!", "Start your day with a smooth metro ride.")
        elif hour < 17:
            greeting = ("🌤️ Good Afternoon!", "Beat the afternoon heat — ride AC metro.")
        elif hour < 21:
            greeting = ("🌆 Good Evening!", "Heading home? Skip the traffic.")
        else:
            greeting = ("🌃 Good Night!", "Safe travels on the late metro.")
        
        is_peak = (8 <= hour < 11) or (17 <= hour < 19)
        
        return jsonify({
            'success': True,
            'stats': {
                'weeklyTrips': int(weekly['weekly_trips'] or 0),
                'weeklySpend': round(float(weekly['weekly_spend'] or 0), 2),
                'monthlyTrips': int(monthly['monthly_trips'] or 0),
                'monthlySpend': round(float(monthly['monthly_spend'] or 0), 2),
                'nextTrip': next_trip_data,
                'co2Saved': co2_saved,
                'totalKm': round(total_km, 1),
                'activePasses': int(passes['active_passes'] or 0),
                'loyaltyPoints': loyalty,
                'walletBalance': float(user.get('walletBalance', 0)),
                'greeting': greeting[0],
                'greetingSubtext': greeting[1],
                'isPeak': is_peak,
                'currentHour': hour
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Dashboard stats error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# MAIN - RUN SERVER
# ============================================================================


if __name__ == '__main__':
    print("=" * 60)
    print("Metro Ticket Booking System - Flask API")
    print("=" * 60)
    
    # Setup database
    print("\n🔧 Setting up database...")
    if db.setup_database():
        print("✅ Database setup complete!")
    
    # --- AHMEDABAD METRO STATION SEEDING ---
    print("\n📍 Checking Station Data...")
    
    conn = db.get_db_connection()
    cursor = conn.cursor()
    
    # Check if we still have the old 'Connaught Place' (Delhi) data
    cursor.execute("SELECT COUNT(*) FROM station_locations WHERE name = 'connaught_place'")
    has_old_data = cursor.fetchone()[0] > 0
    
    # Force update if old data exists or table is empty
    if has_old_data:
        print("🔄 Detected old station data. Updating to Ahmedabad Metro map...")
        cursor.execute("DELETE FROM station_locations") # Clear old stations
        conn.commit()

    # List of Stations from your Image (Name, Latitude, Longitude)
    # Coordinates are approximated to ensure accurate fare calculation
    new_stations = [
        # --- EAST-WEST CORRIDOR (BLUE LINE) ---
        ('thaltej_gam', 23.0530, 72.4800),
        ('thaltej', 23.0510, 72.4950),
        ('doordarshan_kendra', 23.0490, 72.5100),
        ('gurukul_road', 23.0470, 72.5200),
        ('gujarat_university', 23.0450, 72.5300),
        ('commerce_six_road', 23.0430, 72.5400),
        ('stadium', 23.0410, 72.5500),
        ('old_high_court', 23.0400, 72.5600), # INTERCHANGE
        ('shahpur', 23.0380, 72.5700),
        ('gheekanta', 23.0360, 72.5800),
        ('kalupur_railway_station', 23.0340, 72.5900),
        ('kankaria_east', 23.0320, 72.6000),
        ('apparel_park', 23.0300, 72.6100),
        ('amraiwadi', 23.0280, 72.6200),
        ('rabari_colony', 23.0260, 72.6300),
        ('vastral', 23.0240, 72.6400),
        ('nirant_cross_road', 23.0220, 72.6500),
        ('vastral_gam', 23.0200, 72.6600),

        # --- NORTH-SOUTH CORRIDOR (RED LINE) ---
        ('apmc', 22.9900, 72.5600),
        ('jivraj', 23.0000, 72.5600),
        ('rajiv_nagar', 23.0100, 72.5600),
        ('shreyas', 23.0200, 72.5600),  
        ('paldi', 23.0300, 72.5600),
        ('gandhigram', 23.0350, 72.5600),
        # Old High Court is already added above
        ('usmanpura', 23.0450, 72.5600),
        ('vijay_nagar', 23.0550, 72.5600),
        ('vadaj', 23.0650, 72.5600),
        ('ranip', 23.0750, 72.5600),
        ('sabarmati_railway_station', 23.0850, 72.5600),
        ('aec', 23.0950, 72.5600),
        ('sabarmati', 23.1050, 72.5600),
        ('motera_stadium', 23.1150, 72.5600),
        
        # --- PHASE 2 EXTENSION (To Gandhinagar) ---
        ('koteshwar_road', 23.1250, 72.5650),
        ('vishwakarma_college', 23.1350, 72.5700),
        ('tapovan_circle', 23.1450, 72.5750),
        ('narmada_canal', 23.1550, 72.5800),
        ('koba_circle', 23.1650, 72.5850),
        ('juna_koba', 23.1750, 72.5900),
        ('koba_gam', 23.1850, 72.5950),
        ('gnlu', 23.1950, 72.6000), # INTERCHANGE TO GIFT CITY
        ('pdeu', 23.2050, 72.6050),
        ('raysan', 23.2150, 72.6100),
        ('randesan', 23.2250, 72.6150),
        ('dholakuva_circle', 23.2350, 72.6200),
        ('infocity', 23.2450, 72.6250),
        ('sector_1', 23.2550, 72.6300),
        ('sector_10a', 23.2650, 72.6350),
        ('sachivalaya', 23.2750, 72.6400),
        ('akshardham', 23.2850, 72.6450),
        ('juna_sachivalaya', 23.2950, 72.6500),
        ('sector_16', 23.3050, 72.6550),
        ('sector_24', 23.3150, 72.6600),
        ('mahatma_mandir', 23.3250, 72.6650),

        # --- GIFT CITY BRANCH ---
        ('gift_city', 23.1950, 72.6800) # East of GNLU
    ]
    
    # Insert new stations
    for name, x, y in new_stations:
        # Using INSERT IGNORE or ON DUPLICATE KEY UPDATE to prevent errors
        cursor.execute("""
            INSERT INTO station_locations (name, x, y) 
            VALUES (%s, %s, %s) 
            ON DUPLICATE KEY UPDATE x=%s, y=%s
        """, (name, x, y, x, y))
    
    conn.commit()
    conn.close()
    print(f"✅ Loaded {len(new_stations)} stations from the Map!")
    
    # --- Populate MetroDataStore with StationInfo objects (OOP integration) ---
    print("\n📦 Initializing MetroDataStore with station data...")
    for name, x, y in new_stations:
        station_info = StationInfo(name)
        station_info.set_location(x, y)
        datastore.add_station_info(name, station_info)
    
    print(f"✅ DataStore populated: {datastore.get_total_stations()} stations in memory")
    print(f"📊 DataStore stats: {datastore.get_statistics()}")

    print("\n" + "=" * 60)
    print("🚀 Starting Flask server...")
    print("=" * 60)
    
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)
