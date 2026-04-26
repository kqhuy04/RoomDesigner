import base64
import numpy as np
import cv2
import json
import statistics

json_file_path = "ket_qua.json" 

with open(json_file_path, 'r', encoding='utf-8') as f:
    model_output = json.load(f)

def decode_base64_to_image(b64_string):
    """Giải mã chuỗi base64 thành ma trận ảnh OpenCV"""
    img_data = base64.b64decode(b64_string)
    np_arr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)
    return img

b64_mask = model_output["predictions"]["segmentation_mask"]
wall_mask_image = decode_base64_to_image(b64_mask)

if wall_mask_image is None:
    raise ValueError("Lỗi: Không thể giải mã chuỗi base64 thành ảnh. Hãy kiểm tra lại file JSON.")

wall_mask_image = np.where(wall_mask_image > 0, 255, 0).astype(np.uint8)

kernel_h = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 1))
horizontal_mask = cv2.morphologyEx(wall_mask_image, cv2.MORPH_OPEN, kernel_h)

kernel_v = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 25))
vertical_mask = cv2.morphologyEx(wall_mask_image, cv2.MORPH_OPEN, kernel_v)

hv_mask = cv2.bitwise_or(horizontal_mask, vertical_mask)
kernel_dilate = np.ones((5, 5), np.uint8)
hv_mask_dilated = cv2.dilate(hv_mask, kernel_dilate, iterations=1)

diagonal_mask = cv2.subtract(wall_mask_image, hv_mask_dilated)
kernel_diag = np.ones((3, 3), np.uint8)
diagonal_mask = cv2.morphologyEx(diagonal_mask, cv2.MORPH_OPEN, kernel_diag)

wall_vectors = []      
diagonal_vectors = []  

vector_visualization = np.zeros((wall_mask_image.shape[0], wall_mask_image.shape[1], 3), dtype=np.uint8)

contours_h, _ = cv2.findContours(horizontal_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
for cnt in contours_h:
    x, y, w, h = cv2.boundingRect(cnt)
    if w > 15:  
        wall_vectors.append({"type": "horizontal", "x": x, "y": y, "width": w, "height": h})
        cv2.rectangle(vector_visualization, (x, y), (x + w, y + h), (0, 255, 0), -1)

contours_v, _ = cv2.findContours(vertical_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
for cnt in contours_v:
    x, y, w, h = cv2.boundingRect(cnt)
    if h > 15:  
        wall_vectors.append({"type": "vertical", "x": x, "y": y, "width": w, "height": h})
        cv2.rectangle(vector_visualization, (x, y), (x + w, y + h), (0, 0, 255), -1)

contours_d, _ = cv2.findContours(diagonal_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
for cnt in contours_d:
    if cv2.contourArea(cnt) > 200:
        rect = cv2.minAreaRect(cnt)
        box = cv2.boxPoints(rect)
        box = np.int32(box) 
        
        diagonal_vectors.append({
            "type": "diagonal",
            "center": [float(rect[0][0]), float(rect[0][1])], 
            "dimensions": [float(rect[1][0]), float(rect[1][1])],
            "angle": float(rect[2]),
            "corners": box.tolist()
        })
        cv2.drawContours(vector_visualization, [box], 0, (255, 0, 0), -1)

horizontals = [v for v in wall_vectors if v['type'] == 'horizontal']
verticals = [v for v in wall_vectors if v['type'] == 'vertical']

def align_and_unify_thickness(walls, is_horizontal, tolerance=15):
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
            del w['center_axis']

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
            if hy1 <= vy1 <= hy2: 
                vy1 = hy2
            if hy1 <= vy2 <= hy2: 
                vy2 = hy1

    new_height = vy2 - vy1
    if new_height > 5:
        v['y'] = int(vy1)
        v['height'] = int(new_height)
        final_verticals.append(v)

final_vectors = horizontals + final_verticals + diagonal_vectors

optimized_canvas = np.zeros_like(vector_visualization)

for h in horizontals:
    cv2.rectangle(optimized_canvas, (h['x'], h['y']), (h['x'] + h['width'], h['y'] + h['height']), (0, 255, 0), -1)
for v in final_verticals:
    cv2.rectangle(optimized_canvas, (v['x'], v['y']), (v['x'] + v['width'], v['y'] + v['height']), (0, 0, 255), -1)
for d in diagonal_vectors:
    box = np.array(d['corners'])
    cv2.drawContours(optimized_canvas, [box], 0, (255, 0, 0), -1)

cv2.imshow("1. Raw Extracted Vectors", vector_visualization)
cv2.imshow("2. Optimized Vector Walls (With Diagonals)", optimized_canvas)
cv2.waitKey(0)
cv2.destroyAllWindows()

floor_plan_data = {
    "version": "1.0",
    "metadata": {
        "description": "Vectorized wall layout including orthogonal and diagonal walls"
    },
    "layout": {
        "walls": final_vectors
    }
}

output_filename = "floor_plan_vectors.json"
with open(output_filename, 'w', encoding='utf-8') as f:
    json.dump(floor_plan_data, f, indent=4, ensure_ascii=False)

print(f"Đã lưu thành công bản vẽ số vào file: {output_filename}")