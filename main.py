import os
import cv2
import numpy as np
import base64
import httpx
import logging
import asyncio
import random
import uuid
import hashlib
import io
import time
import statistics
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from inference_sdk import InferenceHTTPClient
from dotenv import load_dotenv

# Lệnh này bắt buộc phải có để Python tìm và đọc file .env
load_dotenv()

# ==========================================
# 1. CẤU HÌNH & LOGGING
# ==========================================
class RequestIdFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "N/A"
        return True

logging.basicConfig(level=logging.INFO, format='{"level": "%(levelname)s", "request_id": "%(request_id)s", "msg": "%(message)s"}')
for handler in logging.root.handlers:
    handler.addFilter(RequestIdFilter())

logger = logging.getLogger("architect")

# Thông tin môi trường
API_KEY = os.environ.get("ROBOFLOW_API_KEY")
if not API_KEY:
    logger.error("WARNING: ROBOFLOW_API_KEY is not set. API calls to Roboflow will fail with 403 Forbidden.")
WORKSPACE_NAME = "finetuneyolov8"
WORKFLOW_ID = "custom-workflow"
MAX_FILE_SIZE = 5 * 1024 * 1024
ASSET_CACHE = {}
IMAGE_CACHE = {}

cv_executor = ThreadPoolExecutor(max_workers=min(32, (os.cpu_count() or 1) * 4))
GLOBAL_SEMAPHORE = asyncio.Semaphore(50)

# ==========================================
# 2. CIRCUIT BREAKER LOGIC
# ==========================================
class CircuitBreaker:
    def __init__(self, threshold=5, recovery_time=60):
        self.threshold, self.recovery_time = threshold, recovery_time
        self.failure_count, self.state, self.last_failure_time = 0, "CLOSED", 0
        self.lock = asyncio.Lock()

    async def call_allowed(self):
        async with self.lock:
            if self.state == "OPEN":
                if (time.time() - self.last_failure_time) > self.recovery_time:
                    self.state = "HALF-OPEN"
                    return True
                return False
            return True

    async def record_failure(self):
        async with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.threshold: self.state = "OPEN"

    async def record_success(self):
        async with self.lock:
            self.failure_count, self.state = 0, "CLOSED"

CB = CircuitBreaker()

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http_client = httpx.AsyncClient(timeout=30.0)
    # Khởi tạo Roboflow SDK Client
    app.state.roboflow_client = InferenceHTTPClient(
        api_url="https://serverless.roboflow.com", 
        api_key=API_KEY
    )
    # Preload Assets
    # Preload Assets
    base_dir = os.path.dirname(os.path.abspath(__file__))
    asset_dir = os.path.join(base_dir, "icon") # <--- ĐÃ SỬA THÀNH THƯ MỤC "icon"
    if os.path.exists(asset_dir):
        for f in os.listdir(asset_dir):
            if f.lower().endswith(".png"):
                img = cv2.imread(os.path.join(asset_dir, f), cv2.IMREAD_UNCHANGED)
                if img is not None: ASSET_CACHE[f] = img
    yield
    await app.state.http_client.aclose()
    cv_executor.shutdown(wait=True)

app = FastAPI(title="10/10 AI Architect Final", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.middleware("http")
async def tracing_middleware(request: Request, call_next):
    request.state.id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.id
    return response

# ==========================================
# 3. CV CORE (TÍCH HỢP VECTORIZE LÀM PHẲNG)
# ==========================================
def overlay_transparent_safe(background, overlay, x, y, w, h):
    """Hàm chèn asset PNG trong suốt với boundary safety"""
    try:
        bg_h, bg_w = background.shape[:2]
        x, y, w, h = int(x), int(y), int(w), int(h)
        x_s, y_s = max(0, x), max(0, y)
        x_e, y_e = min(bg_w, x + w), min(bg_h, y + h)
        if x_s >= x_e or y_s >= y_e: return background
        overlay_res = cv2.resize(overlay, (w, h))
        ov_crop = overlay_res[y_s-y:y_e-y, x_s-x:x_e-x]
        img_rgb, mask = ov_crop[:, :, :3], ov_crop[:, :, 3] / 255.0
        for c in range(3):
            background[y_s:y_e, x_s:x_e, c] = (1.0 - mask) * background[y_s:y_e, x_s:x_e, c] + mask * img_rgb[:, :, c]
    except: pass
    return background

def align_and_unify_thickness(walls, is_horizontal, tolerance=15):
    """Hàm căn dóng và đồng nhất độ dày (từ vectorize_data)"""
    if not walls: return
    axis_key = 'y' if is_horizontal else 'x'
    thick_key = 'height' if is_horizontal else 'width'
    
    for w in walls:
        w['center_axis'] = w[axis_key] + w[thick_key] / 2

    clusters = []
    for w in walls:
        placed = False
        for c in clusters:
            if abs(w['center_axis'] - c['center_axis']) <= tolerance:
                c['items'].append(w)
                c['center_axis'] = sum(i['center_axis'] for i in c['items']) / len(c['items'])
                placed = True
                break
        if not placed:
            clusters.append({'center_axis': w['center_axis'], 'items': [w]})

    for c in clusters:
        median_thickness = int(statistics.median([i[thick_key] for i in c['items']]))
        aligned_center = int(c['center_axis'])
        for w in c['items']:
            w[thick_key] = median_thickness
            w[axis_key] = int(aligned_center - median_thickness / 2)
            if 'center_axis' in w: del w['center_axis']

def sync_cv_pipeline(content, b64_mask, rid):
    """Xử lý tường và phòng (Đã tích hợp làm phẳng)"""
    try:
        # --- FIX VẤN ĐỀ 1: Giải mã Base64 giống hệt vectorize_data.py ---
        img_data = base64.b64decode(b64_mask)
        np_arr = np.frombuffer(img_data, np.uint8)
        wall_mask = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)
        
        if wall_mask is None: 
            logger.error(f"Lỗi: Không thể giải mã chuỗi base64 thành ảnh trong sync_cv_pipeline.")
            return None
        
        # Binarize mask giống hệt file gốc
        wall_mask_image = np.where(wall_mask > 0, 255, 0).astype(np.uint8)
        
        img_h, img_w = wall_mask_image.shape[:2]
        img_area = img_h * img_w

        # --- Room Detection (Giữ nguyên logic cũ của bạn) ---
        closed_wall = cv2.dilate(wall_mask_image, np.ones((5, 5), np.uint8), iterations=1)
        rooms_mask = cv2.bitwise_not(closed_wall)
        cnts_r, _ = cv2.findContours(rooms_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        sorted_cnts = sorted(cnts_r, key=cv2.contourArea, reverse=True)
        rooms = []
        for idx, c in enumerate(sorted_cnts[1:]):
            area = cv2.contourArea(c)
            if 0.001 * img_area < area < 0.8 * img_area:
                epsilon = 0.01 * cv2.arcLength(c, True)
                approx = cv2.approxPolyDP(c, epsilon, True)
                rooms.append({"id": idx, "area_px": area, "poly": approx.reshape(-1, 2).tolist()})

        # --- Vectorization & Tách Hướng (Từ vectorize_data) ---
        kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
        horizontal_mask = cv2.morphologyEx(wall_mask_image, cv2.MORPH_OPEN, kernel_h)

        kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
        vertical_mask = cv2.morphologyEx(wall_mask_image, cv2.MORPH_OPEN, kernel_v)

        hv_mask = cv2.bitwise_or(horizontal_mask, vertical_mask)
        kernel_dilate = np.ones((5, 5), np.uint8) # Khai báo kernel rõ ràng
        hv_mask_dilated = cv2.dilate(hv_mask, kernel_dilate, iterations=1)

        diagonal_mask = cv2.subtract(wall_mask_image, hv_mask_dilated)
        kernel_diag = np.ones((3, 3), np.uint8) # Khai báo kernel rõ ràng
        diagonal_mask = cv2.morphologyEx(diagonal_mask, cv2.MORPH_OPEN, kernel_diag)

        wall_vectors = []
        diagonal_vectors = []

        # Rút trích H và V gộp chung vào wall_vectors như code gốc
        contours_h, _ = cv2.findContours(horizontal_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours_h:
            x, y, w, h = cv2.boundingRect(cnt)
            if w > 15: 
                wall_vectors.append({"type": "horizontal", "x": x, "y": y, "width": w, "height": h})

        contours_v, _ = cv2.findContours(vertical_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours_v:
            x, y, w, h = cv2.boundingRect(cnt)
            if h > 15: 
                wall_vectors.append({"type": "vertical", "x": x, "y": y, "width": w, "height": h})

        contours_d, _ = cv2.findContours(diagonal_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for cnt in contours_d:
            if cv2.contourArea(cnt) > 200:
                rect = cv2.minAreaRect(cnt)
                box = cv2.boxPoints(rect)
                box = np.int32(box)
                diagonal_vectors.append({
                    "type": "diagonal", "center": [float(rect[0][0]), float(rect[0][1])], 
                    "dimensions": [float(rect[1][0]), float(rect[1][1])], "angle": float(rect[2]), "corners": box.tolist()
                })

        # Tách lại H và V để xử lý
        horizontals = [v for v in wall_vectors if v['type'] == 'horizontal']
        verticals = [v for v in wall_vectors if v['type'] == 'vertical']

        # --- Làm Phẳng & Khắc Phục Chồng Chéo ---
        if horizontals: align_and_unify_thickness(horizontals, is_horizontal=True)
        if verticals: align_and_unify_thickness(verticals, is_horizontal=False)

        final_verticals = []
        for v in verticals:
            vx1, vy1 = v['x'], v['y']
            vx2, vy2 = v['x'] + v['width'], v['y'] + v['height']

            for h in horizontals:
                hx1, hy1 = h['x'], h['y']
                hx2, hy2 = h['x'] + h['width'], h['y'] + h['height']

                if vx1 < hx2 and vx2 > hx1 and vy1 < hy2 and vy2 > hy1:
                    if hy1 <= vy1 <= hy2: vy1 = hy2
                    if hy1 <= vy2 <= hy2: vy2 = hy1

            new_height = vy2 - vy1
            if new_height > 5:
                v['y'] = int(vy1)
                v['height'] = int(new_height)
                final_verticals.append(v)

        final_vectors = horizontals + final_verticals + diagonal_vectors

        # --- Vẽ lại lên Canvas mới (Nền trắng, tường màu tối) ---
        optimized_canvas = np.ones((img_h, img_w, 3), dtype=np.uint8) * 255 # Khởi tạo nền trắng
        wall_color = (44, 62, 80) # Màu tường đen xám chuyên nghiệp

        for h in horizontals:
            cv2.rectangle(optimized_canvas, (h['x'], h['y']), (h['x'] + h['width'], h['y'] + h['height']), wall_color, -1)
        for v in final_verticals:
            cv2.rectangle(optimized_canvas, (v['x'], v['y']), (v['x'] + v['width'], v['y'] + v['height']), wall_color, -1)
        for d in diagonal_vectors:
            box = np.array(d['corners'])
            cv2.drawContours(optimized_canvas, [box], 0, wall_color, -1)

        return {"canvas": optimized_canvas, "rooms": rooms, "vectors": final_vectors}
    except Exception as e: 
        logger.error(f"CV Exception: {e}")
        return None

# ==========================================
# 4. MAIN ENDPOINT
# ==========================================
@app.post("/api/process")
async def process(request: Request, file: UploadFile = File(...)):
    rid = getattr(request.state, "id", str(uuid.uuid4()))
    _log = logging.LoggerAdapter(logger, {"request_id": rid})
    
    if not await CB.call_allowed(): raise HTTPException(503, "Service Circuit Broken")

    content = await file.read()
    img_hash = hashlib.sha256(content).hexdigest()

    if img_hash in IMAGE_CACHE:
        _log.info("Idempotency HIT")
        return IMAGE_CACHE[img_hash]

    async with GLOBAL_SEMAPHORE:
        try:
            # 1. Gọi Roboflow Wall Segmentation (HTTP)
            wall_url = f"https://outline.roboflow.com/wall-segmentation-cmjwq-5k73y/3?api_key={API_KEY}"
            resp = await app.state.http_client.post(wall_url, files={"file": (file.filename, content, file.content_type)})
            resp.raise_for_status()
            await CB.record_success()
            b64_mask = resp.json().get("predictions", {}).get("segmentation_mask")
        except:
            await CB.record_failure()
            raise HTTPException(502, "Wall API Failed")

        # 2. Xử lý CV (Tường & Phòng) đã được nâng cấp
        cv_res = await asyncio.get_running_loop().run_in_executor(cv_executor, sync_cv_pipeline, content, b64_mask, rid)
        if not cv_res: raise HTTPException(500, "CV Process Failed")
        
        canvas, rooms, vectors = cv_res["canvas"], cv_res["rooms"], cv_res["vectors"]
        # 3. Gọi Roboflow Workflow (Nội thất) - Sửa lỗi asset matching
        # 3. Gọi Roboflow Workflow (Nội thất)
        # 3. Gọi Roboflow Workflow (Nội thất)
        # 3. Gọi Roboflow Workflow (Nội thất)
        workflow_output = {} 
        try:
            _log.info("🚀 Bắt đầu gọi Roboflow Custom Workflow với 2 nhánh Classification...")
            
            # (Giữ nguyên phần chuyển đổi image_rgb_for_roboflow)
            np_arr = np.frombuffer(content, np.uint8)
            image_bgr = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            image_rgb_for_roboflow = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)

            def call_roboflow():
                return app.state.roboflow_client.run_workflow(
                    workspace_name=WORKSPACE_NAME,
                    workflow_id=WORKFLOW_ID,
                    images={"image": image_rgb_for_roboflow},
                    use_cache=False
                )
            
            wf_res = await asyncio.get_running_loop().run_in_executor(cv_executor, call_roboflow)
            output = wf_res[0] if isinstance(wf_res, list) else wf_res
            workflow_output = output
            
            # --- LOGIC XỬ LÝ MỚI: KẾT HỢP 2 MODEL PHÂN LOẠI ---
            real_predictions = output.get("real_predictions", {}).get("predictions", []) 
            class1_preds = output.get("class1_predictions", []) # Không offset
            class2_preds = output.get("class2_predictions", []) # Có offset

            DET_THRESHOLD = 0.8
            CLS_THRESHOLD = 0.6  # Hạ nhẹ threshold nếu cần bắt nhiều hơn

            CLASS_TO_ICON = {
                "sofas": "sofa.png", "sofa": "sofa.png", "bed": "bed.png",
                "bathtub": "bathtub.png", "toilet": "toilet.png", "sink": "sink.png",
                "chair": "armchair.png", "armchair": "armchair.png", "table": "table.png",
                "nightstand": "nightstand.png", "wardrobe": "wardrobe.png",
                "tv_stand": "tv_stand.png", "door": "door.png"
            }

            # Gom tất cả kết quả từ cả 2 model vào một map theo parent_id
            # parent_id chính là detection_id của model Detection hoặc Offset
            best_class_map = {}

            def update_best_map(predictions):
                for c in predictions:
                    p_id = c.get('parent_id')
                    conf = c.get('confidence', 0)
                    label = c.get('top')
                    
                    if label and conf >= CLS_THRESHOLD:
                        # Nếu ID này chưa có, hoặc kết quả mới có độ tự tin cao hơn thì cập nhật
                        if p_id not in best_class_map or conf > best_class_map[p_id]['conf']:
                            best_class_map[p_id] = {'label': label, 'conf': conf}

            update_best_map(class1_preds)
            update_best_map(class2_preds)

            # Duyệt danh sách detection gốc để render
            for det in real_predictions:
                if det.get('confidence', 0) < DET_THRESHOLD:
                    continue 

                det_id = det.get('detection_id')
                
                # Tìm trong map tổng hợp xem nhánh nào (1 hoặc 2) đã nhận diện được
                result = best_class_map.get(det_id)
                
                if not result:
                    continue
                
                raw_class = str(result['label']).lower().strip()
                asset_key = CLASS_TO_ICON.get(raw_class, f"{raw_class}.png")
                
                if asset_key in ASSET_CACHE:
                    w, h = det['width'], det['height']
                    x_min, y_min = det['x'] - w/2, det['y'] - h/2
                    canvas = overlay_transparent_safe(canvas, ASSET_CACHE[asset_key], x_min, y_min, w, h)
                    _log.info(f"✅ Render {raw_class} (Conf: {result['conf']:.2f}) cho ID {det_id}")
                else:
                    _log.warning(f"⚠️ Thiếu icon: {asset_key}")

        except Exception as e:
            _log.error(f"Lỗi Furniture Workflow: {e}")


        # 4. Encode và Cache
        _, buffer = cv2.imencode('.png', canvas)
        final_res = {
            "status": "success", 
            "saved_at": "Bộ nhớ đệm",
            "result_image_base64": f"data:image/png;base64,{base64.b64encode(buffer).decode()}",
            "vectors": vectors,
            "rooms": rooms,
            "workflow_result": workflow_output,  # <--- Bổ sung dòng này để gửi qua cho index.html
            "rid": rid, 
            "hash": img_hash
        }
        IMAGE_CACHE[img_hash] = final_res
        return final_res

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)