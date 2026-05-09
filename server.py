from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import bcrypt
import jwt
import os
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__, static_folder='public')
CORS(app)

SECRET_KEY = os.environ.get("SECRET_KEY", "attendance_secret_key_2024")

# ─────────────────────────────────────────
# DATABASE — PostgreSQL ya SQLite auto-detect
# ─────────────────────────────────────────
# Railway pe DATABASE_URL env variable hoti hai → PostgreSQL use hoga
# Local pe nahi hoti → SQLite use hoga
# Tu kuch nahi karta — apne aap handle ho jaata hai

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    import psycopg2
    import psycopg2.extras

    # Railway ka URL "postgres://" se shuru hota hai
    # psycopg2 ko "postgresql://" chahiye
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    def get_db():
        conn = psycopg2.connect(DATABASE_URL)
        return conn

    def fetchall(cursor):
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def fetchone(cursor):
        if cursor.description is None:
            return None
        cols = [desc[0] for desc in cursor.description]
        row = cursor.fetchone()
        return dict(zip(cols, row)) if row else None

    PG = True
    print("🐘 PostgreSQL mode (Railway)")

else:
    import sqlite3
    DB_PATH = "attendance.db"

    def get_db():
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def fetchall(cursor):
        return [dict(r) for r in cursor.fetchall()]

    def fetchone(cursor):
        row = cursor.fetchone()
        return dict(row) if row else None

    PG = False
    print("🗃️  SQLite mode (local)")


def ph():
    """SQLite me ? PostgreSQL me %s"""
    return '%s' if PG else '?'

def placeholder(n):
    """n tadi placeholders"""
    p = '%s' if PG else '?'
    return ','.join([p] * n)


# ─────────────────────────────────────────
# DATABASE INIT
# ─────────────────────────────────────────

def init_db():
    conn = get_db()
    c = conn.cursor()

    if PG:
        c.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'employee',
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id SERIAL PRIMARY KEY,
                employee_id INTEGER NOT NULL REFERENCES employees(id),
                date TEXT NOT NULL,
                arrival_time TEXT,
                leaving_time TEXT,
                status TEXT DEFAULT 'present',
                UNIQUE(employee_id, date)
            )
        ''')
    else:
        c.execute('''
            CREATE TABLE IF NOT EXISTS employees (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT DEFAULT 'employee',
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        ''')
        c.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                arrival_time TEXT,
                leaving_time TEXT,
                status TEXT DEFAULT 'present',
                FOREIGN KEY (employee_id) REFERENCES employees(id),
                UNIQUE(employee_id, date)
            )
        ''')

    c.execute("SELECT id FROM employees WHERE role='admin'")
    admin_exists = fetchone(c)
    if not admin_exists:
        hashed = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        c.execute(
            f"INSERT INTO employees (name, email, password, role) VALUES ({placeholder(4)})",
            ("Admin", "admin@company.com", hashed, "admin")
        )

    conn.commit()
    conn.close()
    print("✅ Database ready")
    print("👤 Admin → admin@company.com / admin123")


# ─────────────────────────────────────────
# MISSING DAYS FILL
# ─────────────────────────────────────────

def fill_missing_days(records, days):
    today = datetime.now().date()
    existing_dates = {r['date'] for r in records}
    full_records = list(records)

    for i in range(1, days + 1):
        day = today - timedelta(days=i)
        day_str = day.strftime('%Y-%m-%d')
        if day_str not in existing_dates:
            full_records.append({
                'date': day_str,
                'arrival_time': None,
                'leaving_time': None,
                'status': 'missed'
            })

    full_records.sort(key=lambda x: x['date'], reverse=True)
    return full_records


# ─────────────────────────────────────────
# JWT MIDDLEWARE
# ─────────────────────────────────────────

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({"error": "Token missing"}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user = data
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({"error": "Token missing"}), 401
        try:
            data = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            if data.get('role') != 'admin':
                return jsonify({"error": "Admin access required"}), 403
            request.user = data
        except:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT * FROM employees WHERE email = {ph()}", (email,))
    user = fetchone(c)
    conn.close()

    if not user:
        return jsonify({"error": "Invalid email or password"}), 401
    if not bcrypt.checkpw(password.encode(), user['password'].encode()):
        return jsonify({"error": "Invalid email or password"}), 401

    token = jwt.encode({
        "id": user['id'],
        "name": user['name'],
        "email": user['email'],
        "role": user['role'],
        "exp": datetime.utcnow() + timedelta(hours=12)
    }, SECRET_KEY, algorithm="HS256")

    return jsonify({
        "token": token,
        "user": {"id": user['id'], "name": user['name'], "email": user['email'], "role": user['role']}
    })


# ─────────────────────────────────────────
# ADMIN ROUTES
# ─────────────────────────────────────────

@app.route('/api/admin/employees', methods=['GET'])
@admin_required
def get_all_employees():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, name, email, role, created_at FROM employees WHERE role='employee' ORDER BY name")
    employees = fetchall(c)
    conn.close()
    return jsonify(employees)


@app.route('/api/admin/employees', methods=['POST'])
@admin_required
def create_employee():
    data = request.json
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '').strip()

    if not name or not email or not password:
        return jsonify({"error": "Name, email and password required"}), 400

    hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute(
            f"INSERT INTO employees (name, email, password, role) VALUES ({placeholder(4)})",
            (name, email, hashed, 'employee')
        )
        conn.commit()
        conn.close()
        return jsonify({"message": f"Employee '{name}' created successfully"})
    except Exception:
        return jsonify({"error": "Email already exists"}), 400


@app.route('/api/admin/employees/<int:emp_id>', methods=['DELETE'])
@admin_required
def delete_employee(emp_id):
    conn = get_db()
    c = conn.cursor()
    c.execute(f"DELETE FROM attendance WHERE employee_id = {ph()}", (emp_id,))
    c.execute(f"DELETE FROM employees WHERE id = {ph()} AND role = 'employee'", (emp_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Employee deleted"})


@app.route('/api/admin/attendance/<int:emp_id>', methods=['GET'])
@admin_required
def get_employee_attendance(emp_id):
    days = request.args.get('days', 30, type=int)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT id, name, email FROM employees WHERE id = {ph()}", (emp_id,))
    emp = fetchone(c)

    if not emp:
        conn.close()
        return jsonify({"error": "Employee not found"}), 404

    c.execute(f'''
        SELECT date, arrival_time, leaving_time, status
        FROM attendance
        WHERE employee_id = {ph()} AND date >= {ph()}
        ORDER BY date DESC
    ''', (emp_id, since))
    records = fetchall(c)
    conn.close()

    filled = fill_missing_days(records, days)
    return jsonify({
        "employee": emp,
        "records": filled,
        "total_days": len(filled),
        "present_days": len([r for r in filled if r['status'] == 'present']),
        "missed_days": len([r for r in filled if r['status'] == 'missed'])
    })


@app.route('/api/admin/attendance/all', methods=['GET'])
@admin_required
def get_all_attendance():
    days = request.args.get('days', 7, type=int)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    conn = get_db()
    c = conn.cursor()
    c.execute(f'''
        SELECT e.name, e.email, a.date, a.arrival_time, a.leaving_time, a.status
        FROM attendance a
        JOIN employees e ON a.employee_id = e.id
        WHERE a.date >= {ph()}
        ORDER BY a.date DESC, e.name
    ''', (since,))
    records = fetchall(c)
    conn.close()
    return jsonify(records)


# ─────────────────────────────────────────
# EMPLOYEE ROUTES
# ─────────────────────────────────────────

@app.route('/api/attendance/mark-arrival', methods=['POST'])
@token_required
def mark_arrival():
    emp_id = request.user['id']
    today = datetime.now().strftime('%Y-%m-%d')
    now_time = datetime.now().strftime('%H:%M:%S')

    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT * FROM attendance WHERE employee_id = {ph()} AND date = {ph()}", (emp_id, today))
    existing = fetchone(c)

    if existing:
        if existing['arrival_time']:
            conn.close()
            return jsonify({"error": "Arrival already marked today"}), 400
        c.execute(
            f"UPDATE attendance SET arrival_time = {ph()}, status = 'present' WHERE employee_id = {ph()} AND date = {ph()}",
            (now_time, emp_id, today)
        )
    else:
        c.execute(
            f"INSERT INTO attendance (employee_id, date, arrival_time, status) VALUES ({placeholder(4)})",
            (emp_id, today, now_time, 'present')
        )

    conn.commit()
    conn.close()
    return jsonify({"message": "Arrival marked!", "time": now_time, "date": today})


@app.route('/api/attendance/mark-leaving', methods=['POST'])
@token_required
def mark_leaving():
    emp_id = request.user['id']
    today = datetime.now().strftime('%Y-%m-%d')
    now_time = datetime.now().strftime('%H:%M:%S')

    conn = get_db()
    c = conn.cursor()
    c.execute(f"SELECT * FROM attendance WHERE employee_id = {ph()} AND date = {ph()}", (emp_id, today))
    existing = fetchone(c)

    if not existing or not existing['arrival_time']:
        conn.close()
        return jsonify({"error": "Please mark arrival first"}), 400
    if existing['leaving_time']:
        conn.close()
        return jsonify({"error": "Leaving already marked today"}), 400

    c.execute(
        f"UPDATE attendance SET leaving_time = {ph()} WHERE employee_id = {ph()} AND date = {ph()}",
        (now_time, emp_id, today)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": "Leaving marked!", "time": now_time, "date": today})


@app.route('/api/attendance/my', methods=['GET'])
@token_required
def my_attendance():
    emp_id = request.user['id']
    days = request.args.get('days', 30, type=int)
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    conn = get_db()
    c = conn.cursor()
    c.execute(f'''
        SELECT date, arrival_time, leaving_time, status
        FROM attendance
        WHERE employee_id = {ph()} AND date >= {ph()}
        ORDER BY date DESC
    ''', (emp_id, since))
    db_records = fetchall(c)

    today = datetime.now().strftime('%Y-%m-%d')
    c.execute(f"SELECT * FROM attendance WHERE employee_id = {ph()} AND date = {ph()}", (emp_id, today))
    today_record = fetchone(c)
    conn.close()

    records = fill_missing_days(db_records, days)
    return jsonify({
        "records": records,
        "today": today_record,
        "total_days": len(records),
        "present_days": len([r for r in records if r['status'] == 'present']),
        "missed_days": len([r for r in records if r['status'] == 'missed'])
    })


@app.route('/api/me', methods=['GET'])
@token_required
def get_me():
    return jsonify(request.user)


# ─────────────────────────────────────────
# FRONTEND SERVE
# ─────────────────────────────────────────

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('public', path)


# ─────────────────────────────────────────
# START
# ─────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    print("🚀 Server → http://localhost:5000")
    app.run(debug=True, port=5000)
