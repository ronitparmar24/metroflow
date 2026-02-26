"""
MetroFlow Database Seed Script
Populates all tables with realistic dummy data for exam demonstration.
Run: python seed_data.py
"""

import hashlib
import random
from datetime import datetime, date, timedelta

# --- Database Connection (reuse your existing config) ---
import mysql.connector

try:
    from config import Config
    db_config = Config.get_db_config()
except:
    # Fallback if Config class isn't available
    db_config = {
        'host': 'localhost',
        'user': 'root',
        'password': '',
        'database': 'metro_db'
    }

def get_conn():
    return mysql.connector.connect(**db_config)

def sha256(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


# ============================================================================
# STATION NAMES (from your metro map)
# ============================================================================
STATIONS = [
    'thaltej_gam', 'thaltej', 'doordarshan_kendra', 'gurukul_road',
    'gujarat_university', 'commerce_six_road', 'stadium', 'old_high_court',
    'shahpur', 'gheekanta', 'kalupur_railway_station', 'kankaria_east',
    'apparel_park', 'amraiwadi', 'rabari_colony', 'vastral',
    'apmc', 'jivraj', 'rajiv_nagar', 'shreyas', 'paldi', 'gandhigram',
    'usmanpura', 'vijay_nagar', 'vadaj', 'ranip',
    'sabarmati_railway_station', 'aec', 'sabarmati', 'motera_stadium',
    'koteshwar_road', 'gift_city', 'infocity', 'mahatma_mandir'
]


# ============================================================================
# 1. USERS (12 users + existing admin/test accounts)
# ============================================================================
USERS = [
    # (username, password, walletBalance, role)
    ('admin',    sha256('admin'),     50000.0,  'ADMIN'),
    ('staff1',   sha256('staff1'),    10000.0,  'SUPPORT'),
    ('staff2',   sha256('staff2'),     8000.0,  'SUPPORT'),
    ('test',     sha256('test'),       2500.0,  'USER'),
    ('rahul',    sha256('rahul123'),   1850.0,  'USER'),
    ('priya',    sha256('priya123'),   3200.0,  'USER'),
    ('amit',     sha256('amit123'),    4500.0,  'USER'),
    ('sneha',    sha256('sneha123'),    920.0,  'USER'),
    ('vikas',    sha256('vikas123'),   6100.0,  'USER'),
    ('neha',     sha256('neha123'),    2750.0,  'USER'),
    ('arjun',    sha256('arjun123'),   1100.0,  'USER'),
    ('kavita',   sha256('kavita123'),  3400.0,  'USER'),
    ('deepak',   sha256('deepak123'),  5600.0,  'USER'),
    ('anjali',   sha256('anjali123'),  1980.0,  'USER'),
    ('rohan',    sha256('rohan123'),   4250.0,  'USER'),
]

# ============================================================================
# 2. TICKETS (40+ tickets spread across users & dates)
# ============================================================================
def gen_tickets():
    tickets = []
    today = date.today()
    user_names = [u[0] for u in USERS if u[3] == 'USER']
    
    travel_times_peak = ['08:00', '09:00', '10:00', '11:00', '17:00', '18:00', '19:00']
    travel_times_offpeak = ['06:00', '07:00', '12:00', '13:00', '14:00', '15:00', '16:00', '20:00', '21:00']
    
    for i in range(50):
        user = random.choice(user_names)
        src, dst = random.sample(STATIONS, 2)
        pax = random.randint(1, 4)
        is_peak = random.random() < 0.45
        travel_time = random.choice(travel_times_peak if is_peak else travel_times_offpeak)
        
        base_fare = random.choice([30, 40, 50, 60, 70, 80, 100, 120, 150])
        if is_peak:
            fare = round(base_fare * 1.25 * pax, 2)
        else:
            fare = round(base_fare * pax, 2)
        
        days_ago = random.randint(0, 14)
        travel_date = today - timedelta(days=days_ago)
        booking_date = datetime.combine(travel_date, datetime.min.time()) + timedelta(hours=random.randint(6, 21), minutes=random.randint(0, 59))
        
        cancelled = 1 if random.random() < 0.12 else 0
        distance = round(random.uniform(2.0, 28.0), 1)
        
        tickets.append((user, src, dst, pax, fare, travel_date, distance, cancelled, booking_date, travel_time))
    
    return tickets

# ============================================================================
# 3. FEEDBACKS
# ============================================================================
FEEDBACKS = [
    ('rahul',  'The metro service is punctual and clean. Great experience!',           'appreciation'),
    ('priya',  'AC was not working in coach B during morning hours.',                  'complaint'),
    ('amit',   'Please add more frequency during peak hours.',                         'suggestion'),
    ('sneha',  'The new QR code system is very convenient. Love it!',                  'appreciation'),
    ('vikas',  'Display boards at Kalupur station need maintenance.',                  'complaint'),
    ('neha',   'Can you add a monthly pass for students at discounted rate?',          'suggestion'),
    ('arjun',  'Staff at Old High Court station was very helpful.',                    'appreciation'),
    ('kavita', 'Escalator at Paldi station has been broken for a week.',               'complaint'),
    ('deepak', 'Excellent WiFi connectivity at Gujarat University station.',           'appreciation'),
    ('anjali', 'The fare calculator is inaccurate for multi-station routes.',          'complaint'),
    ('rohan',  'Adding a real-time crowd tracker would be amazing.',                   'suggestion'),
    ('test',   'Easy to use app, booking was seamless!',                                'appreciation'),
    ('rahul',  'Night service should run till midnight on weekends.',                  'suggestion'),
    ('priya',  'Found the lost item desk very efficient. Thanks!',                     'appreciation'),
    ('amit',   'Why is there no wheelchair ramp at Vadaj station?',                    'inquiry'),
    ('sneha',  'Penalty for ticket misuse should be stricter.',                         'suggestion'),
    ('vikas',  'Great initiative with the green points loyalty program!',               'appreciation'),
    ('neha',   'Water cooler at Ranip station is not working.',                         'complaint'),
]

# ============================================================================
# 4. SUPPORT TICKETS (linked to some feedbacks)
# ============================================================================
SUPPORT_TICKETS = [
    # (feedbackId, status, assignedStaff)
    (2,  'OPEN',     'staff1'),
    (5,  'OPEN',     'staff2'),
    (8,  'RESOLVED', 'staff1'),
    (10, 'OPEN',     'staff2'),
    (15, 'RESOLVED', 'staff1'),
    (18, 'OPEN',     'staff2'),
]

# ============================================================================
# 5. ANNOUNCEMENTS
# ============================================================================
ANNOUNCEMENTS = [
    'New Phase 2 extension to Gandhinagar is now operational! 🚇',
    'Metro timing extended: 6 AM to 11 PM on weekdays.',
    'EMERGENCY: Signal failure at Kalupur station. Expect 10-min delays on Blue Line.',
    'Green Points loyalty program launched! Earn 1 point per ₹2 spent.',
    'Free WiFi now available at all stations. Connect to MetroFlow-WiFi.',
    'Monthly pass holders get 15% extra discount this month!',
    'Platform screen doors installed at 5 new stations for safety.',
]

# ============================================================================
# 6. METRO CARDS
# ============================================================================
METRO_CARDS = [
    ('rahul',   500.0,  True,   100.0),
    ('priya',   1200.0, False,  200.0),
    ('amit',    800.0,  True,   150.0),
    ('vikas',   2000.0, True,   300.0),
    ('neha',    350.0,  False,  100.0),
    ('deepak',  1500.0, True,   200.0),
    ('rohan',   950.0,  False,  100.0),
    ('test',    600.0,  True,   100.0),
]

# ============================================================================
# 7. MONTHLY PASSES
# ============================================================================
def gen_monthly_passes():
    today = date.today()
    return [
        ('rahul',  'thaltej',          'kalupur_railway_station', today - timedelta(days=10), today + timedelta(days=20), 1500.0),
        ('priya',  'paldi',            'gujarat_university',      today - timedelta(days=5),  today + timedelta(days=25), 1200.0),
        ('vikas',  'motera_stadium',   'old_high_court',          today - timedelta(days=20), today + timedelta(days=10), 1800.0),
        ('deepak', 'sabarmati',        'commerce_six_road',       today - timedelta(days=2),  today + timedelta(days=28), 1400.0),
        ('amit',   'ranip',            'stadium',                 today - timedelta(days=25), today + timedelta(days=5),  1600.0),
    ]

# ============================================================================
# 8. LOST & FOUND
# ============================================================================
LOST_FOUND = [
    ('rahul',  'Black laptop bag',      'Dell laptop bag with charger, left on seat in coach A',  'SEARCHING'),
    ('priya',  'Gold earring',          'Small gold earring, possibly dropped near gate 2',        'FOUND'),
    ('sneha',  'Blue umbrella',          'Foldable blue umbrella forgotten at Paldi station',       'SEARCHING'),
    ('neha',   'Student ID card',       'Gujarat University student ID, name: Neha Patel',         'FOUND'),
    ('arjun',  'Water bottle',          'Steel water bottle with stickers, left on platform',      'CLOSED'),
    ('kavita', 'Sunglasses',            'Ray-Ban sunglasses in black case, Kalupur station',       'SEARCHING'),
    ('test',   'Backpack',              'Red backpack with books, left at Old High Court station',  'SEARCHING'),
]

# ============================================================================
# 9. NOTIFICATIONS
# ============================================================================
def gen_notifications():
    user_names = [u[0] for u in USERS if u[3] == 'USER']
    notifs = []
    messages = [
        'Booking confirmed! You earned {pts} Green Points.',
        'Your ticket #{tid} has been booked successfully.',
        'Welcome to MetroFlow! Start your journey today.',
        'Wallet recharged with ₹{amt}. New balance: ₹{bal}.',
        'Monthly pass activated for {src} → {dst}.',
        'Your lost item report has been updated.',
        'Peak hours start at 8 AM. Plan your journey accordingly!',
        'New announcement: Free WiFi at all stations!',
        'Your metro card has been auto-recharged.',
        'Ticket #{tid} cancelled. Refund of ₹{fare} credited.',
    ]
    
    for user in user_names:
        # 2-4 notifications per user
        for _ in range(random.randint(2, 4)):
            msg = random.choice(messages)
            msg = msg.format(
                pts=random.randint(10, 80),
                tid=random.randint(1, 50),
                amt=random.choice([200, 500, 1000, 2000]),
                bal=random.randint(500, 5000),
                src=random.choice(STATIONS[:8]),
                dst=random.choice(STATIONS[8:16]),
                fare=random.choice([50, 80, 100, 150])
            )
            is_read = random.random() < 0.6
            notifs.append((user, msg, is_read))
    
    return notifs

# ============================================================================
# 10. WALLET HISTORY
# ============================================================================
def gen_wallet_history():
    user_names = [u[0] for u in USERS if u[3] == 'USER']
    history = []
    today = date.today()
    
    for user in user_names:
        # Initial recharge
        d = today - timedelta(days=random.randint(20, 30))
        history.append((user, random.choice([1000, 2000, 3000, 5000]), 'CREDIT', 'Initial wallet recharge', datetime.combine(d, datetime.min.time()) + timedelta(hours=10)))
        
        # 3-5 transactions per user
        for _ in range(random.randint(3, 5)):
            days_ago = random.randint(0, 15)
            dt = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=random.randint(7, 21), minutes=random.randint(0, 59))
            
            if random.random() < 0.35:
                # Recharge
                amt = random.choice([200, 500, 1000, 2000])
                history.append((user, amt, 'CREDIT', 'Wallet recharge', dt))
            else:
                # Ticket purchase
                amt = random.choice([30, 50, 80, 100, 120, 150, 200])
                history.append((user, amt, 'DEBIT', 'Ticket booking', dt))
    
    return history


# ============================================================================
# MAIN SEED FUNCTION
# ============================================================================
def seed():
    conn = get_conn()
    cursor = conn.cursor()
    
    print("🌱 Seeding MetroFlow database...\n")
    
    # --- 1. Users (use INSERT IGNORE to skip existing) ---
    print("👤 Inserting users...")
    for u in USERS:
        try:
            cursor.execute("""
                INSERT INTO users (username, password, walletBalance, role) 
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE walletBalance = VALUES(walletBalance)
            """, u)
        except Exception as e:
            print(f"   ⚠️ User {u[0]}: {e}")
    conn.commit()
    print(f"   ✅ {len(USERS)} users ready")
    
    # --- 2. Add loyaltyPoints column if missing ---
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN loyaltyPoints INT DEFAULT 0")
    except:
        pass
    
    # Update loyalty points for users
    for user in USERS:
        if user[3] == 'USER':
            pts = random.randint(50, 500)
            cursor.execute("UPDATE users SET loyaltyPoints = %s WHERE username = %s", (pts, user[0]))
    conn.commit()
    print("   ✅ Loyalty points assigned")
    
    # --- 3. Tickets ---
    print("🎫 Inserting tickets...")
    tickets = gen_tickets()
    for t in tickets:
        try:
            cursor.execute("""
                INSERT INTO tickets (username, source, destination, passengers, fare, travelDate, distance, cancelled, bookingDate, travelTime)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, t)
        except Exception as e:
            print(f"   ⚠️ Ticket error: {e}")
    conn.commit()
    print(f"   ✅ {len(tickets)} tickets inserted")
    
    # --- 4. Feedbacks ---
    print("💬 Inserting feedbacks...")
    for fb in FEEDBACKS:
        try:
            cursor.execute("""
                INSERT INTO feedbacks (username, text, type) VALUES (%s, %s, %s)
            """, fb)
        except Exception as e:
            print(f"   ⚠️ Feedback error: {e}")
    conn.commit()
    print(f"   ✅ {len(FEEDBACKS)} feedbacks inserted")
    
    # --- 5. Support Tickets ---
    print("🎟️ Inserting support tickets...")
    # Get the feedbackIds we just inserted
    cursor.execute("SELECT feedbackId FROM feedbacks ORDER BY feedbackId DESC LIMIT %s", (len(FEEDBACKS),))
    fb_ids = [row[0] for row in cursor.fetchall()]
    fb_ids.reverse()  # oldest first
    
    for fb_offset, status, staff in SUPPORT_TICKETS:
        if fb_offset - 1 < len(fb_ids):
            fid = fb_ids[fb_offset - 1]
            resolved = datetime.now() if status == 'RESOLVED' else None
            try:
                cursor.execute("""
                    INSERT INTO support_tickets (feedbackId, status, assignedStaffUsername, resolvedDate) 
                    VALUES (%s, %s, %s, %s)
                """, (fid, status, staff, resolved))
            except Exception as e:
                print(f"   ⚠️ Support ticket error: {e}")
    conn.commit()
    print(f"   ✅ {len(SUPPORT_TICKETS)} support tickets inserted")
    
    # --- 6. Announcements ---
    print("📢 Inserting announcements...")
    for msg in ANNOUNCEMENTS:
        try:
            cursor.execute("INSERT INTO announcements (message) VALUES (%s)", (msg,))
        except Exception as e:
            print(f"   ⚠️ Announcement error: {e}")
    conn.commit()
    print(f"   ✅ {len(ANNOUNCEMENTS)} announcements inserted")
    
    # --- 7. Metro Cards ---
    print("💳 Inserting metro cards...")
    for mc in METRO_CARDS:
        try:
            cursor.execute("""
                INSERT INTO metro_cards (username, balance, autoRechargeEnabled, minBalanceThreshold) 
                VALUES (%s, %s, %s, %s)
            """, mc)
        except Exception as e:
            print(f"   ⚠️ Metro card error: {e}")
    conn.commit()
    print(f"   ✅ {len(METRO_CARDS)} metro cards inserted")
    
    # --- 8. Monthly Passes ---
    print("📅 Inserting monthly passes...")
    passes = gen_monthly_passes()
    for p in passes:
        try:
            cursor.execute("""
                INSERT INTO monthly_passes (username, source, destination, purchaseDate, expiryDate, price) 
                VALUES (%s, %s, %s, %s, %s, %s)
            """, p)
        except Exception as e:
            print(f"   ⚠️ Monthly pass error: {e}")
    conn.commit()
    print(f"   ✅ {len(passes)} monthly passes inserted")
    
    # --- 9. Lost & Found ---
    print("🔍 Inserting lost & found items...")
    for lf in LOST_FOUND:
        try:
            cursor.execute("""
                INSERT INTO lost_found (username, item, description, status) VALUES (%s, %s, %s, %s)
            """, lf)
        except Exception as e:
            print(f"   ⚠️ Lost item error: {e}")
    conn.commit()
    print(f"   ✅ {len(LOST_FOUND)} lost items inserted")
    
    # --- 10. Notifications ---
    print("🔔 Inserting notifications...")
    notifs = gen_notifications()
    for n in notifs:
        try:
            cursor.execute("""
                INSERT INTO notifications (username, message, is_read) VALUES (%s, %s, %s)
            """, n)
        except Exception as e:
            print(f"   ⚠️ Notification error: {e}")
    conn.commit()
    print(f"   ✅ {len(notifs)} notifications inserted")
    
    # --- 11. Wallet History ---
    print("💰 Inserting wallet history...")
    wh = gen_wallet_history()
    for w in wh:
        try:
            cursor.execute("""
                INSERT INTO wallet_history (username, amount, type, description, date) VALUES (%s, %s, %s, %s, %s)
            """, w)
        except Exception as e:
            print(f"   ⚠️ Wallet history error: {e}")
    conn.commit()
    print(f"   ✅ {len(wh)} wallet history entries inserted")
    
    # --- Summary ---
    print("\n" + "=" * 50)
    cursor.execute("SELECT COUNT(*) FROM users")
    print(f"📊 Total Users:          {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM tickets")
    print(f"📊 Total Tickets:        {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM feedbacks")
    print(f"📊 Total Feedbacks:      {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM support_tickets")
    print(f"📊 Total Support Tickets:{cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM announcements")
    print(f"📊 Total Announcements:  {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM metro_cards")
    print(f"📊 Total Metro Cards:    {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM monthly_passes")
    print(f"📊 Total Monthly Passes: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM lost_found")
    print(f"📊 Total Lost & Found:   {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM notifications")
    print(f"📊 Total Notifications:  {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM wallet_history")
    print(f"📊 Total Wallet History: {cursor.fetchone()[0]}")
    cursor.execute("SELECT COUNT(*) FROM station_locations")
    print(f"📊 Total Stations:       {cursor.fetchone()[0]}")
    print("=" * 50)
    print("\n🎉 Database seeded successfully! Ready for your exam. 🚇")
    
    cursor.close()
    conn.close()


if __name__ == '__main__':
    seed()
