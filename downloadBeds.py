import sqlite3
import objaverse
import os

DB_PATH = "database/db.db"
DOWNLOAD_DIR = "D:/Web/bed_models"  # Thư mục tải trên ổ D, thay đổi nếu cần

# Thiết lập thư mục tải tùy chỉnh (phải làm ở module level để áp dụng cho tất cả processes)
objaverse._VERSIONED_PATH = DOWNLOAD_DIR

# Tạo thư mục nếu chưa tồn tại (có thể để ở đây, exist_ok=True nên an toàn)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

if __name__ == '__main__':
    # Kết nối database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Lấy danh sách UID trong models_bed
    cursor.execute("SELECT uid FROM models_bed")
    uids = [row[0] for row in cursor.fetchall()]
    conn.close()

    print("Tổng số model cần tải:", len(uids))

    # In ra _VERSIONED_PATH để debug (xác nhận path đã set đúng)
    print(f"Đường dẫn tải: {objaverse._VERSIONED_PATH}")

    # Tải toàn bộ model với tải song song
    paths = objaverse.load_objects(
        uids=uids,
        download_processes=8  # Thay đổi số này tùy máy
    )

    # In ra kết quả
    for uid, path in paths.items():
        print(f"{uid} -> {path}")

    print("Hoàn thành tải model!")