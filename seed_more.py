"""
MetroFlow — Add More Data (Additive Seed)
Adds new users + data on top of existing records. Safe to run multiple times.
Run: python seed_more.py
"""

import hashlib
import random
from datetime import datetime, date, timedelta
import mysql.connector

try:
    from config import Config
    db_config = Config.get_db_config()
except:
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
# STATION NAMES
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
# 1. NEW USERS (10 fresh users with Indian names)
# ============================================================================
NEW_USERS = [
    ('meera',    sha256('meera123'),    3800.0,  'USER'),
    ('karan',    sha256('karan123'),    2100.0,  'USER'),
    ('pooja',    sha256('pooja123'),    4700.0,  'USER'),
    ('harsh',    sha256('harsh123'),    1500.0,  'USER'),
    ('divya',    sha256('divya123'),    5200.0,  'USER'),
    ('sagar',    sha256('sagar123'),    2900.0,  'USER'),
    ('nisha',    sha256('nisha123'),    3300.0,  'USER'),
    ('yash',     sha256('yash123'),     1750.0,  'USER'),
    ('ritu',     sha256('ritu123'),     4100.0,  'USER'),
    ('manav',    sha256('manav123'),    6000.0,  'USER'),
]

# All user names (existing + new) for ticket generation
ALL_USERS = [
    'rahul', 'priya', 'amit', 'sneha', 'vikas', 'neha',
    'arjun', 'kavita', 'deepak', 'anjali', 'rohan', 'test',
    'meera', 'karan', 'pooja', 'harsh', 'divya', 'sagar', 'nisha', 'yash', 'ritu', 'manav'
]

# ============================================================================
# 2. GENERATE TICKETS (80 more tickets spread across 30 days)
# ============================================================================
def gen_tickets():
    tickets = []
    today = date.today()
    travel_times_peak = ['08:00', '08:30', '09:00', '09:30', '10:00', '10:30', '17:00', '17:30', '18:00', '18:30']
    travel_times_offpeak = ['06:00', '06:30', '07:00', '12:00', '13:00', '14:00', '15:00', '16:00', '20:00', '21:00']

    for i in range(80):
        user = random.choice(ALL_USERS)
        src, dst = random.sample(STATIONS, 2)
        pax = random.randint(1, 5)
        is_peak = random.random() < 0.45
        travel_time = random.choice(travel_times_peak if is_peak else travel_times_offpeak)

        base_fare = random.choice([25, 30, 35, 40, 50, 60, 70, 80, 90, 100, 120, 150])
        fare = round(base_fare * (1.25 if is_peak else 1.0) * pax, 2)

        # Spread across past 30 days + some future tickets
        days_offset = random.randint(-5, 30)  # -5 = 5 days in future
        travel_date = today - timedelta(days=days_offset)
        booking_date = datetime.combine(
            min(travel_date, today) - timedelta(days=random.randint(0, 2)),
            datetime.min.time()
        ) + timedelta(hours=random.randint(6, 22), minutes=random.randint(0, 59))

        cancelled = 1 if random.random() < 0.10 else 0
        distance = round(random.uniform(2.0, 32.0), 1)

        tickets.append((user, src, dst, pax, fare, travel_date, distance, cancelled, booking_date, travel_time))

    return tickets

# ============================================================================
# 3. NEW FEEDBACKS
# ============================================================================
NEW_FEEDBACKS = [
    ('meera',  'The new metro card auto-recharge feature is very handy!',              'appreciation'),
    ('karan',  'The metro was delayed by 15 minutes at Gheekanta station.',            'complaint'),
    ('pooja',  'Can we get charging ports in the coaches?',                             'suggestion'),
    ('harsh',  'Security check at Kalupur is too slow during peak hours.',              'complaint'),
    ('divya',  'Loved the QR-based entry system. Very futuristic!',                     'appreciation'),
    ('sagar',  'Please add more parking space at Motera Stadium station.',              'suggestion'),
    ('nisha',  'The cleaning staff does an excellent job. Kudos!',                      'appreciation'),
    ('yash',   'Why does the app not show real-time train position?',                   'inquiry'),
    ('ritu',   'Metro card balance deducted twice for same journey. Need refund.',      'complaint'),
    ('manav',  'First-class coaches would be a great premium addition.',                'suggestion'),
    ('meera',  'Night metro after 10 PM would help working professionals.',             'suggestion'),
    ('karan',  'The announcement system is very clear and helpful.',                    'appreciation'),
    ('pooja',  'Escalator at Commerce Six Road is out of service again.',               'complaint'),
    ('harsh',  'Monthly pass should have family plan option.',                           'suggestion'),
    ('divya',  'The green points loyalty system is motivating me to use metro daily!',  'appreciation'),
    ('rahul',  'WiFi speed at stations has improved a lot. Great work!',                'appreciation'),
    ('priya',  'Token vending machine at Paldi is often jammed.',                       'complaint'),
    ('amit',   'Can the app show crowd density per coach?',                             'suggestion'),
    ('sneha',  'Air conditioning was perfect today. Very comfortable ride.',            'appreciation'),
    ('vikas',  'There should be a dedicated women-only coach.',                          'suggestion'),
]

# ============================================================================
# 4. NEW LOST & FOUND ITEMS
# ============================================================================
NEW_LOST_FOUND = [
    ('meera',  'Silver bracelet',       'Thin silver bracelet dropped near exit gate at Thaltej',        'SEARCHING'),
    ('karan',  'Bluetooth earbuds',     'Black JBL earbuds in charging case, left on seat',              'SEARCHING'),
    ('pooja',  'Tiffin box',            'Steel tiffin box with blue lid, left at Paldi station',        'FOUND'),
    ('harsh',  'Car keys',              'Honda car key with red keychain, fell near ticket counter',     'SEARCHING'),
    ('divya',  'Notebook',              'Brown leather diary with notes, Old High Court platform',       'FOUND'),
    ('sagar',  'Mobile phone',          'Samsung Galaxy phone with cracked screen, blue case',           'SEARCHING'),
    ('nisha',  'Handbag',               'Small black handbag with wallet and makeup, Ranip station',     'SEARCHING'),
    ('yash',   'Sports shoes',          'Nike running shoes in a bag, left under seat',                  'CLOSED'),
    ('ritu',   'Spectacles',            'Gold-framed reading glasses in brown case',                     'FOUND'),
    ('manav',  'Power bank',            'Anker 20000mAh power bank, white color, Vastral station',       'SEARCHING'),
    ('rahul',  'Jacket',                'Blue denim jacket, left on platform bench at AEC station',      'SEARCHING'),
    ('test',   'Headphones',            'Sony over-ear headphones, black, left in coach B',              'FOUND'),
]

# ============================================================================
# 5. NEW METRO CARDS (for new users)
# ============================================================================
NEW_METRO_CARDS = [
    ('meera',   800.0,  True,   150.0),
    ('karan',   450.0,  False,  100.0),
    ('pooja',   1800.0, True,   250.0),
    ('harsh',   300.0,  False,  100.0),
    ('divya',   2500.0, True,   300.0),
    ('sagar',   650.0,  True,   100.0),
    ('nisha',   1100.0, False,  200.0),
    ('yash',    400.0,  False,  100.0),
    ('ritu',    1500.0, True,   200.0),
    ('manav',   3000.0, True,   500.0),
]

# ============================================================================
# 6. GENERATE MONTHLY PASSES
# ============================================================================
def gen_monthly_passes():
    today = date.today()
    return [
        ('meera',  'thaltej',          'gheekanta',               today - timedelta(days=8),  today + timedelta(days=22), 1400.0),
        ('karan',  'vadaj',            'kalupur_railway_station', today - timedelta(days=3),  today + timedelta(days=27), 1300.0),
        ('divya',  'motera_stadium',   'commerce_six_road',       today - timedelta(days=15), today + timedelta(days=15), 1700.0),
        ('manav',  'gift_city',        'old_high_court',          today - timedelta(days=1),  today + timedelta(days=29), 1900.0),
        ('pooja',  'paldi',            'stadium',                 today - timedelta(days=12), today + timedelta(days=18), 1200.0),
        ('ritu',   'sabarmati',        'amraiwadi',               today - timedelta(days=6),  today + timedelta(days=24), 1500.0),
        ('rahul',  'usmanpura',        'kankaria_east',           today - timedelta(days=2),  today + timedelta(days=28), 1350.0),
        ('priya',  'ranip',            'vastral',                 today - timedelta(days=18), today + timedelta(days=12), 1650.0),
    ]

# ============================================================================
# 7. GENERATE NOTIFICATIONS
# ============================================================================
def gen_notifications():
    notifs = []
    messages = [
        'Booking confirmed! You earned {pts} Green Points.',
        'Your ticket #{tid} has been booked successfully.',
        'Wallet recharged with ₹{amt}. New balance: ₹{bal}.',
        'Monthly pass activated for {src} → {dst}.',
        'Your lost item report has been updated.',
        'Peak hours start at 8 AM. Plan your journey!',
        'Your metro card has been auto-recharged with ₹{amt}.',
        'Ticket #{tid} cancelled. Refund of ₹{fare} credited.',
        '🎉 You have reached a {streak}-day travel streak!',
        'Metro card balance low. Recharge to continue seamless travel.',
        'New route added: {src} to {dst}. Try it today!',
        'Your feedback has been received. Thank you!',
    ]

    for user in ALL_USERS:
        for _ in range(random.randint(3, 6)):
            msg = random.choice(messages)
            msg = msg.format(
                pts=random.randint(10, 120),
                tid=random.randint(50, 200),
                amt=random.choice([200, 500, 1000, 1500, 2000]),
                bal=random.randint(500, 8000),
                src=random.choice(STATIONS[:12]).replace('_', ' ').title(),
                dst=random.choice(STATIONS[12:]).replace('_', ' ').title(),
                fare=random.choice([30, 50, 80, 100, 120, 150, 200]),
                streak=random.choice([3, 5, 7, 10, 14])
            )
            is_read = random.random() < 0.5
            notifs.append((user, msg, is_read))

    return notifs

# ============================================================================
# 8. GENERATE WALLET HISTORY
# ============================================================================
def gen_wallet_history():
    history = []
    today = date.today()

    for user in ALL_USERS:
        # 4-8 transactions per user
        for _ in range(random.randint(4, 8)):
            days_ago = random.randint(0, 30)
            dt = datetime.combine(today - timedelta(days=days_ago), datetime.min.time()) + \
                 timedelta(hours=random.randint(6, 22), minutes=random.randint(0, 59))

            roll = random.random()
            if roll < 0.30:
                # Wallet recharge
                amt = random.choice([200, 500, 1000, 1500, 2000, 3000])
                history.append((user, amt, 'CREDIT', 'Wallet recharge', dt))
            elif roll < 0.50:
                # Metro card recharge
                amt = random.choice([200, 500, 1000])
                history.append((user, amt, 'DEBIT', 'Metro card recharge', dt))
            elif roll < 0.60:
                # Monthly pass purchase
                amt = random.choice([1200, 1400, 1500, 1800])
                history.append((user, amt, 'DEBIT', 'Monthly pass purchase', dt))
            elif roll < 0.70:
                # Refund
                amt = random.choice([30, 50, 80, 100, 150])
                history.append((user, amt, 'CREDIT', 'Ticket cancellation refund', dt))
            else:
                # Ticket booking
                amt = random.choice([25, 30, 40, 50, 60, 80, 100, 120, 150, 200, 250])
                history.append((user, amt, 'DEBIT', 'Ticket booking', dt))

    return history

# ============================================================================
# 9. NEW ANNOUNCEMENTS
# ============================================================================
NEW_ANNOUNCEMENTS = [
    'EMERGENCY: vastral route is blocked for today!',
    'hello, train is late today',
    'Weekend special: 20% off on all tickets this Saturday and Sunday! 🎫',
    'New contactless payment system now live at all stations.',
    'Metro services will run extra coaches during Navratri festival. 🎆',
    'Lost & Found desk now available 24/7 at Kalupur Railway Station.',
    'Student discount: Show your college ID for 10% off on monthly passes. 🎓',
]


# ============================================================================
# MAIN SEED FUNCTION
# ============================================================================
def seed_more():
    conn = get_conn()
    cursor = conn.cursor()

    print("🌱 Adding MORE data to MetroFlow database...\n")

    # --- 1. New Users ---
    print("👤 Adding new users...")
    added = 0
    for u in NEW_USERS:
        try:
            cursor.execute("""
                INSERT IGNORE INTO users (username, password, walletBalance, role, loyaltyPoints) 
                VALUES (%s, %s, %s, %s, %s)
            """, (u[0], u[1], u[2], u[3], random.randint(30, 400)))
            if cursor.rowcount > 0:
                added += 1
        except Exception as e:
            print(f"   ⚠️ User {u[0]}: {e}")
    conn.commit()
    print(f"   ✅ {added} new users added")

    # --- 2. Tickets ---
    print("🎫 Adding tickets...")
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
    print(f"   ✅ {len(tickets)} tickets added")

    # --- 3. Feedbacks ---
    print("💬 Adding feedbacks...")
    for fb in NEW_FEEDBACKS:
        try:
            cursor.execute("INSERT INTO feedbacks (username, text, type) VALUES (%s, %s, %s)", fb)
        except Exception as e:
            print(f"   ⚠️ Feedback error: {e}")
    conn.commit()
    print(f"   ✅ {len(NEW_FEEDBACKS)} feedbacks added")

    # --- 4. Support Tickets from new feedbacks ---
    print("🎟️ Adding support tickets...")
    cursor.execute("SELECT feedbackId FROM feedbacks WHERE type = 'complaint' ORDER BY feedbackId DESC LIMIT 8")
    complaint_ids = [row[0] for row in cursor.fetchall()]
    st_count = 0
    staff_list = ['staff1', 'staff2']
    for fid in complaint_ids:
        status = random.choice(['OPEN', 'OPEN', 'RESOLVED'])
        resolved = datetime.now() - timedelta(days=random.randint(0, 5)) if status == 'RESOLVED' else None
        try:
            cursor.execute("""
                INSERT INTO support_tickets (feedbackId, status, assignedStaffUsername, resolvedDate) 
                VALUES (%s, %s, %s, %s)
            """, (fid, status, random.choice(staff_list), resolved))
            st_count += 1
        except Exception as e:
            pass  # Skip duplicates
    conn.commit()
    print(f"   ✅ {st_count} support tickets added")

    # --- 5. Announcements ---
    print("📢 Adding announcements...")
    for msg in NEW_ANNOUNCEMENTS:
        try:
            cursor.execute("INSERT INTO announcements (message) VALUES (%s)", (msg,))
        except Exception as e:
            print(f"   ⚠️ Announcement error: {e}")
    conn.commit()
    print(f"   ✅ {len(NEW_ANNOUNCEMENTS)} announcements added")

    # --- 6. Metro Cards ---
    print("💳 Adding metro cards...")
    mc_count = 0
    for mc in NEW_METRO_CARDS:
        try:
            cursor.execute("""
                INSERT IGNORE INTO metro_cards (username, balance, autoRechargeEnabled, minBalanceThreshold) 
                VALUES (%s, %s, %s, %s)
            """, mc)
            if cursor.rowcount > 0:
                mc_count += 1
        except Exception as e:
            print(f"   ⚠️ Metro card error: {e}")
    conn.commit()
    print(f"   ✅ {mc_count} metro cards added")

    # --- 7. Monthly Passes ---
    print("📅 Adding monthly passes...")
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
    print(f"   ✅ {len(passes)} monthly passes added")

    # --- 8. Lost & Found ---
    print("🔍 Adding lost & found items...")
    for lf in NEW_LOST_FOUND:
        try:
            cursor.execute("INSERT INTO lost_found (username, item, description, status) VALUES (%s, %s, %s, %s)", lf)
        except Exception as e:
            print(f"   ⚠️ Lost item error: {e}")
    conn.commit()
    print(f"   ✅ {len(NEW_LOST_FOUND)} lost items added")

    # --- 9. Notifications ---
    print("🔔 Adding notifications...")
    notifs = gen_notifications()
    for n in notifs:
        try:
            cursor.execute("INSERT INTO notifications (username, message, is_read) VALUES (%s, %s, %s)", n)
        except Exception as e:
            print(f"   ⚠️ Notification error: {e}")
    conn.commit()
    print(f"   ✅ {len(notifs)} notifications added")

    # --- 10. Wallet History ---
    print("💰 Adding wallet history...")
    wh = gen_wallet_history()
    for w in wh:
        try:
            cursor.execute("""
                INSERT INTO wallet_history (username, amount, type, description, date) VALUES (%s, %s, %s, %s, %s)
            """, w)
        except Exception as e:
            print(f"   ⚠️ Wallet history error: {e}")
    conn.commit()
    print(f"   ✅ {len(wh)} wallet history entries added")

    # --- Summary ---
    print("\n" + "=" * 50)
    tables = ['users', 'tickets', 'feedbacks', 'support_tickets', 'announcements',
              'metro_cards', 'monthly_passes', 'lost_found', 'notifications', 'wallet_history']
    icons = ['👤', '🎫', '💬', '🎟️', '📢', '💳', '📅', '🔍', '🔔', '💰']
    for tbl, icon in zip(tables, icons):
        cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
        count = cursor.fetchone()[0]
        print(f"{icon} {tbl:20s} → {count}")
    print("=" * 50)
    print("\n🎉 Additional data added successfully! 🚇")

    cursor.close()
    conn.close()


if __name__ == '__main__':
    seed_more()
