import datetime

import mysql.connector
from mysql.connector import Error as MySQLError

from config import DB_CONFIG

SEED_DOCTORS = [
    ("Dr. Aravind", "Cardiology"),
    ("Dr. Meenakshi Srinivasan", "Cardiology"),
    ("Dr. Priya", "Dermatology"),
    ("Dr. Karthik", "Dermatology"),
    ("Dr. Ram Kumar", "Pediatrics"),
    ("Dr. Suresh Kumar", "General Medicine"),
]

WORK_START_HOUR = 9
WORK_END_HOUR = 17
SLOT_MINUTES = 30
SCHEDULE_DAYS_AHEAD = 7

def connect():
    params = dict(DB_CONFIG)

    try:
        dbConn = mysql.connector.connect(**params)
        return dbConn
    except MySQLError as e:
        if e.errno == 1049:  # ER_BAD_DB_ERROR
            print(f"Database '{DB_CONFIG['database']}' does not exist yet. Creating it...")
            server_conn = connect()
        print(f"Error: Could not connect to MySQL at {DB_CONFIG['host']}:{DB_CONFIG['port']}: {e}")
        print("  Check that MySQL is running and DB_USER/DB_PASSWORD in .env are correct.")
        return None
    except Exception as e:
        print(f"Error: Unexpected error connecting to database: {e}")
        return None

def ensure_schema(conn):
    """Create tables if missing. Returns True/False."""
    statements = [
        """
        CREATE TABLE IF NOT EXISTS patients (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            phone VARCHAR(30) NOT NULL UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS doctors (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(150) NOT NULL,
            specialty VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            patient_id INT NOT NULL,
            doctor_id INT NOT NULL,
            appointment_time DATETIME NOT NULL,
            status ENUM('booked', 'cancelled') NOT NULL DEFAULT 'booked',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (doctor_id) REFERENCES doctors(id)
        )
        """,
    ]
    try:
        cursor = conn.cursor()
        for stmt in statements:
            cursor.execute(stmt)
        conn.commit()
        cursor.close()
        print("✓ Schema ready (patients, doctors, appointments)")
        return True
    except MySQLError as e:
        print(f"✗ Error: Could not create schema: {e}")
        return False

def seed_doctors_if_empty(conn):
    """Insert sample doctors if the doctors table is currently empty."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM doctors")
        (count,) = cursor.fetchone()
        if count > 0:
            cursor.close()
            print(f"Doctors table already has {count} doctor(s) — skipping seed")
            return True

        cursor.executemany(
            "INSERT INTO doctors (name, specialty) VALUES (%s, %s)", SEED_DOCTORS
        )
        conn.commit()
        cursor.close()
        print(f"Seeded {len(SEED_DOCTORS)} sample doctors")
        return True
    except MySQLError as e:
        print(f"Error: Could not seed doctors: {e}")
        return False

def init_database():
    """Connect, ensure schema, seed sample data. Returns a live connection or None."""
    conn = connect()
    if conn is None:
        return None
    if not ensure_schema(conn):
        conn.close()
        return None
    if not seed_doctors_if_empty(conn):
        conn.close()
        return None
    return conn

# Patient lookup / creation 
def get_or_create_patient(conn, name, phone):
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, phone FROM patients WHERE phone = %s", (phone,))
    row = cursor.fetchone()
    if row:
        cursor.close()
        return row, False

    cursor.execute("INSERT INTO patients (name, phone) VALUES (%s, %s)", (name, phone))
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    return {"id": new_id, "name": name, "phone": phone}, True


#  Doctors 
def list_doctors(conn, specialty=None):
    cursor = conn.cursor(dictionary=True)
    if specialty:
        cursor.execute(
            "SELECT id, name, specialty FROM doctors WHERE specialty LIKE %s ORDER BY name",
            (f"%{specialty}%",),
        )
    else:
        cursor.execute("SELECT id, name, specialty FROM doctors ORDER BY specialty, name")
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_doctor(conn, doctor_id):
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT id, name, specialty FROM doctors WHERE id = %s", (doctor_id,))
    row = cursor.fetchone()
    cursor.close()
    return row

def _generate_candidate_slots(days_ahead=SCHEDULE_DAYS_AHEAD):
    slots = []
    today = datetime.date.today()
    for offset in range(1, days_ahead + 1):
        day = today + datetime.timedelta(days=offset)
        if day.weekday() >= 5:  # Saturday/Sunday
            continue
        start = datetime.datetime.combine(day, datetime.time(hour=WORK_START_HOUR))
        end = datetime.datetime.combine(day, datetime.time(hour=WORK_END_HOUR))
        current = start
        while current < end:
            slots.append(current)
            current += datetime.timedelta(minutes=SLOT_MINUTES)
    return slots

def get_booked_times(conn, doctor_id):
    cursor = conn.cursor()
    cursor.execute(
        "SELECT appointment_time FROM appointments WHERE doctor_id = %s AND status = 'booked'",
        (doctor_id,),
    )
    booked = {row[0] for row in cursor.fetchall()}
    cursor.close()
    return booked

def get_available_slots(conn, doctor_id, date=None):
    booked = get_booked_times(conn, doctor_id)
    candidates = _generate_candidate_slots()
    if date is not None:
        candidates = [c for c in candidates if c.date() == date]
    return [c for c in candidates if c not in booked]

def is_slot_available(conn, doctor_id, when):
    booked = get_booked_times(conn, doctor_id)
    if when in booked:
        return False
    weekday_ok = when.weekday() < 5
    time_ok = WORK_START_HOUR <= when.hour < WORK_END_HOUR
    return weekday_ok and time_ok


#  Appointments 
def book_appointment(conn, patient_id, doctor_id, when):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO appointments (patient_id, doctor_id, appointment_time, status)
        VALUES (%s, %s, %s, 'booked')
        """,
        (patient_id, doctor_id, when),
    )
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    return new_id


def list_appointments(conn, patient_id, status=None):
    cursor = conn.cursor(dictionary=True)
    query = """
        SELECT a.id, a.appointment_time, a.status, d.name AS doctor_name, d.specialty
        FROM appointments a
        JOIN doctors d ON d.id = a.doctor_id
        WHERE a.patient_id = %s
    """
    params = [patient_id]
    if status:
        query += " AND a.status = %s"
        params.append(status)
    query += " ORDER BY a.appointment_time"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    cursor.close()
    return rows


def get_appointment(conn, appointment_id, patient_id):
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, doctor_id, appointment_time, status FROM appointments "
        "WHERE id = %s AND patient_id = %s",
        (appointment_id, patient_id),
    )
    row = cursor.fetchone()
    cursor.close()
    return row


def cancel_appointment(conn, appointment_id, patient_id):
    appt = get_appointment(conn, appointment_id, patient_id)
    if appt is None:
        return False, "not_found"
    if appt["status"] == "cancelled":
        return False, "already_cancelled"
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE appointments SET status = 'cancelled' WHERE id = %s", (appointment_id,)
    )
    conn.commit()
    cursor.close()
    return True, "cancelled"


def reschedule_appointment(conn, appointment_id, patient_id, new_when):
    appt = get_appointment(conn, appointment_id, patient_id)
    if appt is None:
        return False, "not_found"
    if appt["status"] != "booked":
        return False, "not_active"
    if not is_slot_available(conn, appt["doctor_id"], new_when):
        return False, "slot_taken"
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE appointments SET appointment_time = %s WHERE id = %s",
        (new_when, appointment_id),
    )
    conn.commit()
    cursor.close()
    return True, "rescheduled"