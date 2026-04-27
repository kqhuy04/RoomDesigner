import sqlite3
import bcrypt
import json

def init_db():
    conn = sqlite3.connect('database/db.db')
    cursor = conn.cursor()
    
    # Bảng users cho authentication
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY NOT NULL UNIQUE,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Bảng models - lưu TẤT CẢ thông tin
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS models (
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
            
            created_db_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Tạo indexes để search nhanh
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_name ON models(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_views ON models(view_count)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_models_tags ON models(tags)")
    
    # Thêm admin user
    hash_password = bcrypt.hashpw("password123".encode('utf-8'), bcrypt.gensalt())
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                      ("admin", hash_password))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    
    conn.close()
    print("Database initialized successfully!")

if __name__ == "__main__":
    init_db()