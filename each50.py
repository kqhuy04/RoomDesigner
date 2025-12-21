import sqlite3
import json
import pandas as pd
import matplotlib.pyplot as plt

furniture_tags = [
    "chair", "sofa", "bench", "stool", "armchair", "recliner", "ottoman", "bean_bag",
    "bed", "mattress", "crib", "bunk_bed", "futon",
    "table", "desk", "nightstand", "coffee_table", "dining_table", "console_table",
    "cabinet", "shelf", "bookshelf", "wardrobe", "dresser", "chest_of_drawers", 
    "closet", "rack", "shoe_rack", "coat_rack",
    "lamp", "floor_lamp", "table_lamp", "chandelier", "ceiling_light",
    "stair", "staircase", "door", "window", "partition", "room_divider",
    "kitchen_cabinet", "kitchen_island", "pantry", "spice_rack", "pot_rack",
    "vanity", "mirror", "towel_rack", "shower_caddy", "bath_mat",
    "patio_table", "patio_chair", "hammock", "swing", "garden_bench",
    "rug", "carpet", "curtain", "blind", "pillow", "blanket", "vase", "plant_stand",
    "office_desk", "office_chair", "file_cabinet", "whiteboard",
    "tv_stand", "television", "tv", "fireplace", "clock", "picture_frame", 
    "pet_bed", "toy_chest"
]

conn = sqlite3.connect("database/db.db")
cursor = conn.cursor()

cursor.execute("SELECT tags FROM models")
rows = cursor.fetchall()

count_dict = {tag: 0 for tag in furniture_tags}

for row in rows:
    tags_json = json.loads(row[0])
    for tag in tags_json:
        name = tag["name"]
        if name in count_dict:
            count_dict[name] += 1

# ❗ Áp dụng giới hạn 50 model cho mỗi tag
capped_dict = {tag: min(count, 50) for tag, count in count_dict.items()}

# Loại bỏ tag = 0 nếu muốn
filtered = {tag: count for tag, count in capped_dict.items() if count > 0}

# Tính tổng số model sau khi đã cap 50/tag
total_capped_models = sum(filtered.values())

print(f"Tổng số model (mỗi tag tối đa 50): {total_capped_models}")
print("-" * 50)

# In chi tiết từng tag (tuỳ chọn)
for tag, count in sorted(filtered.items(), key=lambda x: x[1], reverse=True):
    original = count_dict[tag]
    print(f"{tag:15} → {count:3} (gốc: {original})")

# Vẽ biểu đồ (hiển thị giá trị đã capped)
df = pd.DataFrame(list(filtered.items()), columns=["tag", "count"])
df = df.sort_values("count", ascending=False)  # sắp xếp giảm dần cho đẹp

plt.figure(figsize=(15, 8))
bars = plt.bar(df["tag"], df["count"], color='skyblue', edgecolor='navy', linewidth=0.7)

# Thêm số lên đầu cột
for bar in bars:
    height = bar.get_height()
    plt.text(
        bar.get_x() + bar.get_width() / 2,
        height + 0.5,
        str(int(height)),
        ha='center',
        va='bottom',
        fontsize=9,
        fontweight='bold'
    )

plt.title(f"Thống kê Furniture Tags (mỗi tag tối đa 50 model) - Tổng: {total_capped_models} models", 
          fontsize=14, pad=20)
plt.ylabel("Số lượng model (capped ≤50)")
plt.xticks(rotation=90)
plt.grid(axis='y', linestyle='--', alpha=0.3)
plt.tight_layout()
plt.show()

conn.close()