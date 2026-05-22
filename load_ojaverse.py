import sqlite3
import objaverse
import json
from tqdm import tqdm

def migrate_objaverse_to_sqlite(furniture_tags, limit=None):
    conn = sqlite3.connect('database/db.db')
    cursor = conn.cursor()
    
    print("Loading UIDs...")
    uids = objaverse.load_uids()
    if limit:
        uids = uids[:limit]
    
    print(f"Loading annotations for {len(uids)} models...")
    annotations = objaverse.load_annotations(uids)
    
    total_models = 0
    furniture_models = 0
    
    print("Inserting data into database...")
    for uid in tqdm(uids):
        info = annotations.get(uid)
        if not info:
            continue
            
        total_models += 1
        
        # Check furniture tags
        # Check furniture tags
        tags = info.get('tags', [])
        tag_names = [tag.get('name', '').lower() for tag in tags]

        # Loại bỏ models có "room" trong tên
        model_name = info.get('name', '').lower()
        if 'room' in model_name:
            continue

        # Check nếu BẤT KÌ furniture_tag nào là substring của BẤT KÌ tag nào
        has_furniture_tag = any(
            any(furniture_tag in tag_name for furniture_tag in furniture_tags)
            for tag_name in tag_names
        )

        if not has_furniture_tag:
            continue
            
        furniture_models += 1
        
        try:
            # Convert complex data to JSON strings
            tags_json = json.dumps(tags)
            thumbnails_json = json.dumps(info.get('thumbnails', {}))
            archives_json = json.dumps(info.get('archives', {}))
            categories_json = json.dumps(info.get('categories', []))
            user_json = json.dumps(info.get('user', {}))
            
            # Insert tất cả vào 1 bảng
            cursor.execute("""
                INSERT OR REPLACE INTO models 
                (uid, name, description, uri, viewer_url, embed_url,
                 view_count, like_count, comment_count, animation_count,
                 is_downloadable, is_age_restricted, staff_picked_at, published_at, created_at,
                 face_count, vertex_count, license,
                 tags, thumbnails, archives, categories, user_info)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uid,
                info.get('name'),
                info.get('description'),
                info.get('uri'),
                info.get('viewerUrl'),
                info.get('embedUrl'),
                info.get('viewCount', 0),
                info.get('likeCount', 0),
                info.get('commentCount', 0),
                info.get('animationCount', 0),
                info.get('isDownloadable', False),
                info.get('isAgeRestricted', False),
                info.get('staffpickedAt'),
                info.get('publishedAt'),
                info.get('createdAt'),
                info.get('faceCount'),
                info.get('vertexCount'),
                info.get('license'),
                tags_json,
                thumbnails_json,
                archives_json,
                categories_json,
                user_json
            ))
            
            if total_models % 100 == 0:
                conn.commit()
                
        except Exception as e:
            print(f"\nError processing {uid}: {e}")
            continue
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Migration complete!")
    print(f"Total models processed: {total_models}")
    print(f"Furniture models saved: {furniture_models}")

# Furniture tags
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

# Run migration
migrate_objaverse_to_sqlite(furniture_tags)