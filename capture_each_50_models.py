import objaverse
import os
import urllib.request
import time  # Để thêm delay tránh rate limit
from pathlib import Path

# Thư mục lưu ảnh preview
PREVIEW_DIR = "D:/Web/each_50_models"
os.makedirs(PREVIEW_DIR, exist_ok=True)

# Lấy lại danh sách UID (giống script cũ)
import sqlite3
DB_PATH = "database/db.db"
conn = sqlite3.connect(DB_PATH)
uids = [row[0] for row in conn.execute("SELECT uid FROM each_50_models").fetchall()]
conn.close()

print(f"Đang tải preview cho {len(uids)} model...")

# Thiết lập User-Agent để tránh bị block (giả như browser)
opener = urllib.request.build_opener()
opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')]
urllib.request.install_opener(opener)

# Lấy annotations (có thumbnails)
annotations = objaverse.load_annotations(uids=uids)  # Không cần download_processes vì chỉ load metadata

for uid in uids:
    anno = annotations[uid]
    # Sửa cấu trúc: thumbnails > images > [0] > url (chọn ảnh đầu tiên, hoặc index khác như 6 cho góc khác)
    # Có 12 ảnh/view, index 0 thường là góc front/default
    image_url = anno["thumbnails"]["images"][0]["url"]
    
    save_path = os.path.join(PREVIEW_DIR, f"{uid}.jpg")
    
    if not os.path.exists(save_path):
        try:
            urllib.request.urlretrieve(image_url, save_path)
            print(f"✓ {uid}.jpg")
            time.sleep(0.5)  # Delay 0.5 giây giữa các tải để tránh rate limit GitHub
        except Exception as e:
            print(f"✗ Lỗi tải {uid}: {e}")
    else:
        print(f"→ Đã có {uid}.jpg")

print("Hoàn thành! Ảnh preview nằm trong:", PREVIEW_DIR)