# -----Load metadata and annotations for a specific object from the Objaverse dataset.

# import objaverse
# uids = objaverse.load_uids()[:1]
# annotations = objaverse.load_annotations(uids)
# info = annotations.get(uids[0])
# for k,v in info.items():
#     print(f"{k}: {v}")

# -----Run ChromaDB

# import chromadb
# client = chromadb.Client()
# collection = client.create_collection("my_docs")
# collection.add(
#     documents=["Hà Nội là thủ đô của Việt Nam", "TP.HCM là trung tâm kinh tế lớn"],
#     ids=["doc1", "doc2"]
# )
# results = collection.query(
#     query_texts=["thủ đô của Việt Nam là gì"],
#     n_results=1
# )
# print(results)

import sqlite3
import random

# Kết nối database
conn = sqlite3.connect('database/db.db')
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM models")
total_rows = cursor.fetchone()[0]

# Chọn ngẫu nhiên 1 ID (hoặc dùng OFFSET)
random_offset = random.randint(0, total_rows - 1)

cursor.execute(f"SELECT * FROM models LIMIT 1 OFFSET {random_offset}")
row = cursor.fetchone()

columns = [desc[0] for desc in cursor.description]  # Lấy tên các cột
for col, val in zip(columns, row):
    print(f"{col} : {val}")

conn.close()

# import sqlite3
# import json
# import pandas as pd
# import matplotlib.pyplot as plt

# furniture_tags = {
#     "chair", "sofa", "bench", "stool", 
#     "bed", "mattress", "crib",
#     "table", "desk", 
#     "cabinet", "shelf", "wardrobe", "rack", 
#     "lamp",
#     "stair", "door", "window", "partition",
#     "refrigerator", "oven", "microwave", "sink", "toilet", "bathtub", 
#     "computer", "monitor", "tv", "fireplace",
#     "rug", "curtain", "blind", "mirror", "clock", "pillow", "blanket", "vase"
# }

# conn = sqlite3.connect("database/db.db")
# cursor = conn.cursor()

# cursor.execute("SELECT tags FROM models")
# rows = cursor.fetchall()

# count_dict = {tag: 0 for tag in furniture_tags}

# for row in rows:
#     tags_json = json.loads(row[0])
#     for tag in tags_json:
#         name = tag["name"]
#         if name in count_dict:
#             count_dict[name] += 1

# # ❗ Loại bỏ những tag count = 0
# filtered = {tag: count for tag, count in count_dict.items() if count > 0}

# df = pd.DataFrame(list(filtered.items()), columns=["tag", "count"])

# # Vẽ biểu đồ
# plt.figure(figsize=(12, 6))
# bars = plt.bar(df["tag"], df["count"])

# # Thêm số lên đầu mỗi cột
# for bar in bars:
#     height = bar.get_height()
#     plt.text(
#         bar.get_x() + bar.get_width() / 2,
#         height,
#         str(height),
#         ha='center',
#         va='bottom',
#         fontsize=9
#     )

# plt.xticks(rotation=90)
# plt.tight_layout()
# plt.show()
