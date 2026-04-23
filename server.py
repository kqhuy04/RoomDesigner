import os
import re
import json
import math
import sqlite3
import bcrypt
import requests
import zipfile
import logging
from pathlib import Path
from typing import List, Optional, Dict, Set, Any

from flask import Flask, request, jsonify, render_template, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

import chromadb
from google import genai
from pydantic import BaseModel, Field, validator
from shapely.geometry import box
from shapely.affinity import rotate, translate

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
genai_client = genai.Client(api_key=GEMINI_API_KEY)
SKETCHFAB_API_KEY = os.getenv("SKETCH_API_KEY")

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
        if len(v) != 3 or any(dim <= 0 for dim in v):
            raise ValueError("Kích thước phải là số dương [w, h, l]")
        return v

    @validator('position')
    def normalize_rotation(cls, v):
        if len(v) != 3:
            raise ValueError("Vị trí phải là [x, z, rotation_radians]")
        v[2] = v[2] % (2 * math.pi)
        return v

class LayoutSchema(BaseModel):
    room_width: float = Field(..., gt=0)
    room_length: float = Field(..., gt=0)
    furniture: List[FurnitureItem]

# =============================
# 🔹 GEOMETRY ENGINE
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
        rot = item.position[2]
        bw, bl = self.get_rotated_bounds(w, l, rot)
        item.position[0] = max(bw/2, min(self.room_w - bw/2, item.position[0]))
        item.position[1] = max(bl/2, min(self.room_l - bl/2, item.position[1]))

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

def call_llm(prompt, system_instr=""):
    try:
        result = genai_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config={'system_instruction': system_instr} if system_instr else None
        )
        return result.text
    except Exception as e:
        logger.error(f"LLM Error: {e}")
        return ""

def safe_json_parse(text: str) -> Optional[Dict]:
    try:
        return json.loads(text)
    except:
        matches = re.findall(r'\{.*\}', text, re.DOTALL)
        if not matches: return None
        for match in sorted(matches, key=len, reverse=True):
            try:
                decoder = json.JSONDecoder()
                obj, _ = decoder.raw_decode(match)
                return obj
            except: continue
    return None

def download_and_extract_model(uid, model_name):
    headers = {"Authorization": f"Token {SKETCHFAB_API_KEY}"}
    download_url = f"https://api.sketchfab.com/v3/models/{uid}/download"
    dl_resp = requests.get(download_url, headers=headers)
    if dl_resp.status_code != 200: raise Exception(f"Lỗi lấy link (HTTP {dl_resp.status_code})")

    dl_data = dl_resp.json()
    model_link = dl_data.get("gltf", {}).get("url") or dl_data.get("source", {}).get("url")
    if not model_link: raise Exception("Không có link tải model")

    base_dir = os.path.join(os.getcwd(), "models_downloaded")
    os.makedirs(base_dir, exist_ok=True)
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', model_name.strip().lower())
    zip_path = os.path.join(base_dir, f"{safe_name}.zip")
    extract_folder = os.path.join(base_dir, safe_name)

    if os.path.exists(zip_path): os.remove(zip_path)
    if os.path.exists(extract_folder):
        import shutil
        shutil.rmtree(extract_folder)

    model_zip = requests.get(model_link, stream=True)
    with open(zip_path, "wb") as f:
        for chunk in model_zip.iter_content(chunk_size=8192): f.write(chunk)

    with zipfile.ZipFile(zip_path, "r") as zip_ref: zip_ref.extractall(extract_folder)
    os.remove(zip_path)
    return extract_folder

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
    
    if result and bcrypt.checkpw(data.get('password').encode('utf-8'), result[0]):
        return jsonify({"message": "Login successful"}), 200
    return jsonify({"error": "Invalid credentials"}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    if not data.get('username') or not data.get('password'):
        return jsonify({"error": "Thiếu username/password"}), 400
        
    password_hash = bcrypt.hashpw(data.get('password').encode('utf-8'), bcrypt.gensalt())
    conn = sqlite3.connect('database/database.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (data.get('username'), password_hash))
        conn.commit()
        return jsonify({"message": "Register successful"}), 200
    except sqlite3.IntegrityError: 
        return jsonify({"error": "Username exists"}), 409
    finally: conn.close()

# =============================
# 🔹 ROUTES: TÌM KIẾM CHROMA DB (Kèm Luật chấm điểm của bạn)
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
            
            # --- LUẬT CHẤM ĐIỂM (RERANKING) NHƯ CŨ CỦA BẠN ---
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
# 🔹 ROUTES: LAYOUT ENGINE (MỚI)
# =============================

@app.route('/generate_layout', methods=['POST'])
def generate_layout_api():
    data = request.json
    user_prompt = data.get('prompt', '')
    if not user_prompt: return jsonify({"error": "Prompt trống"}), 400

    try:
        # 1. Trích xuất ý định
        extract_raw = call_llm(f"Extract room_type and style from: {user_prompt}. Return JSON with format {{\"room_type\": \"...\", \"style_phrase\": \"...\"}}")
        extract_data = safe_json_parse(extract_raw) or {"room_type": "living_room", "style_phrase": user_prompt}
        
        from graph_logic import ROOM_RULES_CONFIG, build_scene_graph, solve_optimal_subgraph
        room_type = extract_data.get('room_type', 'living_room')
        style = extract_data.get('style_phrase', '')
        
        # 2. Lấy ứng viên từ Chroma
        categories = ROOM_RULES_CONFIG.get(room_type, {}).get("required", []) + ROOM_RULES_CONFIG.get(room_type, {}).get("optional", [])
        candidates = {}
        for cat in categories:
            try:
                col = db_client.get_collection(name=cat)
                res = col.query(query_texts=[style], n_results=10)
                if res['ids']:
                    candidates[cat] = [{"uid": res['ids'][0][i], "meta": res['metadatas'][0][i], "path": res['metadatas'][0][i].get('path', '')} for i in range(len(res['ids'][0]))]
            except: pass
        
        # 3. Lọc bằng NetworkX
        G = build_scene_graph(candidates)
        final_items = solve_optimal_subgraph(G, room_type)
        if not final_items: return jsonify({"error": "Không tìm thấy đồ vật phù hợp để xếp"}), 404
        
        required_uids = {it['uid'] for it in final_items}
        furn_str = "\n".join([f"- {it['type']} (UID: {it['uid']}): size(w={it.get('dimensions', {}).get('width', 1.0)}, h={it.get('dimensions', {}).get('height', 1.0)}, l={it.get('dimensions', {}).get('length', 1.0)})" for it in final_items])
        
        # 4. Gemini Spatial Engine
        feedback = ""
        room_w, room_l = 5.0, 5.0 # Mặc định

        for attempt in range(1, 4):
            prompt = f"{feedback}\nSTRICT TASK: Place ALL these items in a {room_w}x{room_l}m room.\nREQUIRED UIDs: {list(required_uids)}\nITEMS:\n{furn_str}\nRULES:\n- Return ONLY JSON.\n- Do NOT skip items."
            layout_raw = call_llm(prompt, "Expert Interior Designer. Use coordinates [x, z, rotation_in_radians].")
            layout_json = safe_json_parse(layout_raw)
            
            if not layout_json or 'furniture' not in layout_json: 
                feedback = f"Attempt {attempt} Fail: Invalid JSON."
                continue

            try:
                engine = GeometryEngine(room_w, room_l)
                items_to_place = []
                for f in layout_json.get('furniture', []):
                    if f.get('uid') in required_uids:
                        # Fallback cho AI hay viết nhầm size
                        size = f.get('size', [1,1,1])
                        if len(size) != 3: size = [1,1,1]
                        items_to_place.append(FurnitureItem(type=f.get('type',''), uid=f.get('uid'), position=f.get('position', [0,0,0]), size=size))
                
                items_to_place.sort(key=lambda x: x.size[0] * x.size[2], reverse=True)

                for it in items_to_place:
                    origin = next((o for o in final_items if o['uid'] == it.uid), None)
                    if origin: it.path = origin.get('path', f"{it.uid}.glb")
                    engine.validate_and_add(it)

                if {it.uid for it in engine.valid_items} == required_uids:
                    return jsonify({
                        "metadata": {"room_width": room_w, "room_length": room_l, "style": style},
                        "furniture": [it.dict() for it in engine.valid_items]
                    })
                
                missing = required_uids - {it.uid for it in engine.valid_items}
                feedback = f"Attempt {attempt} Fail. Errors: {engine.errors}. Missing UIDs: {list(missing)}"
            except Exception as e: 
                feedback = f"Validation crash: {e}"

        return jsonify({"error": "AI layout failed after retries"}), 500
    except Exception as e: return jsonify({"error": str(e)}), 500


# =============================
# 🔹 ROUTES: PHỤ TRỢ KHÁC
# =============================

@app.route('/models/<path:filename>')
def serve_model(filename):
    filename = secure_filename(filename)
    if (Path("D:/Web") / filename).exists(): return send_from_directory("D:/Web", filename)
    if (GLBS_ROOT / filename).exists(): return send_from_directory(GLBS_ROOT, filename)
    return "Not found", 404

@app.route('/sketchfab', methods=['POST'])
def get_model():
    data = request.json
    QUERY = data.get('query', '').strip().lower()
    if not QUERY: return jsonify({"error": "Thiếu từ khóa tìm kiếm (query)."}), 400
    
    # ⚠️ CHÚ Ý BẠN ƠI: HÃY DÁN CÁI LOGIC CŨ CỦA BẠN VÀO DƯỚI ĐÂY NHÉ!
    # ... (Giữ nguyên logic Sketchfab cũ của bạn ở đây) ...
    return jsonify({"error": "Vui lòng copy logic Sketchfab cũ của bạn vào đây"})


if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, port=8000)