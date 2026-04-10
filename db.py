"""
Database Manager Module
-----------------------
Handles all MySQL database operations for Metro Ticket Booking System.
"""

import mysql.connector
from mysql.connector import Error
from typing import List, Dict, Optional, Set, Any
from datetime import datetime, date
import logging

from config import Config

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# SIMPLE CONNECTION MANAGER (No pooling to avoid errors)
# ============================================================================

def get_db_connection():
    """Get a simple database connection. Auto-creates the database if missing."""
    try:
        conn = mysql.connector.connect(**Config.get_db_config())
        return conn
    except Error as e:
        # Auto-create database if it doesn't exist (error 1049)
        if e.errno == 1049:
            try:
                db_config = Config.get_db_config().copy()
                db_name = db_config.pop('database')
                db_config.pop('raise_on_warnings', None)
                conn = mysql.connector.connect(**db_config)
                cursor = conn.cursor()
                cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
                conn.commit()
                cursor.close()
                conn.close()
                logger.info(f"✅ Auto-created database '{db_name}'")
                # Reconnect with the new database
                return mysql.connector.connect(**Config.get_db_config())
            except Error as create_err:
                logger.error(f"❌ Failed to auto-create database: {create_err}")
                raise
        logger.error(f"❌ Database connection error: {e}")
        raise


from contextlib import contextmanager

@contextmanager
def get_db_cursor(dictionary=True, buffered=True):
    """Context manager for safe DB access. Auto-closes cursor and connection.
    
    Usage:
        with get_db_cursor() as (conn, cursor):
            cursor.execute("SELECT ...")
            results = cursor.fetchall()
            conn.commit()  # if writing
    """
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=dictionary, buffered=buffered)
    try:
        yield conn, cursor
    finally:
        try:
            cursor.close()
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass


# ============================================================================
# DATABASE SETUP
# ============================================================================

def setup_database():
    """
    Setup database tables if they don't exist
    Call this once when starting the application
    """
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # USERS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username VARCHAR(50) PRIMARY KEY,
                password VARCHAR(100) NOT NULL,
                walletBalance DOUBLE NOT NULL,
                role VARCHAR(20) NOT NULL
            )
        """)
        
        # TICKETS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                ticketId INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                source VARCHAR(50) NOT NULL,
                destination VARCHAR(50) NOT NULL,
                passengers INT NOT NULL,
                fare DOUBLE NOT NULL,
                travelDate DATE NOT NULL,
                cancelled BOOLEAN NOT NULL,
                status VARCHAR(20) DEFAULT 'ACTIVE',
                bookingDate DATETIME NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # FEEDBACKS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS feedbacks (
                feedbackId INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                text VARCHAR(255) NOT NULL,
                type VARCHAR(20) NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # SUPPORT TICKETS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS support_tickets (
                ticketId INT AUTO_INCREMENT PRIMARY KEY,
                feedbackId INT NOT NULL,
                status VARCHAR(20) NOT NULL,
                assignedStaffUsername VARCHAR(50),
                createdDate DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolvedDate DATETIME,
                FOREIGN KEY (feedbackId) REFERENCES feedbacks(feedbackId) ON DELETE CASCADE,
                FOREIGN KEY (assignedStaffUsername) REFERENCES users(username) ON DELETE SET NULL
            )
        """)
        
        # ANNOUNCEMENTS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id INT AUTO_INCREMENT PRIMARY KEY,
                message VARCHAR(255) NOT NULL,
                createdDate DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # METRO CARDS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS metro_cards (
                cardNumber INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                balance DOUBLE NOT NULL,
                autoRechargeEnabled BOOLEAN NOT NULL,
                minBalanceThreshold DOUBLE NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # MONTHLY PASSES TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS monthly_passes (
                passId INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) NOT NULL,
                source VARCHAR(50) NOT NULL,
                destination VARCHAR(50) NOT NULL,
                purchaseDate DATE NOT NULL,
                expiryDate DATE NOT NULL,
                price DOUBLE NOT NULL,
                FOREIGN KEY (username) REFERENCES users(username) ON DELETE CASCADE
            )
        """)
        
        # STATION LOCATIONS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS station_locations (
                name VARCHAR(50) PRIMARY KEY,
                x DOUBLE,
                y DOUBLE,
                has_wifi BOOLEAN DEFAULT FALSE,
                has_parking BOOLEAN DEFAULT FALSE,
                has_restroom BOOLEAN DEFAULT FALSE,
                has_atm BOOLEAN DEFAULT FALSE,
                is_accessible BOOLEAN DEFAULT FALSE,
                contact_number VARCHAR(15) DEFAULT '1800-11-2233'
            )
        """)
        
        # LOST & FOUND TABLE
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
        
        # NOTIFICATIONS TABLE
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50),
                message VARCHAR(255),
                is_read BOOLEAN DEFAULT FALSE,
                date DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # WALLET HISTORY TABLE
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
        
        # MIGRATION: If table exists but cols don't, add them (Safe Migration)
        try:
            cursor.execute("ALTER TABLE station_locations ADD COLUMN has_wifi BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN has_parking BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN has_restroom BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN has_atm BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN is_accessible BOOLEAN DEFAULT FALSE")
            cursor.execute("ALTER TABLE station_locations ADD COLUMN contact_number VARCHAR(15) DEFAULT '1800-11-2233'")
        except:
            pass # Columns likely exist
        
        # Migration: Add status column to tickets table
        try:
            cursor.execute("ALTER TABLE tickets ADD COLUMN status VARCHAR(20) DEFAULT 'ACTIVE'")
            # Retroactively mark all cancelled tickets as REFUNDED
            cursor.execute("UPDATE tickets SET status = 'REFUNDED' WHERE cancelled = TRUE AND (status IS NULL OR status = 'ACTIVE')")
            logger.info("✅ Added status column to tickets table and marked cancelled tickets as REFUNDED")
        except:
            pass  # Column likely exists already
        
        # Migration: Add last_login column to users table
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN last_login DATETIME DEFAULT NULL")
            logger.info("✅ Added last_login column to users table")
        except:
            pass  # Column likely exists already
        
        # Migration: Add email column to users table
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN email VARCHAR(100) DEFAULT NULL")
            logger.info("✅ Added email column to users table")
        except:
            pass  # Column likely exists already
        
        # Migration: Add planType and status columns to monthly_passes table
        try:
            cursor.execute("ALTER TABLE monthly_passes ADD COLUMN planType VARCHAR(20) DEFAULT 'basic'")
            logger.info("✅ Added planType column to monthly_passes table")
        except:
            pass  # Column likely exists already
        try:
            cursor.execute("ALTER TABLE monthly_passes ADD COLUMN status VARCHAR(20) DEFAULT 'active'")
            logger.info("✅ Added status column to monthly_passes table")
        except:
            pass  # Column likely exists already
        # Auto-expire old passes
        try:
            cursor.execute("UPDATE monthly_passes SET status = 'expired' WHERE expiryDate < CURRENT_DATE AND status = 'active'")
        except:
            pass
        
        # Migration: Add tripsUsed column to monthly_passes table
        try:
            cursor.execute("ALTER TABLE monthly_passes ADD COLUMN tripsUsed INT DEFAULT 0")
            logger.info("✅ Added tripsUsed column to monthly_passes table")
        except:
            pass  # Column likely exists already
        
        # Migration: Add ticketClass, coachPreference, paymentMethod to tickets table
        for col_name, col_def in [
            ('ticketClass', "VARCHAR(20) DEFAULT 'standard'"),
            ('coachPreference', "VARCHAR(20) DEFAULT 'general'"),
            ('paymentMethod', "VARCHAR(20) DEFAULT 'wallet'"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE tickets ADD COLUMN {col_name} {col_def}")
                logger.info(f"✅ Added {col_name} column to tickets table")
            except:
                pass  # Column likely exists already
        
        conn.commit()
        cursor.close()
        logger.info("✅ All database tables created successfully")
        return True
        
    except Error as e:
        logger.error(f"❌ Error creating tables: {e}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_station_details(station_name):
    """Get full facility details for a specific station"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT * FROM station_locations WHERE name = %s"
        cursor.execute(sql, (station_name,))
        station = cursor.fetchone()
        cursor.close()
        return station
    except Exception as e:
        logger.error(f"Error fetching station details: {e}")
        return None
    finally:
        if conn and conn.is_connected(): conn.close()
# ============================================================================
# USER OPERATIONS
# ============================================================================

def insert_user(username: str, password_hash: str, wallet_balance: float, role: str, email: str = None) -> bool:
    """Insert new user into the users table"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        if email:
            sql = "INSERT INTO users (username, password, walletBalance, role, email) VALUES (%s, %s, %s, %s, %s)"
            cursor.execute(sql, (username, password_hash, wallet_balance, role, email))
        else:
            sql = "INSERT INTO users (username, password, walletBalance, role) VALUES (%s, %s, %s, %s)"
            cursor.execute(sql, (username, password_hash, wallet_balance, role))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ User '{username}' inserted successfully")
        return success
        
    except Error as e:
        logger.error(f"❌ Error inserting user '{username}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def username_exists(username: str) -> bool:
    """Check if a username exists in the database"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "SELECT 1 FROM users WHERE username = %s"
        cursor.execute(sql, (username,))
        exists = cursor.fetchone() is not None
        cursor.close()
        return exists
        
    except Error as e:
        logger.error(f"❌ Error checking username '{username}': {e}")
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    """Get user details safely, handling database hiccups"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        try:
            sql = "SELECT username, password, walletBalance, role, loyaltyPoints FROM users WHERE username = %s"
            cursor.execute(sql, (username,))
            user = cursor.fetchone()
        except Exception as e:
            logger.warning(f"Recovering from DB error for {username}: {e}")
            try:
                cursor.close()
                cursor = conn.cursor(dictionary=True, buffered=True)
                sql = "SELECT username, password, walletBalance, role FROM users WHERE username = %s"
                cursor.execute(sql, (username,))
                user = cursor.fetchone()
            except:
                return None
            
        cursor.close()
        return user
        
    except Exception as e:
        logger.error(f"Critical Error fetching user '{username}': {e}")
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()
def remove_user(username: str) -> bool:
    """Remove a user by username"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "DELETE FROM users WHERE username = %s"
        cursor.execute(sql, (username,))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ User '{username}' removed")
        return success
        
    except Error as e:
        logger.error(f"❌ Error removing user '{username}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def update_user_wallet_balance(username: str, new_balance: float) -> bool:
    """Update user wallet balance"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE users SET walletBalance = %s WHERE username = %s"
        cursor.execute(sql, (new_balance, username))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating wallet balance for '{username}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def update_user_password(username: str, new_hashed_password: str) -> bool:
    """Update user password"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE users SET password = %s WHERE username = %s"
        cursor.execute(sql, (new_hashed_password, username))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ Password updated for user '{username}'")
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating password for '{username}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_users() -> List[Dict[str, Any]]:
    """Retrieve list of all users with role USER"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT username, password, walletBalance, role FROM users WHERE role = 'USER'"
        cursor.execute(sql)
        users = cursor.fetchall()
        cursor.close()
        return users
        
    except Error as e:
        logger.error(f"❌ Error fetching all users: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# TICKET OPERATIONS
# ============================================================================


def insert_ticket(username: str, source: str, destination: str, passengers: int, fare: float, travel_date: date, distance: float = 0.0, cancelled: bool = False, travel_time: str = 'now', ticket_class: str = 'standard', coach_preference: str = 'general', payment_method: str = 'wallet') -> int:
    """Insert ticket with DISTANCE, TRAVEL TIME, CLASS, COACH, and PAYMENT METHOD. Return ticketId."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = """
            INSERT INTO tickets 
            (username, source, destination, passengers, fare, travelDate, distance, cancelled, bookingDate, travelTime, ticketClass, coachPreference, paymentMethod) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, %s, %s, %s)
        """
        cursor.execute(sql, (username, source, destination, passengers, fare, travel_date, distance, cancelled, travel_time, ticket_class, coach_preference, payment_method))
        conn.commit()
        ticket_id = cursor.lastrowid
        cursor.close()
        return ticket_id
        
    except Error as e:
        logger.error(f"❌ Error inserting ticket: {e}")
        if conn: conn.rollback()
        return -1
    finally:
        if conn and conn.is_connected(): conn.close()
        
def get_tickets_by_user(username: str) -> List[Dict[str, Any]]:
    """Retrieve list of tickets for a user"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT * FROM tickets WHERE username = %s ORDER BY bookingDate DESC"
        cursor.execute(sql, (username,))
        tickets = cursor.fetchall()
        cursor.close()
        return tickets
        
    except Error as e:
        logger.error(f"❌ Error fetching tickets for '{username}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def cancel_ticket(ticket_id: int) -> bool:
    """Mark a ticket as cancelled"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE tickets SET cancelled = TRUE, status = 'REFUNDED' WHERE ticketId = %s"
        cursor.execute(sql, (ticket_id,))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ Ticket #{ticket_id} cancelled")
        return success
        
    except Error as e:
        logger.error(f"❌ Error cancelling ticket #{ticket_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_ticket_by_id(ticket_id: int) -> Optional[Dict[str, Any]]:
    """Get ticket details by ID"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT * FROM tickets WHERE ticketId = %s"
        cursor.execute(sql, (ticket_id,))
        ticket = cursor.fetchone()
        cursor.close()
        return ticket
        
    except Error as e:
        logger.error(f"❌ Error fetching ticket #{ticket_id}: {e}")
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# FEEDBACK OPERATIONS
# ============================================================================

def insert_feedback(username: str, text: str, feedback_type: str) -> int:
    """Insert feedback and return generated feedbackId"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO feedbacks (username, text, type) VALUES (%s, %s, %s)"
        cursor.execute(sql, (username, text, feedback_type))
        conn.commit()
        feedback_id = cursor.lastrowid
        cursor.close()
        
        if feedback_id > 0:
            logger.info(f"✅ Feedback #{feedback_id} created by '{username}'")
        return feedback_id
        
    except Error as e:
        logger.error(f"❌ Error inserting feedback: {e}")
        if conn:
            conn.rollback()
        return -1
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_feedbacks_by_username(username: str) -> List[Dict[str, Any]]:
    """Get all feedbacks by a user"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT feedbackId, username, text, type, timestamp FROM feedbacks WHERE username = %s ORDER BY timestamp DESC"
        cursor.execute(sql, (username,))
        feedbacks = cursor.fetchall()
        cursor.close()
        return feedbacks
        
    except Error as e:
        logger.error(f"❌ Error fetching feedbacks for '{username}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_feedbacks() -> List[Dict[str, Any]]:
    """Get all feedbacks"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT feedbackId, username, text, type, timestamp FROM feedbacks ORDER BY timestamp DESC"
        cursor.execute(sql)
        feedbacks = cursor.fetchall()
        cursor.close()
        return feedbacks
        
    except Error as e:
        logger.error(f"❌ Error fetching all feedbacks: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# SUPPORT TICKET OPERATIONS
# ============================================================================

def insert_support_ticket(feedback_id: int, status: str) -> int:
    """Insert support ticket and return ticketId"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO support_tickets (feedbackId, status) VALUES (%s, %s)"
        cursor.execute(sql, (feedback_id, status))
        conn.commit()
        ticket_id = cursor.lastrowid
        cursor.close()
        
        if ticket_id > 0:
            logger.info(f"✅ Support ticket #{ticket_id} created")
        return ticket_id
        
    except Error as e:
        logger.error(f"❌ Error inserting support ticket: {e}")
        if conn:
            conn.rollback()
        return -1
    finally:
        if conn and conn.is_connected():
            conn.close()


def update_support_ticket_status(ticket_id: int, status: str, resolved_date: Optional[datetime] = None) -> bool:
    """Update support ticket status"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE support_tickets SET status = %s, resolvedDate = %s WHERE ticketId = %s"
        cursor.execute(sql, (status, resolved_date, ticket_id))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating support ticket #{ticket_id}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_assigned_tickets_by_staff(staff_username: str) -> List[Dict[str, Any]]:
    """Get support tickets assigned to a staff member"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = """
            SELECT st.ticketId, st.status, st.createdDate, st.resolvedDate,
                   fb.username, fb.text, fb.type
            FROM support_tickets st
            JOIN feedbacks fb ON st.feedbackId = fb.feedbackId
            WHERE st.assignedStaffUsername = %s
            ORDER BY st.createdDate DESC
        """
        cursor.execute(sql, (staff_username,))
        tickets = cursor.fetchall()
        cursor.close()
        return tickets
        
    except Error as e:
        logger.error(f"❌ Error fetching assigned tickets: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def insert_lost_found(username: str, item: str, description: str) -> bool:
    """Insert a lost item report into the correct table"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO lost_found (username, item, description, status, reportDate) VALUES (%s, %s, %s, 'SEARCHING', NOW())"
        cursor.execute(sql, (username, item, description))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
    except Error as e:
        logger.error(f"❌ Error inserting lost item: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): conn.close()


# ============================================================================
# METRO CARD OPERATIONS
# ============================================================================



def insert_metro_card(username, balance, auto_recharge, min_threshold, card_number=None):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            INSERT INTO metro_cards (username, balance, autoRechargeEnabled, minBalanceThreshold)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(sql, (username, balance, auto_recharge, min_threshold))
        conn.commit()
        cursor.close()
        return True
    except Error as e:
        logger.error(f"Error inserting metro card: {e}")
        if conn: conn.rollback()
        return False
    finally:
        if conn and conn.is_connected(): conn.close()

def get_metro_card_by_username(username):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT * FROM metro_cards WHERE username = %s", (username,))
        card = cursor.fetchone()
        cursor.close()
        
        if card:
            return {
                'cardNumber': card['cardNumber'],
                'username': card['username'],
                'balance': card['balance'],
                'autoRechargeEnabled': card['autoRechargeEnabled'],
                'minBalanceThreshold': card['minBalanceThreshold']
            }
        return None
    except Error as e:
        logger.error(f"Error fetching metro card for '{username}': {e}")
        return None
    finally:
        if conn and conn.is_connected(): conn.close()
            
def update_metro_card(card_number: int, balance: float, auto_recharge_enabled: bool, min_balance_threshold: float) -> bool:
    """Update metro card details"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            UPDATE metro_cards 
            SET balance = %s, autoRechargeEnabled = %s, minBalanceThreshold = %s 
            WHERE cardNumber = %s
        """
        cursor.execute(sql, (balance, auto_recharge_enabled, min_balance_threshold, card_number))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating metro card #{card_number}: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()




# ============================================================================
# MONTHLY PASS OPERATIONS
# ============================================================================

def insert_monthly_pass(username: str, source: str, destination: str, purchase_date: date, expiry_date: date, price: float, plan_type: str = 'basic') -> int:
    """Insert monthly pass and return passId"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            INSERT INTO monthly_passes 
            (username, source, destination, purchaseDate, expiryDate, price, planType, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'active')
        """
        cursor.execute(sql, (username, source, destination, purchase_date, expiry_date, price, plan_type))
        conn.commit()
        pass_id = cursor.lastrowid
        cursor.close()
        
        if pass_id > 0:
            logger.info(f"✅ Monthly pass #{pass_id} ({plan_type}) created for '{username}'")
        return pass_id
        
    except Error as e:
        logger.error(f"❌ Error inserting monthly pass: {e}")
        if conn:
            conn.rollback()
        return -1
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_monthly_passes(username: str) -> list:
    """Get all monthly passes (active + expired) for pass history"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT passId, source, destination, purchaseDate, expiryDate, price,
                   COALESCE(planType, 'basic') as planType,
                   CASE 
                       WHEN expiryDate >= CURRENT_DATE THEN 'active'
                       ELSE 'expired'
                   END as status
            FROM monthly_passes 
            WHERE username = %s
            ORDER BY purchaseDate DESC
        """
        cursor.execute(sql, (username,))
        passes = cursor.fetchall()
        cursor.close()
        return passes
        
    except Error as e:
        logger.error(f"❌ Error fetching pass history for '{username}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_monthly_pass_routes_by_username(username: str) -> List[str]:
    """Get active monthly pass routes for a user"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            SELECT source, destination 
            FROM monthly_passes 
            WHERE username = %s AND expiryDate >= CURRENT_DATE
        """
        cursor.execute(sql, (username,))
        rows = cursor.fetchall()
        cursor.close()
        return [f"{row[0]}->{row[1]}" for row in rows]
        
    except Error as e:
        logger.error(f"❌ Error fetching monthly passes for '{username}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# STATION OPERATIONS
# ============================================================================

def insert_or_update_station_location(name: str, x: float, y: float) -> bool:
    """Insert or update station location"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = """
            INSERT INTO station_locations (name, x, y) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE x = %s, y = %s
        """
        cursor.execute(sql, (name, x, y, x, y))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
        
    except Error as e:
        logger.error(f"❌ Error updating station location '{name}': {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_station_names() -> Set[str]:
    """Get all station names"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "SELECT name FROM station_locations"
        cursor.execute(sql)
        rows = cursor.fetchall()
        cursor.close()
        return {row[0] for row in rows}
        
    except Error as e:
        logger.error(f"❌ Error fetching stations: {e}")
        return set()
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_station_location(name: str) -> Optional[Dict[str, Any]]:
    """Get station coordinates"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT name, x, y FROM station_locations WHERE name = %s"
        cursor.execute(sql, (name,))
        location = cursor.fetchone()
        cursor.close()
        return location
        
    except Error as e:
        logger.error(f"❌ Error fetching station location '{name}': {e}")
        return None
    finally:
        if conn and conn.is_connected():
            conn.close()


# ============================================================================
# ANNOUNCEMENT OPERATIONS
# ============================================================================

def insert_announcement(message: str) -> bool:
    """Insert system announcement"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "INSERT INTO announcements (message) VALUES (%s)"
        cursor.execute(sql, (message,))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ Announcement added")
        return success
        
    except Error as e:
        logger.error(f"❌ Error inserting announcement: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()


def get_all_announcements() -> List[Dict[str, Any]]:
    """Get all announcements"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT * FROM announcements ORDER BY createdDate DESC"
        cursor.execute(sql)
        announcements = cursor.fetchall()
        cursor.close()
        return announcements
        
    except Error as e:
        logger.error(f"❌ Error fetching announcements: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def delete_announcement(announcement_id: int) -> bool:
    """Delete an announcement by ID"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "DELETE FROM announcements WHERE id = %s"
        cursor.execute(sql, (announcement_id,))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        
        if success:
            logger.info(f"✅ Announcement {announcement_id} deleted")
        return success
        
    except Error as e:
        logger.error(f"❌ Error deleting announcement: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()
# ============================================================================
# UTILITY OPERATIONS
# ============================================================================

def clear_all_data() -> bool:
    """Clear all data from database (for testing)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Disable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        
        # Delete data
        cursor.execute("DELETE FROM support_tickets")
        cursor.execute("DELETE FROM feedbacks")
        cursor.execute("DELETE FROM tickets")
        cursor.execute("DELETE FROM monthly_passes")
        cursor.execute("DELETE FROM metro_cards")
        cursor.execute("DELETE FROM station_locations")
        cursor.execute("DELETE FROM announcements")
        cursor.execute("DELETE FROM users")
        
        # Re-enable foreign key checks
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        
        conn.commit()
        cursor.close()
        logger.info("✅ All data cleared")
        return True
        
    except Error as e:
        logger.error(f"❌ Error clearing data: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if conn and conn.is_connected():
            conn.close()



# 1. FOR LOST & FOUND ADMIN
def get_all_lost_found_items() -> List[Dict[str, Any]]:
    """Get ALL lost and found reports (for Admin)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = "SELECT * FROM lost_found ORDER BY reportDate DESC"
        cursor.execute(sql)
        items = cursor.fetchall()
        cursor.close()
        return items
    except Error as e:
        logger.error(f"Error fetching lost items: {e}")
        return []
    finally:
        if conn and conn.is_connected(): conn.close()

def update_lost_found_status(item_id: int, status: str) -> bool:
    """Update status of a lost item (SEARCHING, FOUND, RETURNED)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = "UPDATE lost_found SET status = %s WHERE id = %s"
        cursor.execute(sql, (status, item_id))
        conn.commit()
        success = cursor.rowcount > 0
        cursor.close()
        return success
    except Error as e:
        logger.error(f"Error updating item #{item_id}: {e}")
        return False
    finally:
        if conn and conn.is_connected(): conn.close()

# 2. FOR SYSTEM SETTINGS (PEAK HOUR / MAINTENANCE)
def get_system_settings() -> Dict[str, Any]:
    """Get global settings (Mocked for simplicity or use DB table)"""
    # For this demo, we return a default. In a full app, create a 'settings' table.
    return {
        "peak_hour": False,
        "system_lockdown": False,
        "base_fare": 50,
        "lines": {
            "Blue Line": "Active",
            "Yellow Line": "Active",
            "Red Line": "Maintenance"
        }
    }

# --- ADD TO db.py ---

def get_recent_global_tickets(limit=20):
    """Get recent tickets from ALL users for Admin Feed"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        # Fetch tickets with username
        cursor.execute("""
            SELECT ticketId, username, source, destination, fare, bookingDate 
            FROM tickets ORDER BY bookingDate DESC LIMIT %s
        """, (limit,))
        return cursor.fetchall()
    except Exception as e:
        return []
    finally:
        if conn and conn.is_connected(): conn.close()

def get_station_traffic_stats():
    """Get ticket counts per station for Heatmap"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT source as station, COUNT(*) as count FROM tickets GROUP BY source")
        return cursor.fetchall()
    except Exception as e:
        return []
    finally:
        if conn and conn.is_connected(): conn.close()

def get_top_users_by_balance(limit=5):
    """Get 'Whale' users with highest wallet balance"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT username, walletBalance FROM users ORDER BY walletBalance DESC LIMIT %s", (limit,))
        return cursor.fetchall()
    except Exception as e:
        return []
    finally:
        if conn and conn.is_connected(): conn.close()



def get_peak_hour_stats():
    """Returns ticket counts by hour of day (0-23) for analytics"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True, buffered=True)
        # Extracts the HOUR from bookingDate and counts tickets
        cursor.execute("""
            SELECT HOUR(bookingDate) as hour, COUNT(*) as count 
            FROM tickets 
            GROUP BY HOUR(bookingDate) 
            ORDER BY hour
        """)
        return cursor.fetchall()
    finally:
        conn.close()

def get_feedback_sentiment():
    """Categorizes feedback as Positive/Negative based on keywords"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT text FROM feedbacks")
        all_feedback = cursor.fetchall()
        
        # Simple Python Logic for Sentiment
        stats = {'positive': 0, 'negative': 0, 'neutral': 0}
        pos_words = ['good', 'great', 'fast', 'best', 'love', 'smooth']
        neg_words = ['slow', 'bad', 'late', 'dirty', 'rude', 'worst']
        
        for f in all_feedback:
            txt = f['text'].lower()
            if any(w in txt for w in pos_words): stats['positive'] += 1
            elif any(w in txt for w in neg_words): stats['negative'] += 1
            else: stats['neutral'] += 1
        return stats
    finally:
        conn.close()

def create_staff_user(username, password):
    """Creates a new user with SUPPORT_STAFF role"""
    return insert_user(username, password, 0, "SUPPORT_STAFF")

def get_refund_stats():
    """Calculates total money refunded (cancelled tickets)"""
    # Note: Assuming you have a way to track cancellations. 
    # If not, we will simulate this query based on 'tickets' table logic for now
    # or you can add a 'status' column to tickets later.
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT COUNT(*) as count, SUM(fare) as total FROM tickets WHERE bookingDate < NOW()") 
        # In a real app, you'd filter by status='CANCELLED'
        return cursor.fetchone() 
    finally:
        conn.close()


def get_all_tickets_full():
    """Fetch all tickets with user details for the Admin Validator"""
    conn = get_db_connection()
    try:
        cursor = conn.cursor(dictionary=True, buffered=True)
        cursor.execute("SELECT * FROM tickets ORDER BY bookingDate DESC LIMIT 50")
        return cursor.fetchall()
    finally:
        conn.close()

def toggle_station_status(station_name, status):
    """Simulate closing a station (In real app, you'd add a 'status' column to stations table)"""
    # For now, we just return True to simulate success for the UI
    return True

# ============================================================================
# AUDIT LOG OPERATIONS
# ============================================================================

def get_recent_audit_logs(limit: int = 50) -> List[Dict[str, Any]]:
    """Get most recent audit log entries"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = """
            SELECT log_id, table_name, operation, record_id, 
                   old_value, new_value, changed_at, changed_by
            FROM audit_logs 
            ORDER BY changed_at DESC 
            LIMIT %s
        """
        cursor.execute(sql, (limit,))
        logs = cursor.fetchall()
        cursor.close()
        return logs
    except Error as e:
        logger.error(f"❌ Error fetching audit logs: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_audit_logs_by_table(table_name: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get audit logs for a specific table"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = """
            SELECT log_id, table_name, operation, record_id, 
                   old_value, new_value, changed_at, changed_by
            FROM audit_logs 
            WHERE table_name = %s
            ORDER BY changed_at DESC 
            LIMIT %s
        """
        cursor.execute(sql, (table_name, limit))
        logs = cursor.fetchall()
        cursor.close()
        return logs
    except Error as e:
        logger.error(f"❌ Error fetching audit logs for table '{table_name}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_audit_logs_by_user(username: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get audit logs for changes made by a specific user"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = """
            SELECT log_id, table_name, operation, record_id, 
                   old_value, new_value, changed_at, changed_by
            FROM audit_logs 
            WHERE changed_by = %s
            ORDER BY changed_at DESC 
            LIMIT %s
        """
        cursor.execute(sql, (username, limit))
        logs = cursor.fetchall()
        cursor.close()
        return logs
    except Error as e:
        logger.error(f"❌ Error fetching audit logs for user '{username}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_audit_logs_by_operation(operation: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Get audit logs for a specific operation type (INSERT, UPDATE, DELETE)"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        sql = """
            SELECT log_id, table_name, operation, record_id, 
                   old_value, new_value, changed_at, changed_by
            FROM audit_logs 
            WHERE operation = %s
            ORDER BY changed_at DESC 
            LIMIT %s
        """
        cursor.execute(sql, (operation.upper(), limit))
        logs = cursor.fetchall()
        cursor.close()
        return logs
    except Error as e:
        logger.error(f"❌ Error fetching audit logs for operation '{operation}': {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_audit_logs_filtered(
    table_name: Optional[str] = None,
    operation: Optional[str] = None,
    username: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get audit logs with multiple filters"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Build dynamic query
        conditions = []
        params = []
        
        if table_name:
            conditions.append("table_name = %s")
            params.append(table_name)
        
        if operation:
            conditions.append("operation = %s")
            params.append(operation.upper())
        
        if username:
            conditions.append("changed_by = %s")
            params.append(username)
        
        if start_date:
            conditions.append("changed_at >= %s")
            params.append(start_date)
        
        if end_date:
            conditions.append("changed_at <= %s")
            params.append(end_date)
        
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        sql = f"""
            SELECT log_id, table_name, operation, record_id, 
                   old_value, new_value, changed_at, changed_by
            FROM audit_logs 
            WHERE {where_clause}
            ORDER BY changed_at DESC 
            LIMIT %s
        """
        params.append(limit)
        
        cursor.execute(sql, tuple(params))
        logs = cursor.fetchall()
        cursor.close()
        return logs
    except Error as e:
        logger.error(f"❌ Error fetching filtered audit logs: {e}")
        return []
    finally:
        if conn and conn.is_connected():
            conn.close()

def get_audit_stats() -> Dict[str, Any]:
    """Get audit log statistics"""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True, buffered=True)
        
        # Total logs
        cursor.execute("SELECT COUNT(*) as total FROM audit_logs")
        total = cursor.fetchone()['total']
        
        # Logs by operation
        cursor.execute("""
            SELECT operation, COUNT(*) as count 
            FROM audit_logs 
            GROUP BY operation
        """)
        by_operation = {row['operation']: row['count'] for row in cursor.fetchall()}
        
        # Logs by table
        cursor.execute("""
            SELECT table_name, COUNT(*) as count 
            FROM audit_logs 
            GROUP BY table_name 
            ORDER BY count DESC 
            LIMIT 10
        """)
        by_table = cursor.fetchall()
        
        # Recent activity (last 24 hours)
        cursor.execute("""
            SELECT COUNT(*) as count 
            FROM audit_logs 
            WHERE changed_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        """)
        last_24h = cursor.fetchone()['count']
        
        cursor.close()
        
        return {
            'total_logs': total,
            'by_operation': by_operation,
            'by_table': by_table,
            'last_24_hours': last_24h
        }
    except Error as e:
        logger.error(f"❌ Error fetching audit stats: {e}")
        return {}
    finally:
        if conn and conn.is_connected():
            conn.close()

