import sqlite3
import jwt
import datetime
import os
import json

DB_FILE = 'gateway.db'
SECRET_KEY = "jwt_secret_key_uts_secure"
AUDIT_LOG_FILE = 'audit.json'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT,
            clearance INTEGER  -- Level 3: Secret, Level 2: Confidential, Level 1: Public
        )
    ''')
    
    cursor.execute("INSERT OR IGNORE INTO users (username, password, role, clearance) VALUES ('admin', 'admin123', 'Admin', 3)")
    cursor.execute("INSERT OR IGNORE INTO users (username, password, role, clearance) VALUES ('staff', 'staff123', 'Staff', 2)")
    cursor.execute("INSERT OR IGNORE INTO users (username, password, role, clearance) VALUES ('public', 'public123', 'Public', 1)")
    conn.commit()
    conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT username, role, clearance FROM users WHERE username=? AND password=?", (username, password))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        token = jwt.encode({
            'username': user[0],
            'role': user[1],
            'clearance': user[2],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=2)
        }, SECRET_KEY, algorithm="HS256")
        return token, user[1], user[2]
    return None, None, None

def verify_token(token):
    try:
        decoded = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return decoded
    except Exception:
        return None

def check_bell_lapadula_read(user_clearance, file_required_clearance=3):
    """
    Bell-LaPadula Model: "No Read Up" (Simple Security Property)
    User hanya boleh membaca file jika user_clearance >= file_required_clearance.
    Jika file berlabel 'secret' (clearance 3) dan user adalah 'public' (clearance 1) -> DENY!
    """
    return user_clearance >= file_required_clearance

def write_audit_log(username, action, filename, sha256_hash, source_node, status="ALLOW"):
    """Mencatat aktivitas akses dan status ALLOW / DENY ke Audit Log"""
    log_entry = {
        'timestamp': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'username': username,
        'action': action,
        'filename': filename,
        'sha256_hash': sha256_hash,
        'source_node': source_node,
        'status': status
    }
    
    logs = []
    if os.path.exists(AUDIT_LOG_FILE):
        try:
            with open(AUDIT_LOG_FILE, 'r') as f:
                logs = json.load(f)
        except Exception:
            logs = []
            
    logs.append(log_entry)
    with open(AUDIT_LOG_FILE, 'w') as f:
        json.dump(logs, f, indent = 4)