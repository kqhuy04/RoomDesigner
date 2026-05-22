import json
import os
import glob

# ĐƯỜNG DẪN THƯ MỤC CHỨA JSON
# Lưu ý: Nhớ đổi lại đường dẫn nếu cần thiết, dùng r"" để tránh lỗi ký tự đặc biệt
folder_path = r"D:\Web\each_50_models_output"

# 1. DANH SÁCH CÁC TAG GỐC (FURNITURE TAGS) - Dùng để check substring
# Những từ này sẽ được giữ lại làm chuẩn.
furniture_tags = [
    "chair", "sofa", "bench", "stool",
    "table", "desk",
    "cabinet", "shelf", "rack", "wardrobe", "chest",
    "bed",         # Thêm bed vì là đồ nội thất cơ bản
    "lamp", "light",
    "rug",
    "partition",   # Dùng cho vách ngăn
    "stair",       # Dùng thay cho staircase
    "tv",
    "mirror",      # Thường dùng
    "curtain",     # Thường dùng
    "plant"        # Cây trang trí
]

# 2. TỪ ĐIỂN ÁNH XẠ (MAPPING) - Dùng cho các trường hợp không chứa substring
# Cấu trúc: "từ_hiện_tại": "từ_mới_muốn_sửa"
special_mappings = {
    # Biến thể ghế (không chứa chữ chair/stool...)
    "ottoman": "stool",
    "bean_bag": "chair",
    "recliner": "chair",
    "swing": "chair",
    "hammock": "chair",
    
    # Biến thể bàn (không chứa chữ table/desk)
    "nightstand": "table",
    "vanity": "table",
    "kitchen_island": "table",
    "plant_stand": "table",
    "tv_stand": "cabinet",  # Hoặc table tùy bạn, ở đây map về cabinet theo logic tủ kệ
    
    # Biến thể tủ/kệ (không chứa cabinet/shelf/rack)
    "chest_of_drawers": "cabinet",
    "dresser": "cabinet",
    "closet": "wardrobe",
    "pantry": "cabinet",
    "toy_chest": "cabinet",
    "shower_caddy": "rack",
    
    # Đồ trang trí / Khác
    "chandelier": "lamp",
    "bath_mat": "rug",
    "television": "tv",
    "staircase": "stair",   # Vì 'stair' nằm trong 'staircase' nên logic 1 sẽ bắt được, nhưng để đây cho chắc
    "room_divider": "partition"
}

def process_json_files():
    # Lấy tất cả file .json trong thư mục
    files = glob.glob(os.path.join(folder_path, "*.json"))
    
    processed_count = 0
    deleted_count = 0
    
    print(f"Bắt đầu xử lý {len(files)} files...")

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            original_object = data.get("object", "").lower().strip()
            new_object = None
            
            # --- LOGIC 1: KIỂM TRA SUBSTRING ---
            # Ví dụ: "armchair" chứa "chair" -> new_object = "chair"
            for tag in furniture_tags:
                if tag in original_object:
                    new_object = tag
                    break # Ưu tiên tìm thấy cái nào trước thì lấy (nên sắp xếp list tag từ quan trọng nếu cần)
            
            # --- LOGIC 2: KIỂM TRA MAPPING (Nếu Logic 1 thất bại) ---
            if not new_object:
                if original_object in special_mappings:
                    new_object = special_mappings[original_object]

            # --- KẾT QUẢ ---
            if new_object:
                # Nếu object thay đổi hoặc giữ nguyên nhưng hợp lệ, ghi đè file
                if new_object != data["object"]:
                    data["object"] = new_object
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=4, ensure_ascii=False)
                    print(f"[UPDATED] {original_object} -> {new_object} | File: {os.path.basename(file_path)}")
                else:
                    # Object đã chuẩn, không cần ghi đè nhưng file an toàn
                    pass
                processed_count += 1
                
            else:
                # --- LOGIC 3: KHÔNG THUỘC LOẠI NÀO -> XÓA FILE ---
                # Ví dụ: picture_frame (quá chi tiết), garbage data...
                f.close() # Đóng file trước khi xóa
                os.remove(file_path)
                deleted_count += 1
                print(f"[DELETED] Object '{original_object}' không hợp lệ. Đã xóa file: {os.path.basename(file_path)}")

        except Exception as e:
            print(f"Lỗi khi xử lý file {file_path}: {e}")

    print("-" * 30)
    print(f"HOÀN TẤT!")
    print(f"Số file giữ lại/cập nhật: {processed_count}")
    print(f"Số file bị xóa: {deleted_count}")

if __name__ == "__main__":
    process_json_files()