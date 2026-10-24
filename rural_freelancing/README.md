# 🌾 Empowering Rural Areas Through Digital Freelancing

A web-based platform that connects **rural clients with nearby skilled workers** such as tractor operators, electricians, plumbers, carpenters, harvesting teams, and more.

Built as a **Final-Year Project** by the Department of Information Science & Engineering.

## 🚀 Tech Stack

- **Frontend:** HTML5, CSS3, JavaScript, Bootstrap 5
- **Backend:** Python, Flask
- **Database:** MySQL
- **PWA:** Progressive Web App
- **Testing:** pytest
- **Communication:** Web Speech API, Twilio

## ✨ Key Features

- 🔐 Secure registration, login & password hashing
- 👥 **Client, Worker & Admin** role-based access
- 👷 Worker profiles with skills, experience, availability & photos
- 🛠️ Service listing with pricing and service images
- 📍 Location-based worker matching using **Geolocation + Haversine formula**
- 🔎 Filtering by category, price, availability, date & distance
- 📅 Booking and scheduling with **no double-booking**
- 💬 In-app chat for bookings
- 📞 Optional **masked calling using Twilio**
- 🤝 Price negotiation between clients and workers
- ⭐ Ratings & reviews after completed bookings
- 🚨 Complaint reporting and admin management
- 🌐 English, Hindi & Kannada interface
- 🎤 Voice search in English, Hindi, Kannada, Tamil & Telugu
- 📱 Installable **PWA** with responsive mobile design
- 🛡️ CSRF protection, parameterized SQL, upload validation & secure environment variables
- 🧪 **47 automated pytest tests**

## 🧠 How It Works

**Client Request → Worker Matching → Booking → Negotiation → Communication → Service Completion → Rating**

Workers are matched based on **service, location, availability, price and rating**.

Distance is calculated using the **Haversine formula** and workers can be filtered within **1, 5, 10 or 25 km**.

## 📁 Project Structure

```text
rural_freelancing/
├── app.py
├── config.py
├── translations.py
├── database.sql
├── migration_v2.sql
├── seed.py
├── create_admin.py
├── tests/
├── static/
└── templates/
```

## ⚙️ Setup

### 1. Create virtual environment

```bash
python -m venv venv
venv\Scripts\activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create MySQL database

Run `database.sql` using MySQL Workbench or MySQL command line.

For an existing v1 database, run:

```text
migration_v2.sql
```

### 4. Set environment variables

```powershell
$env:SECRET_KEY="your-secret-key"
$env:DB_PASSWORD="your-mysql-password"
```

### 5. Run the application

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## 🧪 Run Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

The test suite uses a separate database so real application data is not affected.

## 📞 Optional Twilio Calling

For real masked calling, configure:

```text
TWILIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN
TWILIO_NUMBER
```

Without Twilio configuration, the application provides a clearly labelled simulation.

## 🔮 Future Enhancements

- 💳 Razorpay / UPI payments
- 🗺️ Maps integration
- 📱 Native Android application
- 💬 WebSocket-based real-time chat
- 📧 Email/SMS notifications
- 🌐 Tamil & Telugu interface
- 🤖 AI/image-based service recognition

## 👩‍💻 Project

**Empowering Rural Areas Through Digital Freelancing and Skill-Based Opportunities**

Aims to make **local skills easier to discover, hire and monetize**, while creating digital employment opportunities in rural communities.