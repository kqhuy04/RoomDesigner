import chromadb


# 1. Kết nối vào Database đã tạo

DB_DIR = r"D:\Web\bed_chroma_db"

client = chromadb.PersistentClient(path=DB_DIR)

collection = client.get_collection(name="bed_collection")


def search_bed(query, n_results=3):

    print(f"\n🔍 Đang tìm: '{query}'...")
# Truy vấn ChromaDB
    results = collection.query(query_texts=[query],n_results=n_results)
# Hiển thị kết quả
    for i in range(n_results):
# Lấy thông tin

        meta = results['metadatas'][0][i]

        distance = results['distances'][0][i] # Càng thấp càng chính xác

        doc_id = results['ids'][0][i]


        print(f"\n--- Top {i+1} (Độ khớp: {distance:.4f}) ---")

        print(f"🛏️ Tên file: {doc_id}")

        print(f"🎨 Style: {meta['style']}")

        print(f"🪵 Material: {meta['material']}")

        print(f"📝 Mô tả: {meta['object']} - {meta['color_str']}")


# Chạy thử

if __name__ == "__main__":

    while True:

        q = input("\nNhập mô tả giường bạn muốn tìm (hoặc 'exit' để thoát): ")

        if q.lower() == 'exit': 
            break
        search_bed(q)