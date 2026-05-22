-- 1. Bảng Users (Quản lý người dùng)
CREATE TABLE IF NOT EXISTS Users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,  -- ID tự tăng
    username TEXT NOT NULL UNIQUE,         -- Tên đăng nhập, không trùng lặp
    password_hash TEXT NOT NULL,           -- Mật khẩu đã mã hóa Bcrypt
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP -- Thời điểm tạo
);

-- 2. Bảng Models (Dữ liệu từ Sketchfab Crawler)
CREATE TABLE IF NOT EXISTS Models (
    uid TEXT PRIMARY KEY,                  -- Khóa chính: ID từ Sketchfab (VD: aaf4093e...)
    name TEXT,                             -- Tên hiển thị
    description TEXT,                      -- Mô tả (hỗ trợ Markdown)
    file_path TEXT,                        -- Đường dẫn file .glb trên ổ cứng
    thumbnail_url TEXT,                    -- Link ảnh đại diện
    viewer_url TEXT,                       -- Link gốc Sketchfab
    face_count INTEGER,                    -- Số lượng mặt đa giác
    vertex_count INTEGER,                  -- Số lượng đỉnh
    tags TEXT,                             -- Lưu mảng JSON (VD: ["stair", "hemlock"])
    categories TEXT,                       -- Danh mục phân loại
    license TEXT,                          -- Thông tin bản quyền
    is_downloadable INTEGER DEFAULT 0,     -- 1: Có, 0: Không
    created_db_at DATETIME DEFAULT CURRENT_TIMESTAMP -- Thời điểm crawler lưu vào DB
);