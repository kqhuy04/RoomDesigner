import sqlite3
import json
import random

# =========================================
# CẤU HÌNH
# =========================================
DB_PATH = "database/db.db"
MAX_PER_TAG = 50

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

# =========================================
# BƯỚC 1: Tạo bảng each_50_models (cùng cấu trúc models)
# =========================================
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

cursor.execute("DROP TABLE IF EXISTS each_50_models")

cursor.execute("""
CREATE TABLE each_50_models (
    uid TEXT PRIMARY KEY NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    uri TEXT,
    viewer_url TEXT,
    embed_url TEXT,
    
    view_count INTEGER DEFAULT 0,
    like_count INTEGER DEFAULT 0,
    comment_count INTEGER DEFAULT 0,
    animation_count INTEGER DEFAULT 0,
    
    is_downloadable BOOLEAN DEFAULT 0,
    is_age_restricted BOOLEAN DEFAULT 0,
    staff_picked_at TIMESTAMP,
    published_at TIMESTAMP,
    created_at TIMESTAMP,
    
    face_count INTEGER,
    vertex_count INTEGER,
    license TEXT,
    
    tags TEXT,
    thumbnails TEXT,
    archives TEXT,
    categories TEXT,
    user_info TEXT,
    
    created_db_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    selected_tag TEXT
)
""")

cursor.execute("CREATE INDEX IF NOT EXISTS idx_each50_tags ON each_50_models(tags)")
conn.commit()
print("Bảng 'each_50_models' đã sẵn sàng!")

# =========================================
# BƯỚC 2: Thu thập model theo tag
# =========================================
tag_to_models = {tag: [] for tag in furniture_tags}

print("Đang quét toàn bộ models để phân loại theo tag...")
cursor.execute("SELECT uid, tags FROM models")
rows = cursor.fetchall()

for uid, tags_json in rows:
    try:
        tags_list = json.loads(tags_json)
        model_tags = {t["name"].lower() for t in tags_list}  # chuẩn hóa lowercase
        for tag in furniture_tags:
            if tag in model_tags:
                tag_to_models[tag].append(uid)
    except:
        continue

# =========================================
# BƯỚC 3: Chọn 50 model mỗi tag + chèn vào bảng mới (không trùng)
# =========================================
already_inserted = set()  # tránh trùng model
total_inserted = 0

# Lấy danh sách tất cả uid đã chèn
cursor.execute("SELECT uid FROM each_50_models")
for row in cursor.fetchall():
    already_inserted.add(row[0])

for tag in furniture_tags:
    candidate_uids = tag_to_models[tag]
    if not candidate_uids:
        continue
    
    # Lọc bỏ những cái đã chèn rồi
    available = [uid for uid in candidate_uids if uid not in already_inserted]
    
    # Chọn tối đa 50 (random để đa dạng)
    if len(available) > MAX_PER_TAG:
        selected_uids = random.sample(available, MAX_PER_TAG)
    else:
        selected_uids = available[:MAX_PER_TAG]
    
    # Copy nguyên row từ models → each_50_models
    for uid in selected_uids:
        cursor.execute("""
        INSERT INTO each_50_models 
        SELECT m.*, ? AS selected_tag 
        FROM models m 
        WHERE m.uid = ?
        """, (tag, uid))
        
        already_inserted.add(uid)
        total_inserted += 1
    
    print(f"{tag:15} → {len(selected_uids):2} model mới (tổng gốc: {len(candidate_uids)})")

# =========================================
# HOÀN TẤT
# =========================================
conn.commit()
conn.close()

print("\n" + "="*60)
print(f"HOÀN TẤT!")
print(f"Đã thêm {total_inserted} model duy nhất vào bảng 'each_50_models'")
print(f"Mỗi tag tối đa 50 model, không trùng lặp, giữ nguyên toàn bộ thông tin gốc.")
print(f"Bạn có thể dùng bảng này để train/validation furniture dataset")
print("="*60)