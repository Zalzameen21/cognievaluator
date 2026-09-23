import sqlite3
conn = sqlite3.connect('db.sqlite3')
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
for t in tables:
    tname = t[0]
    if not tname.startswith('auth_') and not tname.startswith('django_') and tname not in ('evaluator_app_location', 'evaluator_app_userprofile') and tname != 'sqlite_sequence':
        print("Cleaning table:", tname)
        cursor.execute(f"DELETE FROM {tname}")
conn.commit()
conn.close()
