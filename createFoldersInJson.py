import os

# 1. ĐƯỜNG DẪN THƯ MỤC GỐC
base_dir = r"D:\Web\json"

# 2. DANH SÁCH TAG (TÊN CÁC FOLDER CẦN TẠO)
furniture_tags = [
    "chair", "sofa", "bench", "stool",
    "table", "desk",
    "cabinet", "shelf", "rack", "wardrobe", "chest",
    "bed",
    "lamp", "light",
    "rug",
    "partition",
    "stair",
    "tv",
    "mirror",
    "curtain",
    "plant"
]

def create_folders():
    # Kiểm tra xem folder gốc D:\Web\json có tồn tại chưa, chưa thì tạo
    if not os.path.exists(base_dir):
        try:
            os.makedirs(base_dir)
            print(f"Đã tạo thư mục gốc: {base_dir}")
        except OSError as e:
            print(f"Lỗi: Không thể tạo thư mục gốc {base_dir}. Kiểm tra quyền truy cập. Chi tiết: {e}")
            return

    print(f"--- Bắt đầu tạo folder trong {base_dir} ---")

    count = 0
    for tag in furniture_tags:
        # Tạo đường dẫn đầy đủ: D:\Web\json\chair, v.v.
        folder_path = os.path.join(base_dir, tag)
        
        try:
            # exist_ok=True nghĩa là nếu folder đã có rồi thì không báo lỗi, cứ bỏ qua
            os.makedirs(folder_path, exist_ok=True)
            print(f"[OK] Folder: {tag}")
            count += 1
        except OSError as e:
            print(f"[LỖI] Không thể tạo folder {tag}: {e}")

    print("-" * 30)
    print(f"Hoàn tất! Đã xử lý {count} thư mục.")

if __name__ == "__main__":
    create_folders()