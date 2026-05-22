import os
import json
import shutil

# ĐƯỜNG DẪN GỐC
base_dir = r"D:\Web\json"

def fix_tv_data():
    old_folder = os.path.join(base_dir, "tv")
    new_folder = os.path.join(base_dir, "television")

    # 1. Đổi tên Folder: tv -> television
    if os.path.exists(old_folder):
        if not os.path.exists(new_folder):
            try:
                os.rename(old_folder, new_folder)
                print(f"[OK] Đã đổi tên folder: 'tv' -> 'television'")
            except OSError as e:
                print(f"[LỖI] Không thể đổi tên folder: {e}")
                return
        else:
            print(f"[INFO] Folder 'television' đã tồn tại. Sẽ gộp nội dung từ 'tv' sang.")
            # Nếu cả 2 cùng tồn tại thì move file từ tv sang television rồi xóa tv
            for f in os.listdir(old_folder):
                shutil.move(os.path.join(old_folder, f), os.path.join(new_folder, f))
            os.rmdir(old_folder)
    
    # Kiểm tra lại folder mới
    if not os.path.exists(new_folder):
        print("Không tìm thấy folder 'television' (và cũng không có 'tv'). Kết thúc.")
        return

    # 2. Sửa nội dung JSON bên trong folder television
    files = [f for f in os.listdir(new_folder) if f.endswith(".json")]
    print(f"Đang cập nhật nội dung {len(files)} file trong 'television'...")

    count = 0
    for file_name in files:
        file_path = os.path.join(new_folder, file_name)
        
        try:
            # Đọc
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Sửa
            if data.get("object") == "tv":
                data["object"] = "television"
                
                # Ghi đè lại
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)
                count += 1
        except Exception as e:
            print(f"Lỗi file {file_name}: {e}")

    print(f"[HOÀN TẤT] Đã sửa nội dung 'object' cho {count} file.")

if __name__ == "__main__":
    fix_tv_data()