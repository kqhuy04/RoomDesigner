import sqlite3
import json

DB_PATH = "database/db.db"  # sửa lại path nếu cần

conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Tạo bảng mới với cấu trúc giống bảng cũ
cursor.execute("""
CREATE TABLE IF NOT EXISTS models_bed AS
SELECT *
FROM models
WHERE 0;
""")

cursor.execute("SELECT * FROM models")
rows = cursor.fetchall()

# Lấy tên các cột để insert đúng thứ tự
col_names = [description[0] for description in cursor.description]
col_placeholders = ",".join(["?"] * len(col_names))
insert_sql = f"INSERT INTO models_bed ({','.join(col_names)}) VALUES ({col_placeholders})"

count = 0

for row in rows:
    tags_index = col_names.index("tags")
    tags_json = json.loads(row[tags_index])
    tag_names = [t["name"] for t in tags_json]

    if "bed" in tag_names:
        cursor.execute(insert_sql, row)
        count += 1

conn.commit()
conn.close()

print("Đã copy", count, "models vào bảng models_bed")
