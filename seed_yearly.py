"""
MetroFlow YEAR-LONG Ticket Seed
Generates 500+ tickets across 12 months for proper revenue graphs.
Run: python seed_yearly.py
"""

import hashlib, random
from datetime import datetime, date, timedelta
import mysql.connector

try:
    from config import Config
    db_config = Config.get_db_config()
except:
    db_config = {'host': 'localhost', 'user': 'root', 'password': '', 'database': 'metro_db'}

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

USERS = ['test', 'rahul', 'priya', 'amit', 'sneha', 'vikas', 'neha', 'arjun', 'kavita', 'deepak', 'anjali', 'rohan']

PEAK_TIMES = ['08:00', '09:00', '10:00', '11:00', '17:00', '18:00', '19:00']
OFFPEAK_TIMES = ['06:00', '07:00', '12:00', '13:00', '14:00', '15:00', '16:00', '20:00', '21:00']

# Monthly revenue targets (gives a realistic growth curve)
# Lower in early months, growing through the year
MONTHLY_TICKET_COUNTS = {
    1: 25,   # Mar 2025  (early, low adoption)
    2: 30,   # Apr 2025
    3: 35,   # May 2025
    4: 28,   # Jun 2025  (summer dip)
    5: 40,   # Jul 2025
    6: 45,   # Aug 2025
    7: 50,   # Sep 2025
    8: 55,   # Oct 2025  (festive season boost)
    9: 60,   # Nov 2025
    10: 65,  # Dec 2025
    11: 70,  # Jan 2026
    12: 80,  # Feb 2026  (current month, highest)
}

def seed():
    conn = mysql.connector.connect(**db_config)
    cursor = conn.cursor()
    
    today = date.today()
    total_inserted = 0
    monthly_revenue = {}
    
    print("== MetroFlow Yearly Data Seed ==\n")
    
    # Generate tickets for each of the last 12 months
    for month_offset in range(12, 0, -1):
        # Calculate the month's date range
        month_start = date(today.year, today.month, 1) - timedelta(days=month_offset * 30)
        # Adjust to actual first of month
        month_start = month_start.replace(day=1)
        
        # Get days in this month
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)
        
        # Don't go past today
        if month_end > today:
            month_end = today
        
        num_tickets = MONTHLY_TICKET_COUNTS.get(13 - month_offset, 40)
        month_label = month_start.strftime('%b %Y')
        month_total = 0
        
        for _ in range(num_tickets):
            user = random.choice(USERS)
            src, dst = random.sample(STATIONS, 2)
            pax = random.choices([1, 2, 3, 4], weights=[50, 30, 15, 5])[0]
            
            is_peak = random.random() < 0.45
            travel_time = random.choice(PEAK_TIMES if is_peak else OFFPEAK_TIMES)
            
            # Realistic fares based on approximate distance
            base_fare = random.choices(
                [30, 40, 50, 60, 70, 80, 100, 120, 150],
                weights=[10, 15, 20, 20, 15, 10, 5, 3, 2]
            )[0]
            
            if is_peak:
                fare = round(base_fare * 1.25 * pax, 2)
            else:
                fare = round(base_fare * pax, 2)
            
            # Random date within the month
            days_in_range = (month_end - month_start).days
            if days_in_range <= 0:
                travel_date = month_start
            else:
                travel_date = month_start + timedelta(days=random.randint(0, days_in_range))
            
            # Booking time
            hour = random.randint(6, 22)
            minute = random.randint(0, 59)
            booking_dt = datetime.combine(travel_date, datetime.min.time()) + timedelta(hours=hour, minutes=minute)
            
            cancelled = 1 if random.random() < 0.08 else 0
            distance = round(random.uniform(2.0, 28.0), 1)
            
            if not cancelled:
                month_total += fare
            
            try:
                cursor.execute("""
                    INSERT INTO tickets (username, source, destination, passengers, fare, 
                                        travelDate, distance, cancelled, bookingDate, travelTime)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (user, src, dst, pax, fare, travel_date, distance, cancelled, booking_dt, travel_time))
                total_inserted += 1
            except Exception as e:
                print(f"  Error: {e}")
        
        conn.commit()
        monthly_revenue[month_label] = month_total
        print(f"  {month_label}: {num_tickets} tickets, Revenue: Rs.{month_total:,.0f}")
    
    # Also add wallet history entries across the year 
    print("\n-- Adding wallet history across 12 months --")
    wh_count = 0
    for month_offset in range(12, 0, -1):
        month_start = date(today.year, today.month, 1) - timedelta(days=month_offset * 30)
        month_start = month_start.replace(day=1)
        if month_start.month == 12:
            month_end = date(month_start.year + 1, 1, 1) - timedelta(days=1)
        else:
            month_end = date(month_start.year, month_start.month + 1, 1) - timedelta(days=1)
        if month_end > today:
            month_end = today
        
        days_in_range = max((month_end - month_start).days, 1)
        
        for _ in range(random.randint(8, 15)):
            user = random.choice(USERS)
            d = month_start + timedelta(days=random.randint(0, days_in_range))
            dt = datetime.combine(d, datetime.min.time()) + timedelta(hours=random.randint(7, 21), minutes=random.randint(0, 59))
            
            if random.random() < 0.4:
                amt = random.choice([200, 500, 1000, 2000, 3000])
                typ, desc = 'CREDIT', 'Wallet recharge'
            else:
                amt = random.choice([30, 50, 60, 80, 100, 120, 150])
                typ, desc = 'DEBIT', 'Ticket booking'
            
            try:
                cursor.execute("""
                    INSERT INTO wallet_history (username, amount, type, description, date)
                    VALUES (%s, %s, %s, %s, %s)
                """, (user, amt, typ, desc, dt))
                wh_count += 1
            except:
                pass
        conn.commit()
    
    print(f"  Added {wh_count} wallet history entries\n")
    
    # Final stats
    cursor.execute("SELECT COUNT(*) FROM tickets")
    total_tickets = cursor.fetchone()[0]
    cursor.execute("SELECT COALESCE(SUM(fare), 0) FROM tickets WHERE cancelled = 0")
    total_rev = cursor.fetchone()[0]
    
    print("=" * 50)
    print(f"  Total Tickets in DB:   {total_tickets}")
    print(f"  Total Revenue:         Rs.{total_rev:,.0f}")
    print(f"  New Tickets Added:     {total_inserted}")
    print("=" * 50)
    
    print("\nMonthly Revenue Breakdown:")
    for month, rev in monthly_revenue.items():
        bar = '#' * int(rev / 500)
        print(f"  {month:>8}: Rs.{rev:>8,.0f}  {bar}")
    
    print("\nDone! Refresh admin dashboard -> click Week / Month / Year to see graphs.")
    
    cursor.close()
    conn.close()

if __name__ == '__main__':
    seed()
