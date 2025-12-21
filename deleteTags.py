import sqlite3
import json

conn = sqlite3.connect("database/db.db")
cursor = conn.cursor()

LIMIT = 1000
TARGET_TAGS = ["lamp", "stair", "staircase"]

cursor.execute("SELECT uid, tags FROM models")
rows = cursor.fetchall()

group = {tag: [] for tag in TARGET_TAGS}

# Gom UID theo tag
for uid, tags_json in rows:
    tags = [t["name"] for t in json.loads(tags_json)]
    for tg in TARGET_TAGS:
        if tg in tags:
            group[tg].append(uid)

# Xoá phần dư > 1000
uids_to_delete = []

for tg in TARGET_TAGS:
    if len(group[tg]) > LIMIT:
        extra = group[tg][LIMIT:]  # danh sách UID cần xoá
        uids_to_delete.extend(extra)

# Thực hiện xoá
if uids_to_delete:
    q = "DELETE FROM models WHERE uid IN ({})".format(
        ",".join(["?"] * len(uids_to_delete))
    )
    cursor.execute(q, uids_to_delete)
    conn.commit()

print("Đã xoá", len(uids_to_delete), "model dư thừa")
