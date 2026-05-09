# AttendX — Employee Attendance System

## 🚀 Setup (3 steps)

### 1. Install Python dependencies
```bash
pip install flask flask-cors pyjwt bcrypt
```

### 2. Run the server
```bash
python server.py
```

### 3. Open browser
```
http://localhost:5000
```

---

## 🔑 Default Login

| Role  | Email               | Password  |
|-------|---------------------|-----------|
| Admin | admin@company.com   | admin123  |

---

## 📱 Features

### Employee
- Mark **Arrival** with one tap → time auto-saved
- Mark **Leaving** with one tap → time auto-saved
- View attendance history (5 / 10 / 15 / 30 days filter)
- See Present / Missed counts

### Admin
- Create employees (name, email, password)
- Delete employees
- View attendance of any employee
- View ALL employees attendance together
- Filter by 5 / 10 / 15 / 30 days

---

## 📁 Project Structure

```
attendance-app/
├── server.py          ← Flask backend (all APIs here)
├── attendance.db      ← SQLite database (auto-created)
├── public/
│   └── index.html     ← Full frontend (HTML + CSS + JS)
└── README.md
```

---

## 🔌 API Endpoints

| Method | URL | Description |
|--------|-----|-------------|
| POST | /api/login | Login |
| GET | /api/me | Get current user |
| POST | /api/attendance/mark-arrival | Mark arrival |
| POST | /api/attendance/mark-leaving | Mark leaving |
| GET | /api/attendance/my?days=N | My attendance |
| GET | /api/admin/employees | List employees |
| POST | /api/admin/employees | Create employee |
| DELETE | /api/admin/employees/:id | Delete employee |
| GET | /api/admin/attendance/:id?days=N | Employee attendance |
| GET | /api/admin/attendance/all?days=N | All attendance |
