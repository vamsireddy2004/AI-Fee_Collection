from app.database import check_database_connection

try:
    version = check_database_connection()
    print("SUCCESS: Connected to MySQL!")
    print(f"MySQL version: {version}")
except Exception as exc:
    print("FAILED: Could not connect to MySQL.")
    print(f"Error: {exc}")