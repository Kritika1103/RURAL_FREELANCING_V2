-- Upgrade an EXISTING database (the one you already created) to the new schema.
-- Run ONCE.  Keeps all your current users, bookings and messages.
--   mysql> source C:/path/to/migration_v2.sql
USE rural_freelancing;

ALTER TABLE users MODIFY role ENUM('client','worker','admin') NOT NULL;
ALTER TABLE users ADD COLUMN is_active TINYINT(1) NOT NULL DEFAULT 1;
ALTER TABLE services ADD COLUMN image VARCHAR(255) DEFAULT NULL;
ALTER TABLE call_requests ADD COLUMN mode VARCHAR(10) NOT NULL DEFAULT 'demo';
ALTER TABLE call_requests ADD COLUMN provider_sid VARCHAR(64) NULL;

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
