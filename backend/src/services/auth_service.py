from ..db import get_conn
from ..security import hash_password

def find_user(email: str):
    with get_conn() as conn:
        return conn.execute("SELECT id,email,name,role,password_hash FROM users WHERE email=%s", (email,)).fetchone()

def ensure_users():
    users = [
        ("ta@donglan.edu", "林若溪", "ta"),
        ("teacher@donglan.edu", "周明远", "teacher"),
        ("admin@donglan.edu", "沈老师", "college_admin"),
    ]
    with get_conn() as conn:
        for email, name, role in users:
            conn.execute("""INSERT INTO users(email,name,role,password_hash) VALUES (%s,%s,%s,%s)
                ON CONFLICT(email) DO UPDATE SET name=EXCLUDED.name, role=EXCLUDED.role""", (email, name, role, hash_password("campus123")))
