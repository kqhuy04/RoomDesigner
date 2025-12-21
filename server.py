from flask import Flask, request, jsonify, render_template, send_from_directory
import sqlite3
import bcrypt
import requests
import re
import random
import os
import zipfile
import json
from pathlib import Path
from google import genai
from dotenv import load_dotenv
from flask_cors import CORS
# --- THÊM THƯ VIỆN CHROMA ---
import chromadb 

# =========================== CẤU HÌNH ===========================
# Đường dẫn thư mục chứa file .GLB (để server trả file về cho web)
GLBS_ROOT = Path(r"D:/Web/each_50_models/glbs")

# Đường dẫn Database Chroma (đã tạo ở bước trước)
CHROMA_DB_PATH = r"D:\Web\chroma_db"

# Database User cũ (giữ nguyên cho Login/Register)
DB_PATH = Path("database/db.db") 

load_dotenv()
app = Flask(__name__)
CORS(app)

SKETCHFAB_API_KEY = os.getenv("SKETCH_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# ==================================================================================
# =============================
# 🔹 Trang người dùng
# =============================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login.html')
def login_page():
    return render_template('login.html')

@app.route('/register.html')
def register_page():
    return render_template('register.html')

@app.route('/test_load.html')
def test_load():
    return render_template('test_load.html')

# =============================
# 🔹 Đăng ký / đăng nhập (GIỮ NGUYÊN)
# =============================
@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password') 
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400    

    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = ?", (username,))
    result = cursor.fetchone()
    conn.close()

    if result and bcrypt.checkpw(password.encode('utf-8'), result[0]): 
        return jsonify({"message": "Login successful"}), 200
    else:
        return jsonify({"error": "Invalid credentials"}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username')
    password = data.get('password') 
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400    

    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT username FROM users WHERE username = ?", (username,))    
        result = cursor.fetchone()
        if result:
            return jsonify({"error": "Username already exists"}), 409
        else:
            cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", 
                        (username, password_hash))
            conn.commit()
            conn.close()
            return jsonify({"message": "Register successful"}), 200
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 409

# =============================
# 🔹 API MỚI: TÌM KIẾM BẰNG CHROMADB
# =============================
@app.route('/search')
def search_model():
    # 1. Lấy tham số từ Frontend
    # q = tên folder (collection), ví dụ: "bed", "chair"
    # description = mô tả phong cách, ví dụ: "Modern wooden bed..."
    query_object = request.args.get('q', '').strip().lower()
    description = request.args.get('description', '').strip()

    if not query_object:
        return jsonify({"found": False, "error": "Thiếu tham số q="}), 400

    # 2. Xử lý mapping tên đặc biệt
    collection_name = query_object
    if collection_name == 'tv': 
        collection_name = 'television'
    
    # Nếu description rỗng, dùng chính tên object để tìm
    search_text = description if description else f"A {collection_name}"

    print(f"🔎 Đang tìm trong Collection: '{collection_name}' | Query: '{search_text[:50]}...'")

    try:
        # 3. Kết nối ChromaDB
        client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        
        # Kiểm tra collection có tồn tại không
        try:
            collection = client.get_collection(name=collection_name)
        except Exception:
            print(f"⚠️ Collection '{collection_name}' không tồn tại trong DB.")
            return jsonify({"found": False, "error": f"Category '{collection_name}' not found in DB"})

        # 4. Query tìm kiếm Top 1 (n_results=1)
        results = collection.query(
            query_texts=[search_text],
            n_results=1
        )

        # 5. Xử lý kết quả
        if not results['ids'] or not results['ids'][0]:
            return jsonify({"found": False, "message": "Không tìm thấy model phù hợp"})

        # Lấy thông tin model tốt nhất
        best_uid = results['ids'][0][0]
        best_distance = results['distances'][0][0]
        metadata = results['metadatas'][0][0]

        # Đường dẫn file GLB: Front-end sẽ gọi /models/{uid}.glb
        glb_filename = f"{best_uid}.glb"
        
        # Kiểm tra xem file vật lý có tồn tại không
        full_physical_path = GLBS_ROOT / glb_filename
        if not full_physical_path.exists():
            print(f"❌ DB có UID {best_uid} nhưng không thấy file GLB tại {full_physical_path}")
            # Có thể trả về false hoặc thử tìm model thứ 2 (tạm thời trả false)
            return jsonify({"found": False, "error": "File GLB bị thiếu trên server"})

        print(f"✅ Đã tìm thấy: {best_uid} (Distance: {best_distance:.4f})")

        return jsonify({
            "found": True,
            "uid": best_uid,
            "path": glb_filename,     # Frontend sẽ ghép thành: SERVER_URL + "/models/" + path
            "score": float(best_distance),
            "style_info": metadata.get('style', '')
        })

    except Exception as e:
        print(f"🔥 Lỗi Server Search: {e}")
        return jsonify({"found": False, "error": str(e)}), 500

# =============================
# API: Serve file .glb (GIỮ NGUYÊN)
# =============================
@app.route('/models/<path:filename>')
def serve_objaverse_model(filename):
    file_path = (GLBS_ROOT / filename).resolve()
    
    # Bảo mật: chỉ cho phép truy cập trong GLBS_ROOT
    try:
        # Kiểm tra xem file có nằm trong thư mục cho phép không
        if GLBS_ROOT.resolve() not in file_path.parents and GLBS_ROOT.resolve() != file_path.parent:
             return "Forbidden", 403
        
        if not file_path.exists():
            return "File not found", 404

        return send_from_directory(file_path.parent, file_path.name)
    except Exception as e:
        return jsonify({"error": str(e)}), 404

# =============================
# 🔹 API: Lấy model từ Sketchfab (GIỮ NGUYÊN)
# =============================
@app.route('/sketchfab', methods=['POST'])
def get_model():
    data = request.json
    QUERY = data.get('query', '').strip().lower()
    if not QUERY:
        return jsonify({"error": "Thiếu từ khóa tìm kiếm (query)."}), 400

    # ... (Giữ nguyên logic Sketchfab cũ của bạn ở đây) ...
    # Để code gọn, tôi không paste lại toàn bộ phần Sketchfab dài
    # Bạn hãy giữ nguyên phần code Sketchfab cũ nhé.
    return jsonify({"error": "Sketchfab logic placeholder"}) 


# =============================
# 🔹 Function Helper
# =============================
def call_llm(prompt):
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        result = client.models.generate_content(
            model="gemini-2.5-pro",
            contents=prompt,
        )
        text = result.text if hasattr(result, "text") else str(result)
        return text
    except Exception as e:
        return "error: " + str(e)
    
def download_and_extract_model(uid, model_name):
    """
    Tải model từ Sketchfab bằng UID và giải nén ra thư mục cùng tên với model_name.
    Trả về đường dẫn thư mục giải nén.
    """
    headers = {"Authorization": f"Token {SKETCHFAB_API_KEY}"}
    download_url = f"https://api.sketchfab.com/v3/models/{uid}/download"

    dl_resp = requests.get(download_url, headers=headers)
    if dl_resp.status_code != 200:
        raise Exception(f"Không thể lấy link download (HTTP {dl_resp.status_code})")

    dl_data = dl_resp.json()
    model_link = dl_data.get("gltf", {}).get("url") or dl_data.get("source", {}).get("url")
    if not model_link:
        raise Exception("Không có link tải model")

    # ---- Chuẩn bị đường dẫn ----
    base_dir = os.path.join(os.getcwd(), "models_downloaded")
    os.makedirs(base_dir, exist_ok=True)

    # Làm sạch tên model (loại ký tự đặc biệt)
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', model_name.strip().lower())
    zip_path = os.path.join(base_dir, f"{safe_name}.zip")
    extract_folder = os.path.join(base_dir, safe_name)

    # Xóa nếu tồn tại
    if os.path.exists(zip_path):
        os.remove(zip_path)
    if os.path.exists(extract_folder):
        import shutil
        shutil.rmtree(extract_folder)

    # ---- Tải file zip ----
    print(f"⬇️ Đang tải model '{model_name}'...")
    model_zip = requests.get(model_link, stream=True)
    with open(zip_path, "wb") as f:
        for chunk in model_zip.iter_content(chunk_size=8192):
            f.write(chunk)

    # ---- Giải nén ----
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_folder)
    os.remove(zip_path)

    print(f"📂 Model '{model_name}' đã được tải và giải nén tại: {extract_folder}")
    return extract_folder
   

# =============================
# 🔹 Run Flask
# =============================
if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=8000)