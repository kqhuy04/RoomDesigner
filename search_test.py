import chromadb
import os

# --- CẤU HÌNH ---
db_path = r"D:\Web\chroma_db"  # Đường dẫn đến DB bạn đã build

def search_bed_demo():
    # 1. Kết nối DB
    if not os.path.exists(db_path):
        print(f"Lỗi: Không tìm thấy thư mục DB tại {db_path}")
        return

    client = chromadb.PersistentClient(path=db_path)

    # 2. Lấy Collection 'bed'
    try:
        collection = client.get_collection(name="bed")
    except Exception as e:
        print(f"Lỗi: Không tìm thấy collection 'bed'. Bạn đã chạy build chưa? ({e})")
        return

    # 3. NHẬP MÔ TẢ BẠN MUỐN TÌM Ở ĐÂY
    # Ví dụ: Tìm giường ngủ hiện đại, màu xám, đầu giường bọc vải
    query_text = "A modern double bed with grey fabric headboard, wooden legs, minimalist style, comfortable and clean look."
    
    print(f"--- Đang tìm kiếm: '{query_text}' ---\n")

    # 4. Thực hiện truy vấn
    results = collection.query(
        query_texts=[query_text],
        n_results=3  # Top 3
    )

    # 5. Hiển thị kết quả
    ids = results['ids'][0]
    metadatas = results['metadatas'][0]
    distances = results['distances'][0] # Khoảng cách càng nhỏ = càng giống

    if not ids:
        print("Không tìm thấy kết quả nào.")
        return

    for i in range(len(ids)):
        print(f"#{i+1} [Độ sai lệch: {distances[i]:.4f}]")
        print(f"   ID (UID): {ids[i]}")
        print(f"   Object:   {metadatas[i]['object']}")
        print(f"   Style:    {metadatas[i]['style']}")
        print(f"   Material: {metadatas[i]['material']}")
        print(f"   Color:    {metadatas[i]['color']}")
        print(f"   File:     {metadatas[i]['path']}")
        print("-" * 50)

if __name__ == "__main__":
    search_bed_demo()