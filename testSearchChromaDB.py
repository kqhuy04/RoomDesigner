import chromadb
import os
import matplotlib.pyplot as plt
import matplotlib.image as mpimg
from PIL import Image

# 1. Kết nối vào Database
DB_DIR = r"D:\Web\bed_chroma_db"
IMG_DIR = r"D:\Web\bed_previews"  # Folder chứa ảnh

client = chromadb.PersistentClient(path=DB_DIR)
collection = client.get_collection(name="bed_collection")

def search_bed(query, n_results=3):
    print(f"\n🔍 Đang tìm: '{query}'...")
    
    # Truy vấn ChromaDB
    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )
    
    # Chuẩn bị list để vẽ ảnh
    found_images = []
    captions = []

    # Hiển thị thông tin text
    for i in range(n_results):
        if not results['ids'][0]: continue # Phòng trường hợp không có kết quả

        meta = results['metadatas'][0][i]
        distance = results['distances'][0][i]
        doc_id = results['ids'][0][i]
        
        print(f"\n--- Top {i+1} (Độ khớp: {distance:.4f}) ---")
        print(f"🛏️ Tên file: {doc_id}")
        print(f"📝 Mô tả: {meta.get('object', '')} - {meta.get('style', '')}")
        
        # Xử lý đường dẫn ảnh
        # Tên file ảnh = tên file (doc_id) + .jpg
        img_filename = f"{doc_id}.jpg"
        img_path = os.path.join(IMG_DIR, img_filename)
        
        if os.path.exists(img_path):
            found_images.append(img_path)
            captions.append(f"Top {i+1}\n{doc_id}")
        else:
            print(f"⚠️ Cảnh báo: Không tìm thấy ảnh tại {img_path}")

    # Hiển thị ảnh bằng Matplotlib (Nếu tìm thấy ảnh)
    if found_images:
        show_images(found_images, captions)
    else:
        print("❌ Không tìm thấy file ảnh nào để hiển thị.")

def show_images(image_paths, titles):
    """Hàm vẽ nhiều ảnh trên cùng một hàng"""
    n = len(image_paths)
    if n == 0: return

    # Tạo khung hình (Figure)
    fig, axes = plt.subplots(1, n, figsize=(15, 5)) # 1 hàng, n cột
    
    # Nếu chỉ có 1 ảnh, axes không phải là list, cần chuyển thành list để loop
    if n == 1:
        axes = [axes]

    for ax, img_path, title in zip(axes, image_paths, titles):
        try:
            # Đọc và hiển thị ảnh
            img = mpimg.imread(img_path)
            ax.imshow(img)
            ax.set_title(title, fontsize=10, color='blue')
            ax.axis('off') # Tắt trục tọa độ cho đẹp
        except Exception as e:
            print(f"Lỗi đọc ảnh {img_path}: {e}")

    plt.tight_layout()
    plt.show()

# Chạy thử
if __name__ == "__main__":
    while True:
        q = input("\nNhập mô tả giường bạn muốn tìm (hoặc 'exit' để thoát): ")
        if q.lower() == 'exit': break
        search_bed(q)