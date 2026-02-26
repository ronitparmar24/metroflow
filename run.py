"""
MetroFlow — One-Click Setup & Run Script
=========================================
This script automatically:
  1. Installs all required Python packages
  2. Creates the MySQL database if it doesn't exist
  3. Seeds demo data (optional, first run only)
  4. Starts the Flask server

Usage:
    python run.py
"""

import subprocess
import sys
import os

# ─────────────────────────────────────────────
# STEP 1: Auto-install dependencies
# ─────────────────────────────────────────────
def install_requirements():
    """Install all packages from requirements.txt"""
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'requirements.txt')
    
    if not os.path.exists(req_file):
        print("❌ requirements.txt not found!")
        return False
    
    print("=" * 60)
    print("📦  Installing dependencies...")
    print("=" * 60)
    
    try:
        subprocess.check_call(
            [sys.executable, '-m', 'pip', 'install', '-r', req_file, '--quiet'],
            stdout=subprocess.DEVNULL if '--quiet' not in sys.argv else None,
            stderr=subprocess.STDOUT
        )
        print("✅  All packages installed successfully!\n")
        return True
    except subprocess.CalledProcessError:
        print("⚠️  Some packages failed. Trying one-by-one...\n")
        # Fallback: install each package individually
        with open(req_file, 'r') as f:
            for line in f:
                pkg = line.strip()
                if pkg and not pkg.startswith('#'):
                    try:
                        subprocess.check_call(
                            [sys.executable, '-m', 'pip', 'install', pkg, '--quiet'],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.STDOUT
                        )
                        print(f"  ✅ {pkg}")
                    except subprocess.CalledProcessError:
                        print(f"  ❌ {pkg} — FAILED (install manually: pip install {pkg})")
        print()
        return True


# ─────────────────────────────────────────────
# STEP 2: Create database if missing
# ─────────────────────────────────────────────
def ensure_database():
    """Create the 'metrosystemdb' database if it doesn't exist"""
    print("=" * 60)
    print("🗄️   Checking MySQL database...")
    print("=" * 60)
    
    try:
        import mysql.connector
        from config import Config
        
        db_config = Config.get_db_config().copy()
        db_name = db_config.pop('database')
        db_config.pop('raise_on_warnings', None)
        
        # Connect WITHOUT specifying a database
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(f"SHOW DATABASES LIKE '{db_name}'")
        result = cursor.fetchone()
        
        if result:
            print(f"✅  Database '{db_name}' already exists.\n")
        else:
            cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            conn.commit()
            print(f"✅  Database '{db_name}' created successfully!\n")
        
        cursor.close()
        conn.close()
        return True
        
    except ImportError:
        print("❌  mysql-connector-python not installed. Run: pip install mysql-connector-python")
        return False
    except Exception as e:
        error_msg = str(e).lower()
        if 'access denied' in error_msg:
            print(f"\n❌  MySQL Access Denied!")
            print(f"    → Open config.py and update your MySQL username/password")
            print(f"    → Default: user='root', password='' (blank for XAMPP)")
        elif 'can\'t connect' in error_msg or 'connection refused' in error_msg or '2003' in str(e):
            print(f"\n❌  Cannot connect to MySQL!")
            print(f"    → Make sure MySQL/XAMPP is running")
            print(f"    → Start XAMPP → Click 'Start' next to MySQL")
        else:
            print(f"\n❌  Database error: {e}")
        return False


# ─────────────────────────────────────────────
# STEP 3: Run the app
# ─────────────────────────────────────────────
def run_app():
    """Start the Flask application"""
    print("=" * 60)
    print("🚀  Starting MetroFlow...")
    print("=" * 60)
    print("    Open in browser: http://localhost:5000")
    print("    Press Ctrl+C to stop\n")
    
    # Import and run
    try:
        # Change to the script's directory
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
        
        # Run app.py as a subprocess so it gets the full startup flow
        subprocess.call([sys.executable, 'app.py'])
    except KeyboardInterrupt:
        print("\n\n👋  MetroFlow stopped. See you next time!")
    except Exception as e:
        print(f"\n❌  Error starting app: {e}")
        print("    Try running directly: python app.py")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == '__main__':
    print()
    print("╔════════════════════════════════════════════╗")
    print("║     🚇  MetroFlow — Auto Setup & Run      ║")
    print("╚════════════════════════════════════════════╝")
    print()
    
    # Step 1: Install packages
    install_requirements()
    
    # Step 2: Ensure database exists
    if not ensure_database():
        print("\n⚠️  Database setup failed. Fix the issue above and try again.")
        print("    Once MySQL is running, re-run: python run.py")
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    # Step 3: Launch the app
    run_app()
