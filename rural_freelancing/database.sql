-- Run once:  mysql -u root -p < database.sql
CREATE DATABASE IF NOT EXISTS rural_freelancing CHARACTER SET utf8mb4;
USE rural_freelancing;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('client','worker','admin') NOT NULL,
  phone VARCHAR(15) NOT NULL,
  village VARCHAR(100) DEFAULT '',
  latitude DOUBLE NULL,
  longitude DOUBLE NULL,
  language VARCHAR(10) DEFAULT 'en-IN',
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(60) NOT NULL UNIQUE,
  icon VARCHAR(10) NOT NULL
);

CREATE TABLE IF NOT EXISTS worker_profiles (
  user_id INT PRIMARY KEY,
  skills VARCHAR(255) DEFAULT '',
  bio TEXT,
  experience_years INT DEFAULT 0,
  available TINYINT(1) DEFAULT 1,
  photo VARCHAR(255) DEFAULT NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS services (
  id INT AUTO_INCREMENT PRIMARY KEY,
  worker_id INT NOT NULL,
  category_id INT NOT NULL,
  title VARCHAR(120) NOT NULL,
  description TEXT,
  price DECIMAL(10,2) NOT NULL,
  price_unit VARCHAR(20) DEFAULT 'per day',
  image VARCHAR(255) DEFAULT NULL,
  FOREIGN KEY (worker_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (category_id) REFERENCES categories(id)
);

CREATE TABLE IF NOT EXISTS bookings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  client_id INT NOT NULL,
  worker_id INT NOT NULL,
  service_id INT NOT NULL,
  status ENUM('PENDING','ACCEPTED','REJECTED','CONFIRMED','IN_PROGRESS','COMPLETED','CANCELLED') DEFAULT 'PENDING',
  scheduled_date DATE NOT NULL,
  address VARCHAR(255) NOT NULL,
  notes TEXT,
  offered_price DECIMAL(10,2) NULL,
  offered_by ENUM('client','worker') NULL,
  agreed_price DECIMAL(10,2) NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (client_id) REFERENCES users(id),
  FOREIGN KEY (worker_id) REFERENCES users(id),
  FOREIGN KEY (service_id) REFERENCES services(id)
);

CREATE TABLE IF NOT EXISTS messages (
  id INT AUTO_INCREMENT PRIMARY KEY,
  booking_id INT NOT NULL,
  sender_id INT NULL,               -- NULL = system message
  body VARCHAR(500) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
  id INT AUTO_INCREMENT PRIMARY KEY,
  booking_id INT NOT NULL UNIQUE,
  client_id INT NOT NULL,
  worker_id INT NOT NULL,
  rating TINYINT NOT NULL,
  comment VARCHAR(500),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS call_requests (
  id INT AUTO_INCREMENT PRIMARY KEY,
  booking_id INT NOT NULL,
  caller_id INT NOT NULL,
  mode VARCHAR(10) NOT NULL DEFAULT 'demo',
  provider_sid VARCHAR(64) NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS unavailable_dates (
  id INT AUTO_INCREMENT PRIMARY KEY,
  worker_id INT NOT NULL,
  off_date DATE NOT NULL,
  UNIQUE KEY uq_worker_day (worker_id, off_date),
  FOREIGN KEY (worker_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS complaints (
  id INT AUTO_INCREMENT PRIMARY KEY,
  booking_id INT NOT NULL,
  complainant_id INT NOT NULL,
  against_id INT NOT NULL,
  subject VARCHAR(120) NOT NULL,
  body VARCHAR(1000) NOT NULL,
  status ENUM('OPEN','RESOLVED') NOT NULL DEFAULT 'OPEN',
  admin_note VARCHAR(500) NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
  FOREIGN KEY (complainant_id) REFERENCES users(id),
  FOREIGN KEY (against_id) REFERENCES users(id)
);

INSERT IGNORE INTO categories (name, icon) VALUES
 ('Tractor Operation','🚜'),('Harvesting','🌾'),('Irrigation','💧'),
 ('Electrician','⚡'),('Plumber','🔧'),('Carpenter','🪚'),
 ('Mason','🧱'),('Farming Assistance','🧑‍🌾'),('Repair Services','🛠️');
