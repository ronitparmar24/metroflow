# 🚇 MetroFlow — Metro Ticket Booking System

A full-stack **Metro Ticket Booking System** built with Flask + MySQL.  
Book metro tickets, manage wallet, buy monthly passes, and more — with a beautiful dashboard UI.

---

## ⚡ Quick Start (One Command)

### Prerequisites
1. **Python 3.8+** — [Download here](https://www.python.org/downloads/)  
   ⚠️ During install, check **"Add Python to PATH"**
2. **XAMPP** (MySQL) — [Download here](https://www.apachefriends.org/download.html)  
   Only MySQL is needed. Start XAMPP → Click **Start** next to **MySQL**

### Run the Project

```bash
# Clone the project
git clone https://github.com/ronitparmar24/metroflow.git
cd metroflow

# One-click setup & run
python run.py
```

That's it! `run.py` will automatically:
- ✅ Install all Python packages
- ✅ Create the database (`metrosystemdb`)
- ✅ Start the server at **http://localhost:5000**

### Or Run Manually

```bash
# Install dependencies
pip install -r requirements.txt

# Start the app
python app.py
```

> **Note:** Make sure MySQL (XAMPP) is running before starting the app.

---

## 🔐 Default Login Credentials

| Role | Username | Password |
|------|----------|----------|
| User | `ronitparmar` | `ronit2424` |
| Admin | `admin` | `admin123` |

> Run `python seed_data.py` to populate demo data (users, tickets, etc.)

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python, Flask, REST API |
| Frontend | HTML5, CSS3, JavaScript |
| Database | MySQL (via XAMPP) |
| PDF Generation | ReportLab |
| QR Codes | qrcode + Pillow |

---

## ✨ Features

- 🔐 User Registration & Login (SHA-256 hashed passwords)
- 🎫 Ticket Booking with Smart Fare Calculator (peak/off-peak pricing)
- 💳 Digital Wallet & Metro Card
- 📅 Monthly Pass System (Basic, Premium, Unlimited tiers)
- 📊 Admin Dashboard with Analytics
- 🎨 Dark Mode Support
- 📄 PDF Ticket Download
- 📱 QR Code Tickets
- 🔔 Smart Notification Center
- 🚉 Live Station Info
- 📈 Travel Analytics & Charts
- 🌙 Light/Dark Theme Toggle

---

## 📂 Project Structure

```
MetroFlow/
├── app.py              # Main Flask application (all API routes)
├── db.py               # Database operations (MySQL queries)
├── config.py           # Database configuration
├── models.py           # Data models (User, Admin, Ticket, etc.)
├── ds.py               # Data structures (Queue, Graph, etc.)
├── utils.py            # Utility functions (hashing, formatting)
├── run.py              # One-click setup & run script
├── requirements.txt    # Python dependencies
├── seed_data.py        # Database seeder (demo data)
├── seed_more.py        # Additional seed data
├── seed_yearly.py      # Yearly statistics seeder
├── frontend/
│   ├── index.html      # Landing page
│   ├── login.html      # Login page
│   ├── register.html   # Registration page
│   ├── dashboard.html  # User dashboard
│   ├── admin.html      # Admin dashboard
│   ├── 404.html        # Error page
│   ├── CSS/            # Stylesheets
│   └── JS/             # JavaScript files
└── README.md
```

---

## ⚙️ Configuration

Database settings are in `config.py`:

```python
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',        # Your MySQL password (blank for XAMPP)
    'database': 'metrosystemdb',
}
```

> If you use a different MySQL password, update `config.py` before running.

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| `Can't connect to MySQL` | Start XAMPP → Click Start next to MySQL |
| `Access denied for user 'root'` | Update password in `config.py` |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` |
| `Port 5000 in use` | Close other apps using port 5000 |
| `Database doesn't exist` | Run `python run.py` (auto-creates it) |

---

## 👨‍💻 Developed By

**Ronit Parmar** — Semester 3 Academic Project
