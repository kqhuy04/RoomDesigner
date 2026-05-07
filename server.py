import os
import re
import json
import math
import sqlite3
import bcrypt
import logging
from pathlib import Path
from typing import List, Optional, Dict

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

import chromadb
from pydantic import BaseModel, validator
from shapely.geometry import box
from shapely.affinity import rotate, translate

# --- IMPORT LANGCHAIN ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

# --- IMPORT MODULE ---
from graph_logic import ROOM_RULES_CONFIG, build_scene_graph, solve_optimal_subgraph

# =========================== CẤU HÌNH & KHỞI TẠO ===========================
load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

BASE_DIR = Path(__file__).resolve().parent
GLBS_ROOT = BASE_DIR / "each_50_models" / "glbs"
CHROMA_DB_PATH = str(BASE_DIR / "chroma_db")

db_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Khởi tạo mô hình qua LangChain
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", google_api_key=GEMINI_API_KEY, temperature=0.2)

HARDCODED_MODELS = {
    "window": "window.glb",
    "nightstand": "nightstand.glb",
    "door": "door.glb"
}

# =============================
# 🔹 PYDANTIC SCHEMAS
# =============================

class FurnitureItem(BaseModel):
    type: str
    uid: str
    position: List[float]  # [x, z, rot]
    size: List[float]      # [w, h, l]
    path: Optional[str] = ""

    @validator('size')
    def validate_dimensions(cls, v):
        if len(v) != 3 or any(dim <= 0 for dim in v): raise ValueError("Kích thước phải là số dương [w, h, l]")
        return v

    @validator('position')
    def normalize_rotation(cls, v):
        if len(v) != 3: raise ValueError("Vị trí phải là [x, z, rotation_radians]")
        v[2] = v[2] % (2 * math.pi)
        return v

# =============================
# 🔹 GEOMETRY ENGINE (VALIDATOR AGENT'S CORE)
# =============================

class GeometryEngine:
    def __init__(self, room_w: float, room_l: float):
        self.room_w = room_w
        self.room_l = room_l
        self.room_poly = box(0, 0, room_w, room_l).buffer(1e-6)
        self.placed_polys = []
        self.valid_items = []
        self.errors = []
        self.margin = 0.15 

    def get_rotated_bounds(self, w, l, rot):
        new_w = abs(w * math.cos(rot)) + abs(l * math.sin(rot))
        new_l = abs(w * math.sin(rot)) + abs(l * math.cos(rot))
        return new_w, new_l

    def build_polygon(self, item: FurnitureItem):
        x, z, rot = item.position
        w, _, l = item.size
        rect = box(-w/2, -l/2, w/2, l/2)
        return translate(rotate(rect, rot, use_radians=True), x, z)

    def clamp_strictly(self, item: FurnitureItem):
        w, _, l = item.size
        x, z, rot = item.position
        bw, bl = self.get_rotated_bounds(w, l, rot)
        
        # Sửa lỗi unpack, repack minh bạch để đảm bảo an toàn index
        x = max(bw/2, min(self.room_w - bw/2, x))
        z = max(bl/2, min(self.room_l - bl/2, z))
        item.position = [x, z, rot]

    def nudge_to_fit(self, item: FurnitureItem) -> bool:
        orig_pos = list(item.position)
        directions = [(0.1,0),(-0.1,0),(0,0.1),(0,-0.1),(0.1,0.1),(-0.1,0.1)]
        for dx, dz in directions:
            item.position[0] = orig_pos[0] + dx
            item.position[1] = orig_pos[1] + dz
            self.clamp_strictly(item)
            poly = self.build_polygon(item)
            if poly.within(self.room_poly) and all(poly.distance(p) >= self.margin for p in self.placed_polys):
                return True
        item.position = orig_pos
        return False

    def validate_and_add(self, item: FurnitureItem):
        self.clamp_strictly(item)
        poly = self.build_polygon(item)
        collision = any(poly.distance(p) < self.margin for p in self.placed_polys)
        
        if collision and self.nudge_to_fit(item):
            poly = self.build_polygon(item)
            collision = False

        if not poly.within(self.room_poly):
            self.errors.append(f"OUT_OF_BOUNDS: {item.uid}")
            return False
        if collision:
            self.errors.append(f"COLLISION: {item.uid}")
            return False

        self.placed_polys.append(poly)
        self.valid_items.append(item)
        return True

# =============================
# 🔹 HELPERS
# =============================

def safe_json_parse(text: str) -> Optional[Dict]:
    try: return json.loads(text)
    except:
        matches = re.findall(r'\{.*\}', text, re.DOTALL)
        if not matches: return None
        for match in sorted(matches, key=len, reverse=True):
            try:
                obj, _ = json.JSONDecoder().raw_decode(match)
                return obj
            except: continue
    return None

# =============================
# 🔹 ROUTES: TRANG CHỦ & AUTH
# =============================

@app.route('/')
def index(): return render_template('room_viewer.html')

@app.route('/login.html')
def login_page(): return render_template('login.html')

@app.route('/register.html')
def register_page(): return render_template('register.html')

@app.route('/test_load.html')
def test_load(): return render_template('test_load.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    if not data.get('username') or not data.get('password'): 
        return jsonify({"error": "Thiếu username/password"}), 400
    
    conn = sqlite3.connect('database/database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE username = ?", (data.get('username'),))
    result = cursor.fetchone()
    conn.close()
    
    # Sửa lỗi encode/decode của bcrypt với chuỗi từ DB
    if result and bcrypt.checkpw(data.get('password').encode('utf-8'), result[0].encode('utf-8')):
        return jsonify({"message": "Login successful"}), 200
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if not data.get('username') or not data.get('password'): 
        return jsonify({"error": "Thiếu username/password"}), 400
        
    # Sửa lỗi lưu kiểu byte array vào DB bằng cách giải mã utf-8
    password_hash = bcrypt.hashpw(data.get('password').encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    
    conn = sqlite3.connect('database/database.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (data.get('username'), password_hash))
        conn.commit()
        return jsonify({"message": "Register successful"}), 200
    except sqlite3.IntegrityError: 
        return jsonify({"error": "Username exists"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally: conn.close()

# =============================
# 🔹 ROUTES: TÌM KIẾM CHROMA DB (Logic chấm điểm nguyên bản)
# =============================

@app.route('/search', methods=['POST'])
def search_model():
    data = request.json
    query_object = data.get('q', '').strip().lower()
    item_data = data.get('item_data', {})

    if not query_object: return jsonify({"found": False, "error": "Thiếu tham số q"}), 400
    if query_object in HARDCODED_MODELS:
        return jsonify({"found": True, "uid": query_object, "path": HARDCODED_MODELS[query_object], "total_score": 999.0})

    collection_name = query_object if query_object != 'tv' else 'television'
    try:
        collection = db_client.get_collection(name=collection_name)
        total_items = collection.count()
        if total_items == 0: return jsonify({"found": False, "message": "Collection rỗng"})

        search_desc = item_data.get('description', f"A {collection_name}")
        results = collection.query(query_texts=[search_desc], n_results=total_items)

        best_model = None
        highest_score = -1.0

        for i in range(len(results['ids'][0])):
            metadata = results['metadatas'][0][i]
            semantic_score = 1.0 / (1.0 + results['distances'][0][i])
            metadata_score = 0.0
            
            input_colors = item_data.get('color', [])
            if isinstance(input_colors, str): input_colors = [c.strip() for c in input_colors.split(',')]
            target_colors = metadata.get('color', [])
            if isinstance(target_colors, str):
                try: target_colors = json.loads(target_colors.replace("'", '"'))
                except: target_colors = [target_colors]
            for c in input_colors:
                if any(c.lower() in str(tc).lower() for tc in target_colors): metadata_score += 1.0

            if str(item_data.get('style', '')).lower() == str(metadata.get('style', '')).lower(): metadata_score += 0.5

            input_rooms = item_data.get('appropriate_room', [])
            if isinstance(input_rooms, str): input_rooms = [r.strip() for r in input_rooms.split(',')]
            target_rooms = metadata.get('appropriate_room', [])
            if isinstance(target_rooms, str):
                try: target_rooms = json.loads(target_rooms.replace("'", '"'))
                except: target_rooms = [target_rooms]
            for r in input_rooms:
                if any(r.lower() in str(tr).lower() for tr in target_rooms): metadata_score += 0.3

            input_materials = item_data.get('material', [])
            if isinstance(input_materials, str): input_materials = [m.strip() for m in input_materials.split(',')]
            target_materials = metadata.get('material', [])
            if isinstance(target_materials, str):
                try: target_materials = json.loads(target_materials.replace("'", '"'))
                except: target_materials = [target_materials]
            for m in input_materials:
                if any(m.lower() in str(tm).lower() for tm in target_materials): metadata_score += 0.2

            if str(item_data.get('mood', '')).lower() == str(metadata.get('mood', '')).lower(): metadata_score += 0.2

            total_score = semantic_score + metadata_score
            if total_score > highest_score:
                highest_score = total_score
                best_model = {"uid": results['ids'][0][i], "path": f"{results['ids'][0][i]}.glb", "total_score": total_score, "meta": metadata}

        if best_model:
            full_path = GLBS_ROOT / best_model['path']
            if not full_path.exists(): return jsonify({"found": False, "error": "File GLB missing"}), 404
            return jsonify({"found": True, "uid": best_model['uid'], "path": best_model['path'], "total_score": round(best_model['total_score'], 4), "style_info": best_model['meta'].get('style', '')})
        return jsonify({"found": False, "message": "Không tìm thấy model phù hợp"})
    except Exception as e: return jsonify({"found": False, "error": str(e)}), 500

# =============================
# 🔹 ROUTES: LAYOUT ENGINE (MỚI - SỬ DỤNG LANGCHAIN MULTI-AGENT)
# =============================

@app.route('/generate_layout', methods=['POST'])
def generate_layout_api():
    data = request.json
    user_prompt = data.get('prompt', '')
    
    # Lấy thông số kích thước phòng từ client
    room_w = float(data.get('room_width', 5.0))
    room_l = float(data.get('room_length', 5.0))
    room_dim = {"width": room_w, "length": room_l}

    if not user_prompt: return jsonify({"error": "Prompt trống"}), 400

    try:
        # 1. AGENT PHÂN TÍCH (Space Analyst): Trích xuất ý định
        analyst_prompt = PromptTemplate.from_template(
            "Trích xuất room_type (living_room/bedroom) và style từ câu sau: {prompt}. Trả về dạng JSON chuẩn: {{\"room_type\": \"...\", \"style_phrase\": \"...\"}}"
        )
        analyst_chain = analyst_prompt | llm
        extract_raw = analyst_chain.invoke({"prompt": user_prompt}).content
        extract_data = safe_json_parse(extract_raw) or {"room_type": "living_room", "style_phrase": user_prompt}
        
        room_type = extract_data.get('room_type', 'living_room')
        style = extract_data.get('style_phrase', '')
        
        # 2. AGENT TRUY VẤN (Retriever): Lấy ứng viên từ Chroma
        categories = ROOM_RULES_CONFIG.get(room_type, {}).get("required", []) + ROOM_RULES_CONFIG.get(room_type, {}).get("optional", [])
        candidates = {}
        for cat in categories:
            try:
                col = db_client.get_collection(name=cat)
                res = col.query(query_texts=[style], n_results=10)
                if res['ids']:
                    candidates[cat] = [{"uid": res['ids'][0][i], "meta": res['metadatas'][0][i], "path": res['metadatas'][0][i].get('path', '')} for i in range(len(res['ids'][0]))]
            except Exception as e:
                logger.warning(f"ChromaDB Query Error on category {cat}: {e}")
        
        # Lọc đồ thị RAG bằng NetworkX (Có truyền kích thước phòng)
        G = build_scene_graph(candidates)
        final_items = solve_optimal_subgraph(G, room_type, room_dim)
        
        if not final_items: return jsonify({"error": "Không tìm thấy đồ vật phù hợp để xếp"}), 404
        
        required_uids = {it['uid'] for it in final_items}
        furn_str = "\n".join([f"- {it['category']} (UID: {it['uid']}): size(w={it.get('dimensions', {}).get('width', 1.0)}, h={it.get('dimensions', {}).get('height', 1.0)}, l={it.get('dimensions', {}).get('length', 1.0)})" for it in final_items])
        
        # 3. AGENT BỐ CỤC (Layout Optimizer) & KIỂM ĐỊNH (Validator Loop)
        feedback = ""

        layout_prompt = PromptTemplate.from_template(
            "Bạn là Chuyên gia thiết kế nội thất AI. Hãy xếp ĐẦY ĐỦ các món đồ sau vào phòng {room_w}x{room_l}m.\n"
            "Danh sách UIDs BẮT BUỘC (không được thiếu): {uids}\n"
            "Thông số đồ vật:\n{items}\n"
            "Phản hồi từ Validator (nếu có lỗi trước đó): {feedback}\n\n"
            "TRẢ VỀ DUY NHẤT ĐỊNH DẠNG JSON chứa danh sách 'furniture' với tọa độ 'position': [x, z, rotation_in_radians] và 'size': [w, h, l]. Không kèm text giải thích."
        )
        layout_chain = layout_prompt | llm

        # Vòng lặp tối ưu Agent (Tối đa 4 lần thử để tự sửa lỗi va chạm)
        for attempt in range(1, 5):
            layout_raw = layout_chain.invoke({
                "room_w": room_w, "room_l": room_l,
                "uids": list(required_uids),
                "items": furn_str, "feedback": feedback
            }).content
            
            layout_json = safe_json_parse(layout_raw)
            if not layout_json or 'furniture' not in layout_json: 
                feedback = f"Lỗi lần {attempt}: Trả về sai chuẩn JSON. Phải trả về JSON chứa mảng 'furniture'."
                continue

            try:
                engine = GeometryEngine(room_w, room_l)
                items_to_place = []
                for f in layout_json.get('furniture', []):
                    if f.get('uid') in required_uids:
                        size = f.get('size', [1,1,1])
                        if len(size) != 3: size = [1,1,1]
                        items_to_place.append(FurnitureItem(type=f.get('type', f.get('category', '')), uid=f.get('uid'), position=f.get('position', [0,0,0]), size=size))
                
                # Ưu tiên đặt đồ vật to trước
                items_to_place.sort(key=lambda x: x.size[0] * x.size[2], reverse=True)

                for it in items_to_place:
                    origin = next((o for o in final_items if o['uid'] == it.uid), None)
                    if origin: it.path = origin.get('meta', {}).get('path', f"{it.uid}.glb")
                    engine.validate_and_add(it)

                placed_uids = {it.uid for it in engine.valid_items}

                # Nếu đặt đủ đồ và không có lỗi -> Trả về Client luôn
                if placed_uids.issuperset(required_uids):
                    return jsonify({
                        "metadata": {"room_width": room_w, "room_length": room_l, "style": style},
                        "furniture": [it.dict() for it in engine.valid_items]
                    })
                
                # Nếu thiếu đồ hoặc bị đè lấn -> Phản hồi cho LLM Agent sửa lại
                missing = required_uids - placed_uids
                feedback = f"Lỗi lần {attempt}. Lỗi hình học: {engine.errors}. Các UIDs bị thiếu/lỗi: {list(missing)}. Hãy đổi tọa độ [x,z] của các đồ vật này đi chỗ khác."
            except Exception as e: 
                feedback = f"Lỗi hệ thống kiểm định: {e}"

        return jsonify({"error": "AI Agent không thể tìm được bố cục hợp lý sau các lần thử. Vui lòng thử lại."}), 500
    except Exception as e: return jsonify({"error": str(e)}), 500


# =============================
# 🔹 ROUTES: PHỤ TRỢ KHÁC
# =============================

@app.route('/models/<path:filename>')
def serve_model(filename):
    filename = secure_filename(filename)
    # Loại bỏ ổ đĩa cứng D:/, phục vụ trực tiếp qua folder GLBS_ROOT tương đối
    if (GLBS_ROOT / filename).exists(): return send_from_directory(GLBS_ROOT, filename)
    return jsonify({"error": "File not found"}), 404


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=8000)