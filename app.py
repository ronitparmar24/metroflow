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
from models import User, Admin, Feedback, Role, SupportTicketStatus
from utils import hash_password, verify_password, format_date, format_datetime
from ds import MetroDataStore, Queue

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


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_current_user() -> Optional[Dict[str, Any]]:
    """Get currently logged-in user from session"""
    username = session.get('username')
    if username:
        return db.get_user_by_username(username)
    return None


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
        
        # Get user from database
        user = db.get_user_by_username(username)
        
        if not user:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
        # Verify password (frontend sends SHA-256 hash directly)
        if password != user['password']:
            return jsonify({'success': False, 'error': 'Invalid credentials'}), 401
        
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
    """Get current logged-in user details"""
    user = get_current_user()
    if user:
        # Calculate totals for better dashboard accuracy
        return jsonify({
            'success': True,
            'user': {
                'username': user['username'],
                'walletBalance': float(user['walletBalance']), # Ensure it returns a float, not Decimal
                'role': user['role'],
                'loyaltyPoints': user.get('loyaltyPoints', 0)
            }
        }), 200
    else:
        return jsonify({'success': False, 'error': 'User not found'}), 404
# ============================================================================
# USER ROUTES (Wallet, Profile)
# ============================================================================

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


@app.route('/api/metrocard/create', methods=['POST'])
@require_login
def api_create_metro_card():
    try:
        user = get_current_user()
        username = user['username']
        


        # 1. Check existing
        if db.get_metro_card_by_username(username):
            return jsonify({'success': False, 'error': 'Card already exists'}), 400

        # 2. Insert (db.py will handle column names automatically now)
        if db.insert_metro_card(username, 0.0, 0, 50.0):
            
            # 3. Fetch immediately
            new_card = db.get_metro_card_by_username(username)
            if new_card:
                return jsonify({
                    'success': True,
                    'message': 'MetroCard Issued!',
                    'card': new_card
                })
            else:
                 return jsonify({'success': False, 'error': 'Card created but could not be fetched'}), 500
        else:
            return jsonify({'success': False, 'error': 'Database insert failed. Check server console.'}), 500

    except Exception as e:
        logger.error(f"Metro card API error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
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
    try:
        data = request.json
        source = data.get('source', '').lower().strip()
        destination = data.get('destination', '').lower().strip()
        passengers = int(data.get('passengers', 1))
        travel_date_str = data.get('travelDate', '')
        
        # 1. Validation
        if not source or not destination:
            return jsonify({'success': False, 'error': 'Source and destination required'}), 400
        
        if source == destination:
            return jsonify({'success': False, 'error': 'Source and destination must be different'}), 400
        
        if passengers < 1 or passengers > 6:
            return jsonify({'success': False, 'error': 'Passengers must be between 1 and 6'}), 400
        
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
        
        # 4. Check wallet balance (against possibly-discounted fare)
        if fare > user['walletBalance']:
            return jsonify({
                'success': False,
                'error': f'Insufficient balance. Required: Rs. {fare:.2f}, Available: Rs. {user["walletBalance"]:.2f}'
            }), 400
        
        # 5. Deduct from wallet
        new_balance = user['walletBalance'] - fare
        if not db.update_user_wallet_balance(user['username'], new_balance):
            return jsonify({'success': False, 'error': 'Failed to update wallet balance'}), 500
        
        # 6. Insert ticket (with travel time for QR gate validation)
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
            travel_time_val
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
                    'time': time,        # Optional: Send est. time back
                    'is_peak': is_peak   # Optional: Send peak status back
                },
                'newBalance': new_balance,
                'autoRecharged': auto_recharged,
                'passApplied': pass_applied,
                'passDiscount': pass_discount,
                'originalFare': original_fare,
                'passId': matched_pass_id,
                'passPlanType': matched_plan_type
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
        
        # Get ticket
        ticket = db.get_ticket_by_id(ticket_id)
        
        if not ticket:
            return jsonify({'success': False, 'error': 'Ticket not found'}), 404
        
        if ticket['username'] != user['username']:
            return jsonify({'success': False, 'error': 'This ticket does not belong to you'}), 403
        
        if ticket['cancelled']:
            return jsonify({'success': False, 'error': 'Ticket already cancelled'}), 400
        
        # Calculate refund
        travel_datetime = datetime.combine(ticket['travelDate'], datetime.min.time())
        time_diff = travel_datetime - datetime.now()
        hours_before = max(time_diff.total_seconds() / 3600, 0)
        
        if hours_before >= 24:
            refund_rate = 0.8
            charge_reason = 'Standard cancellation (24+ hours before travel)'
        else:
            refund_rate = 0.5
            charge_reason = 'Late cancellation (less than 24 hours before travel)'
        
        original_fare = ticket['fare']
        cancellation_charge = round(original_fare * (1 - refund_rate), 2)
        refund = round(original_fare * refund_rate, 2)
        
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
            # If it's a complaint, create a support ticket
            if feedback_type == 'complaint':
                db.insert_support_ticket(feedback_id, SupportTicketStatus.OPEN)
            
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
    """Get metro card details (Creates one if missing)"""
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
            auto_recharge_value = card.get('autoRechargeEnabled', 0)
            is_auto = auto_recharge_value == 1 or auto_recharge_value is True
            
            return jsonify({
                'success': True,
                'card': {
                    'cardNumber': card.get('cardNumber'),
                    'balance': float(card.get('balance', 0)),
                    'autoRechargeEnabled': is_auto, 
                    'minBalanceThreshold': float(card.get('minBalanceThreshold', 50))
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
    """Get all users (Admin only)"""
    try:
        users = db.get_all_users()
        
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
    """Remove a user (Admin only)"""
    try:
        current_user = get_current_user()
        
        if username == current_user['username']:
            return jsonify({'success': False, 'error': 'Cannot delete yourself'}), 400
        
        if db.remove_user(username):
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
    Add a new station (Admin only)
    
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
        
        if db.insert_or_update_station_location(name, x, y):
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
    Add system announcement (Admin only)
    
    Request JSON:
        {"message": "string"}
    """
    try:
        data = request.json
        message = data.get('message', '').strip()
        
        if not message:
            return jsonify({'success': False, 'error': 'Message required'}), 400
        
        if db.insert_announcement(message):
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

@app.route('/api/announcements', methods=['GET'])
def api_get_announcements():
    """Get all announcements"""
    try:
        announcements = db.get_all_announcements()
        
        formatted = []
        for ann in announcements:
            formatted.append({
                'id': ann['id'],
                'message': ann['message'],
                'createdDate': format_datetime(ann['createdDate'])
            })
        
        return jsonify({
            'success': True,
            'announcements': formatted
        }), 200
        
    except Exception as e:
        logger.error(f"Get announcements error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.route('/api/health', methods=['GET'])
def api_health_check():
    """Health check endpoint"""
    return jsonify({
        'success': True,
        'message': 'Metro Backend API is running',
        'version': '1.0.0'
    }), 200


@app.route('/', methods=['GET'])
def api_root():
    """Root endpoint"""
    return jsonify({
        'message': 'Metro Ticket Booking System API',
        'version': '1.0.0',
        'endpoints': {
            'auth': '/api/register, /api/login, /api/logout',
            'tickets': '/api/tickets/*',
            'feedback': '/api/feedback/*',
            'admin': '/api/admin/*',
            'health': '/api/health'
        }
    }), 200


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
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'analytics': {
                'total_spent': float(totals['total_spent'] or 0),
                'total_bookings': totals['total_bookings'] or 0,
                'total_distance': float(totals['total_distance'] or 0), # Real Distance
                'monthly_spending': monthly,
                'favorite_routes': routes
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
        return jsonify({'success': True, 'favorites': []})

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



@app.route('/api/lostfound/my', methods=['GET'])
@require_login
def get_my_lost_reports():
    try:
        user = get_current_user()
        conn = db.get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT * FROM lost_found WHERE username = %s ORDER BY reportDate DESC", (user['username'],))
        reports = cursor.fetchall()
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
def api_admin_peak_hours():
    return jsonify({'success': True, 'data': db.get_peak_hour_stats()})

@app.route('/api/admin/analytics/sentiment', methods=['GET'])
def api_admin_sentiment():
    return jsonify({'success': True, 'data': db.get_feedback_sentiment()})

@app.route('/api/admin/staff/add', methods=['POST'])
def api_admin_add_staff():
    data = request.json
    hashed = hash_password(data['password'])
    if db.create_staff_user(data['username'], hashed):
        return jsonify({'success': True})
    return jsonify({'success': False, 'message': 'User exists'})

@app.route('/api/admin/pricing/surge', methods=['POST'])
def api_admin_surge():
    # In a real app, save this to a 'config' table. 
    # Here we just acknowledge it for the UI demo.
    data = request.json
    return jsonify({'success': True, 'multiplier': data['multiplier']})

@app.route('/api/admin/tickets/all', methods=['GET'])
def api_admin_all_tickets():
    return jsonify({'success': True, 'tickets': db.get_all_tickets_full()})

@app.route('/api/admin/station/status', methods=['POST'])
def api_admin_station_status():
    data = request.json
    db.toggle_station_status(data['name'], data['status'])
    return jsonify({'success': True})
    
# 1. CCTV & INFRASTRUCTURE
@app.route('/api/admin/infra/cctv', methods=['GET'])
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
def update_system_config():
    data = request.json
    if 'peak_pricing' in data: system_config['peak_pricing'] = data['peak_pricing']
    if 'maintenance_mode' in data: system_config['maintenance_mode'] = data['maintenance_mode']
    return jsonify({'success': True, 'config': system_config})

@app.route('/api/admin/config/get')
def get_system_config():
    return jsonify({'success': True, 'config': system_config})

# 3. BULK REFUND ACTION
@app.route('/api/admin/refunds/approve_all', methods=['POST'])
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
        
        # Get a valid user_id from the database
        cursor.execute("SELECT userId FROM users LIMIT 1")
        user_row = cursor.fetchone()
        if not user_row:
            return jsonify({'success': False, 'error': 'No users in database'}), 400
        user_id = user_row[0]
        
        import uuid
        from datetime import datetime, timedelta
        
        tickets_added = 0
        for pair in high_traffic_pairs:
            # Add multiple bookings per pair (3-5 bookings each) spread over recent dates
            for day_offset in range(5):
                booking_date = datetime.now() - timedelta(days=day_offset, hours=random.randint(0, 12))
                travel_date = booking_date + timedelta(hours=random.randint(1, 8))
                ticket_id = str(uuid.uuid4())[:8].upper()
                passengers = pair[2] + random.randint(-1, 2)
                if passengers < 1:
                    passengers = 1
                fare = pair[3] * passengers
                
                cursor.execute("""
                    INSERT INTO tickets (ticketId, userId, source, destination, passengers, fare, 
                                        travelDate, bookingDate, cancelled, distance)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, FALSE, %s)
                """, (
                    ticket_id, user_id, pair[0], pair[1], passengers, fare,
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

    print("\n" + "=" * 60)
    print("🚀 Starting Flask server...")
    print("=" * 60)
    
    # Run Flask app
    app.run(debug=True, host='0.0.0.0', port=5000)