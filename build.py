import os
import json
import chromadb

# --- CẤU HÌNH ---
json_root_folder = r"D:\Web\json"
db_path = r"D:\Web\chroma_db"

def safe_metadata(value):
    """Chuyển đổi mọi giá trị thành string để tránh lỗi Metadata"""
    if isinstance(value, list):
        return ", ".join(map(str, value))
    elif value is None:
        return ""
    else:
        return str(value)

def build_database():
    print(f"Khởi động ChromaDB tại: {db_path}")
    client = chromadb.PersistentClient(path=db_path)

    if not os.path.exists(json_root_folder):
        print(f"Lỗi: Không tìm thấy thư mục {json_root_folder}")
        return

    folders = [f for f in os.listdir(json_root_folder) if os.path.isdir(os.path.join(json_root_folder, f))]

    for folder_name in folders:
        # Bây giờ folder_name đã là "television" (đủ dài), không cần if/else sửa tên nữa
        folder_path = os.path.join(json_root_folder, folder_name)
        
        try:
            collection = client.get_or_create_collection(name=folder_name)
            print(f"--- Đang xử lý Collection: {folder_name} ---")
        except Exception as e:
            print(f"[BỎ QUA] Không thể tạo collection '{folder_name}' (có thể tên không hợp lệ): {e}")
            continue

        json_files = [f for f in os.listdir(folder_path) if f.endswith(".json")]
        
        ids = []
        documents = []
        metadatas = []

        for json_file in json_files:
            file_path = os.path.join(folder_path, json_file)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                uid = os.path.splitext(json_file)[0]

                # Tạo nội dung tìm kiếm
                text_to_embed = (
                    f"{safe_metadata(data.get('description'))}. "
                    f"Style: {safe_metadata(data.get('style'))}. "
                    f"Material: {safe_metadata(data.get('material'))}. "
                    f"Color: {safe_metadata(data.get('color'))}. "
                    f"Room: {safe_metadata(data.get('appropriate_room'))}."
                )

                # Tạo Metadata hiển thị
                meta = {
                    "object": safe_metadata(data.get("object")),
                    "style": safe_metadata(data.get("style")),
                    "mood": safe_metadata(data.get("mood")),
                    "size_category": safe_metadata(data.get("size_category")),
                    "usage": safe_metadata(data.get("usage")),
                    "color": safe_metadata(data.get("color")),
                    "material": safe_metadata(data.get("material")),
                    "appropriate_room": safe_metadata(data.get("appropriate_room")),
                    "path": file_path
                }

                ids.append(uid)
                documents.append(text_to_embed)
                metadatas.append(meta)

            except Exception as e:
                print(f"[WARN] Lỗi đọc file {json_file}: {e}")

        if ids:
            try:
                collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
                print(f"-> Đã xử lý {len(ids)} items.")
            except Exception as e:
                print(f"[ERR] Lỗi lưu DB collection '{folder_name}': {e}")

    print("="*30)
    print("HOÀN TẤT XÂY DỰNG DATABASE!")

if __name__ == "__main__":
    build_database()