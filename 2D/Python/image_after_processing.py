import cv2
import numpy as np
import os
import random
import glob
import math
import string
import re

# ================= CẤU HÌNH =================
ICON_DIR = r"D:\KLTN\2D\image_after_processing"
OUTPUT_IMG_DIR = r"D:\KLTN\2D\dataset\images"
OUTPUT_TXT_DIR = r"D:\KLTN\2D\dataset\labels"
NUM_IMAGES_TO_GENERATE = 1000
CANVAS_SIZE = 800
MIN_ICON_SIZE = 60  # Pixel tối thiểu sau resize, tránh icon quá nhỏ

os.makedirs(OUTPUT_IMG_DIR, exist_ok=True)
os.makedirs(OUTPUT_TXT_DIR, exist_ok=True)

# ================= CLASS MAP =================
icon_paths = glob.glob(os.path.join(ICON_DIR, "*.*"))
if not icon_paths:
    print(f"Không tìm thấy ảnh nào trong {ICON_DIR}")
    exit()

def extract_classname(filepath):
    basename = os.path.splitext(os.path.basename(filepath))[0]
    return re.sub(r'\d+$', '', basename).strip().lower()

all_classnames = sorted(set(extract_classname(p) for p in icon_paths))
CLASS_MAP = {name: idx for idx, name in enumerate(all_classnames)}

print(f"Phát hiện {len(CLASS_MAP)} class:")
for name, idx in CLASS_MAP.items():
    print(f"  [{idx}] {name}")
print()

# ================= ICON POOL =================
icon_pool = []

def get_balanced_icons(n):
    global icon_pool
    while len(icon_pool) < n:
        temp = icon_paths.copy()
        random.shuffle(temp)
        icon_pool.extend(temp)
    selected = icon_pool[:n]
    icon_pool = icon_pool[n:]
    return selected

# ================= HELPER FUNCTIONS =================
def overlay_image_alpha(img, img_overlay, x, y, alpha_mask):
    y1, y2 = max(0, y), min(img.shape[0], y + img_overlay.shape[0])
    x1, x2 = max(0, x), min(img.shape[1], x + img_overlay.shape[1])
    y1o, y2o = max(0, -y), min(img_overlay.shape[0], img.shape[0] - y)
    x1o, x2o = max(0, -x), min(img_overlay.shape[1], img.shape[1] - x)
    if y1 >= y2 or x1 >= x2 or y1o >= y2o or x1o >= x2o:
        return img
    img_crop = img[y1:y2, x1:x2]
    img_overlay_crop = img_overlay[y1o:y2o, x1o:x2o]
    alpha = alpha_mask[y1o:y2o, x1o:x2o, np.newaxis]
    img_crop[:] = alpha * img_overlay_crop + (1 - alpha) * img_crop
    return img

def draw_dashed_line_safe(img, occupancy, pt1, pt2, color, thickness=1, dash_length=15):
    """Vẽ nét đứt, bỏ qua đoạn nào đi qua vùng occupied"""
    dist = math.hypot(pt2[0] - pt1[0], pt2[1] - pt1[1])
    if dist == 0: return
    dashes = int(dist / dash_length)
    for i in range(dashes):
        sx = int(pt1[0] + (pt2[0] - pt1[0]) * i / dashes)
        sy = int(pt1[1] + (pt2[1] - pt1[1]) * i / dashes)
        ex = int(pt1[0] + (pt2[0] - pt1[0]) * (i + 0.5) / dashes)
        ey = int(pt1[1] + (pt2[1] - pt1[1]) * (i + 0.5) / dashes)
        mx = max(0, min(CANVAS_SIZE - 1, (sx + ex) // 2))
        my = max(0, min(CANVAS_SIZE - 1, (sy + ey) // 2))
        if not occupancy[my, mx]:
            cv2.line(img, (sx, sy), (ex, ey), color, thickness)

def is_overlap(x, y, w, h, placed_boxes, padding=0):
    """Đã FIX: Đưa padding về 0, Icon có thể chạm mép nhau nhưng không đè"""
    for (bx, by, bw, bh) in placed_boxes:
        if (x - padding < bx + bw and x + w + padding > bx and
                y - padding < by + bh and y + h + padding > by):
            return True
    return False

# ================= XỬ LÝ TƯỜNG (RAYCASTING) =================
def get_safe_E_horizontal(rect, wy1, wy2, other_rects, max_E_left, max_E_right):
    """Tính toán chiều dài cho phép của tường ngang để không đâm vào icon khác"""
    ix1, iy1, w, h = rect
    ix2 = ix1 + w
    E_L, E_R = max_E_left, max_E_right
    for (ox1, oy1, ow, oh) in other_rects:
        ox2, oy2 = ox1 + ow, oy1 + oh
        if wy1 < oy2 and wy2 > oy1: # Chạm mặt cắt ngang
            if ox2 <= ix1: E_L = min(E_L, ix1 - ox2) # Chặn bên trái
            if ox1 >= ix2: E_R = min(E_R, ox1 - ix2) # Chặn bên phải
    return max(0, E_L), max(0, E_R)

def get_safe_E_vertical(rect, wx1, wx2, other_rects, max_E_top, max_E_bot):
    """Tính toán chiều dài cho phép của tường dọc để không đâm vào icon khác"""
    ix1, iy1, w, h = rect
    iy2 = iy1 + h
    E_T, E_B = max_E_top, max_E_bot
    for (ox1, oy1, ow, oh) in other_rects:
        ox2, oy2 = ox1 + ow, oy1 + oh
        if wx1 < ox2 and wx2 > ox1: # Chạm mặt cắt dọc
            if oy2 <= iy1: E_T = min(E_T, iy1 - oy2) # Chặn bên trên
            if oy1 >= iy2: E_B = min(E_B, oy1 - iy2) # Chặn bên dưới
    return max(0, E_T), max(0, E_B)

def draw_safe_walls(canvas, rect, other_rects):
    """Vẽ tường dùng cv2.rectangle chặn điểm dừng chính xác, không dùng masking nữa"""
    ix1, iy1, w, h = rect
    ix2, iy2 = ix1 + w, iy1 + h
    wt = random.randint(6, 22)

    # Các hình chữ nhật cốt lõi (Core Rect) kề sát Icon
    core_top = (ix1, iy1 - wt, ix2, iy1)
    core_bot = (ix1, iy2, ix2, iy2 + wt)
    core_left = (ix1 - wt, iy1, ix1, iy2)
    core_right = (ix2, iy1, ix2 + wt, iy2)

    def is_core_clear(core_r):
        """Kiểm tra không gian kề Icon có bị icon khác đè vào không"""
        cx1, cy1, cx2, cy2 = core_r
        for (ox1, oy1, ow, oh) in other_rects:
            ox2, oy2 = ox1 + ow, oy1 + oh
            if cx1 < ox2 and cx2 > ox1 and cy1 < oy2 and cy2 > oy1:
                return False
        return True

    valid_edges = []
    if is_core_clear(core_top): valid_edges.append('TOP')
    if is_core_clear(core_bot): valid_edges.append('BOTTOM')
    if is_core_clear(core_left): valid_edges.append('LEFT')
    if is_core_clear(core_right): valid_edges.append('RIGHT')

    valid_corners = []
    if 'TOP' in valid_edges and 'LEFT' in valid_edges and is_core_clear((ix1 - wt, iy1 - wt, ix1, iy1)):
        valid_corners.append('TL')
    if 'TOP' in valid_edges and 'RIGHT' in valid_edges and is_core_clear((ix2, iy1 - wt, ix2 + wt, iy1)):
        valid_corners.append('TR')
    if 'BOTTOM' in valid_edges and 'LEFT' in valid_edges and is_core_clear((ix1 - wt, iy2, ix1, iy2 + wt)):
        valid_corners.append('BL')
    if 'BOTTOM' in valid_edges and 'RIGHT' in valid_edges and is_core_clear((ix2, iy2, ix2 + wt, iy2 + wt)):
        valid_corners.append('BR')

    topologies = []
    if valid_edges: topologies.append('I')
    if valid_corners: topologies.append('L')
    if not topologies: return

    chosen_topo = random.choice(topologies)
    E1, E2 = random.randint(50, 300), random.randint(50, 300)

    if chosen_topo == 'I':
        edge = random.choice(valid_edges)
        if edge == 'TOP':
            EL, ER = get_safe_E_horizontal(rect, iy1 - wt, iy1, other_rects, E1, E2)
            cv2.rectangle(canvas, (ix1 - EL, iy1 - wt), (ix2 + ER, iy1), (0,0,0), -1)
        elif edge == 'BOTTOM':
            EL, ER = get_safe_E_horizontal(rect, iy2, iy2 + wt, other_rects, E1, E2)
            cv2.rectangle(canvas, (ix1 - EL, iy2), (ix2 + ER, iy2 + wt), (0,0,0), -1)
        elif edge == 'LEFT':
            ET, EB = get_safe_E_vertical(rect, ix1 - wt, ix1, other_rects, E1, E2)
            cv2.rectangle(canvas, (ix1 - wt, iy1 - ET), (ix1, iy2 + EB), (0,0,0), -1)
        elif edge == 'RIGHT':
            ET, EB = get_safe_E_vertical(rect, ix2, ix2 + wt, other_rects, E1, E2)
            cv2.rectangle(canvas, (ix2, iy1 - ET), (ix2 + wt, iy2 + EB), (0,0,0), -1)

    elif chosen_topo == 'L':
        corner = random.choice(valid_corners)
        if corner == 'TL':
            _, ER = get_safe_E_horizontal(rect, iy1 - wt, iy1, other_rects, 0, E1)
            _, EB = get_safe_E_vertical(rect, ix1 - wt, ix1, other_rects, 0, E2)
            cv2.rectangle(canvas, (ix1 - wt, iy1 - wt), (ix2 + ER, iy1), (0,0,0), -1)
            cv2.rectangle(canvas, (ix1 - wt, iy1 - wt), (ix1, iy2 + EB), (0,0,0), -1)
        elif corner == 'TR':
            EL, _ = get_safe_E_horizontal(rect, iy1 - wt, iy1, other_rects, E1, 0)
            _, EB = get_safe_E_vertical(rect, ix2, ix2 + wt, other_rects, 0, E2)
            cv2.rectangle(canvas, (ix1 - EL, iy1 - wt), (ix2 + wt, iy1), (0,0,0), -1)
            cv2.rectangle(canvas, (ix2, iy1 - wt), (ix2 + wt, iy2 + EB), (0,0,0), -1)
        elif corner == 'BL':
            _, ER = get_safe_E_horizontal(rect, iy2, iy2 + wt, other_rects, 0, E1)
            ET, _ = get_safe_E_vertical(rect, ix1 - wt, ix1, other_rects, E2, 0)
            cv2.rectangle(canvas, (ix1 - wt, iy2), (ix2 + ER, iy2 + wt), (0,0,0), -1)
            cv2.rectangle(canvas, (ix1 - wt, iy1 - ET), (ix1, iy2 + wt), (0,0,0), -1)
        elif corner == 'BR':
            EL, _ = get_safe_E_horizontal(rect, iy2, iy2 + wt, other_rects, E1, 0)
            ET, _ = get_safe_E_vertical(rect, ix2, ix2 + wt, other_rects, E2, 0)
            cv2.rectangle(canvas, (ix1 - EL, iy2), (ix2 + wt, iy2 + wt), (0,0,0), -1)
            cv2.rectangle(canvas, (ix2, iy1 - ET), (ix2 + wt, iy2 + wt), (0,0,0), -1)

# ================= SINH ẢNH =================
def generate_synthetic_image(image_idx):
    canvas = np.ones((CANVAS_SIZE, CANVAS_SIZE, 3), dtype=np.uint8) * 255
    occupancy = np.zeros((CANVAS_SIZE, CANVAS_SIZE), dtype=bool)

    yolo_labels = []
    placed_boxes = []
    icons_to_draw = []

    num_icons = random.randint(5, 8)
    selected_icons = get_balanced_icons(num_icons)

    # Bước 1: Tính toán Bounding Box (padding=0)
    for icon_path in selected_icons:
        icon = cv2.imread(icon_path, cv2.IMREAD_UNCHANGED)
        if icon is None: continue

        scale = random.uniform(0.8, 1.4)
        new_w = max(MIN_ICON_SIZE, int(icon.shape[1] * scale))
        new_h = max(MIN_ICON_SIZE, int(icon.shape[0] * scale))
        icon = cv2.resize(icon, (new_w, new_h))

        if icon.shape[2] == 4:
            alpha_mask = icon[:, :, 3] / 255.0
            icon_rgb = icon[:, :, :3]
        else:
            gray = cv2.cvtColor(icon, cv2.COLOR_BGR2GRAY)
            _, mask = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
            alpha_mask = mask / 255.0
            icon_rgb = icon

        margin = 20
        placed = False
        for _ in range(50):
            x = random.randint(margin, max(margin, CANVAS_SIZE - new_w - margin))
            y = random.randint(margin, max(margin, CANVAS_SIZE - new_h - margin))
            if not is_overlap(x, y, new_w, new_h, placed_boxes, padding=0):
                placed = True
                break

        if not placed: continue

        placed_boxes.append((x, y, new_w, new_h))
        icons_to_draw.append((icon_rgb, alpha_mask, x, y, new_w, new_h, icon_path))

        classname = extract_classname(icon_path)
        class_id = CLASS_MAP.get(classname, 0)
        x_center = (x + new_w / 2.0) / CANVAS_SIZE
        y_center = (y + new_h / 2.0) / CANVAS_SIZE
        w_norm   = new_w / CANVAS_SIZE
        h_norm   = new_h / CANVAS_SIZE
        yolo_labels.append(f"{class_id} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")

    # Bước 2: Vẽ Tường (An toàn, tự động dừng nếu chạm Box khác)
    for i, rect in enumerate(placed_boxes):
        if random.random() < 0.6:
            other_rects = placed_boxes[:i] + placed_boxes[i+1:]
            draw_safe_walls(canvas, rect, other_rects)

    # Bước 3: Cập nhật Occupancy Map (Bao gồm cả Box và Tường đen)
    for (x, y, w, h) in placed_boxes:
        occupancy[y:y+h, x:x+w] = True
    wall_mask = (canvas[:,:,0] == 0) & (canvas[:,:,1] == 0) & (canvas[:,:,2] == 0)
    occupancy = occupancy | wall_mask

    # Bước 4: Vẽ nét đứt (Dùng Occupancy để không cắt ngang đồ và tường)
    for _ in range(random.randint(2, 5)):
        pos = random.randint(0, CANVAS_SIZE)
        if random.choice([True, False]):
            draw_dashed_line_safe(canvas, occupancy, (0, pos), (CANVAS_SIZE, pos), (120, 120, 120), 1, 15)
        else:
            draw_dashed_line_safe(canvas, occupancy, (pos, 0), (pos, CANVAS_SIZE), (120, 120, 120), 1, 15)

    # Bước 5: Chèn Text (Né cả Tường và Icon)
    for _ in range(random.randint(5, 12)):
        txt_x = random.randint(20, CANVAS_SIZE - 60)
        txt_y = random.randint(30, CANVAS_SIZE - 30)
        
        check_y = max(0, min(CANVAS_SIZE - 1, txt_y))
        check_x = max(0, min(CANVAS_SIZE - 1, txt_x))
        if occupancy[check_y, check_x]:
            continue 

        font_scale = random.uniform(0.4, 0.7)
        color = (0, 0, 0) if random.random() > 0.4 else (150, 150, 150)
        text = random.choice([
            str(random.randint(1000, 5000)),
            random.choice(string.ascii_uppercase) + "-" + str(random.randint(1, 15)),
            random.choice(["LDK", "WC", "DN", "UP", "CH"])
        ])
        cv2.putText(canvas, text, (txt_x, txt_y), cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1)

    # Bước 6: Cuối cùng mới vẽ Icon đè lên để che khuyết điểm 1px (nếu có)
    for (icon_rgb, alpha_mask, x, y, new_w, new_h, _) in icons_to_draw:
        canvas = overlay_image_alpha(canvas, icon_rgb, x, y, alpha_mask)

    # Bước 7: Lưu File
    img_name = f"synth_pro_{image_idx:05d}.jpg"
    txt_name = f"synth_pro_{image_idx:05d}.txt"
    cv2.imwrite(os.path.join(OUTPUT_IMG_DIR, img_name), canvas)
    with open(os.path.join(OUTPUT_TXT_DIR, txt_name), 'w') as f:
        f.write("\n".join(yolo_labels))

# ================= MAIN =================
print("Bắt đầu sinh dữ liệu siêu cấp (Fix lỗi đè Tường)...")
for i in range(NUM_IMAGES_TO_GENERATE):
    generate_synthetic_image(i)
    if (i + 1) % 100 == 0:
        print(f"Đã tạo {i + 1}/{NUM_IMAGES_TO_GENERATE} ảnh...")
print("Hoàn thành!")

print("\n--- Copy vào data.yaml ---")
print(f"nc: {len(CLASS_MAP)}")
print(f"names: {list(CLASS_MAP.keys())}")