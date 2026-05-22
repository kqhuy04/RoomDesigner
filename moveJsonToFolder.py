import os
import json
import shutil
import glob

# 1. CẤU HÌNH ĐƯỜNG DẪN
source_folder = r"D:\Web\each_50_models_output"  # Thư mục chứa 2000 file json ban đầu
destination_root = r"D:\Web\json"                # Thư mục chứa các folder phân loại (chair, table...)

def organize_files():
    # Lấy danh sách tất cả file .json còn lại trong thư mục nguồn
    files = glob.glob(os.path.join(source_folder, "*.json"))
    
    if not files:
        print("Không tìm thấy file JSON nào trong thư mục nguồn để di chuyển.")
        return

    print(f"Đang xử lý {len(files)} file...")
    
    moved_count = 0
    error_count = 0

    for file_path in files:
        try:
            # Bước 1: Đọc file để lấy giá trị "object"
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                object_type = data.get("object") # Ví dụ: "chair"

            if object_type:
                # Bước 2: Xác định đường dẫn folder đích
                # Ví dụ: D:\Web\json\chair
                target_folder = os.path.join(destination_root, object_type)

                # (Tuỳ chọn) Tự tạo folder nếu chưa có (để tránh lỗi nếu bước trước tạo thiếu)
                os.makedirs(target_folder, exist_ok=True)

                # Bước 3: Di chuyển file
                file_name = os.path.basename(file_path)
                destination_path = os.path.join(target_folder, file_name)

                # Kiểm tra nếu file trùng tên ở đích đã tồn tại
                if os.path.exists(destination_path):
                    print(f"[WARN] File {file_name} đã tồn tại trong {object_type}. Đang ghi đè...")
                    os.remove(destination_path) # Xóa file cũ ở đích đi để move file mới vào

                # Thực hiện lệnh Move (Cut -> Paste)
                shutil.move(file_path, destination_path)
                
                # In ra log (bỏ comment dòng dưới nếu muốn xem chi tiết từng file)
                # print(f"[OK] {file_name} -> folder: {object_type}")
                moved_count += 1
            else:
                print(f"[SKIP] File {os.path.basename(file_path)} không có key 'object'.")

        except Exception as e:
            print(f"[ERROR] Không thể di chuyển file {file_path}: {e}")
            error_count += 1

    print("-" * 30)
    print(f"HOÀN TẤT!")
    print(f"Đã di chuyển thành công: {moved_count} files")
    print(f"Số file còn lại/lỗi: {error_count}")

if __name__ == "__main__":
    organize_files()