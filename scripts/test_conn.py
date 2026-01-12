import psycopg2
from dotenv import load_dotenv
import os
load_dotenv()

print("Тест 1: postgres база (системная)")
conn = psycopg2.connect(
    host="localhost", port=5432, dbname="postgres",
    user="postgres", password="password"
)
print("✅ postgres OK")
conn.close()

print("Тест 2: video_stats база")
try:
    conn = psycopg2.connect(
        host="localhost", port=5432, dbname="video_stats",
        user="postgres", password="password"
    )
    print("✅ video_stats OK")
    conn.close()
except Exception as e:
    print(f"❌ video_stats ERROR: {e}")
