import os
import shutil
import xml.etree.ElementTree as ET
import re
from pathlib import Path

# ==========================================
# 1. CẤU HÌNH NHÃN VÀ THƯ MỤC
# ==========================================
CLASS_MAPPING = {
    "Door": 0,
    "Window": 1,
    "Closet": 2,
    "CoatCloset": 2, # Gộp các loại tủ
    "Toilet": 3,
    "Sink": 4,
    "WashingMachine": 5,
    "Refrigerator": 6,
    "Shower": 7,
    "BaseCabinet": 8,
    "WallCabinet": 9
}

# ĐƯỜNG DẪN THƯ MỤC (Bạn nhớ sửa lại cho đúng máy của bạn nhé)
DATASET_ROOT = r"D:\Floor plan reconstruction\cubicasa5k\cubicasa5k" 
EXPORT_DIR = r"D:\Floor plan reconstruction\Roboflow_Export_Fixed"

# ==========================================
# 2. XỬ LÝ TOÁN HỌC & MA TRẬN AFFINE (FIX LỆCH BBOX)
# ==========================================
def parse_svg_matrix(matrix_str):
    if not matrix_str:
        return [1, 0, 0, 1, 0, 0]
    match = re.search(r'matrix\(([^)]+)\)', matrix_str)
    if match:
        # Xử lý cả dấu phẩy hoặc khoảng trắng trong chuỗi matrix
        return [float(x) for x in match.group(1).replace(',', ' ').split()]
    return [1, 0, 0, 1, 0, 0]

def apply_transform(x, y, matrix):
    a, b, c, d, e, f = matrix
    return a * x + c * y + e, b * x + d * y + f

def extract_cubicasa_fixed(svg_path):
    try:
        tree = ET.parse(svg_path)
        root = tree.getroot()
    except Exception as e:
        return [], 0, 0

    img_width = float(root.attrib.get('width', 0))
    img_height = float(root.attrib.get('height', 0))
    extracted_objects = []

    # Quét tất cả các thẻ nhóm <g> (hỗ trợ cả có namespace và không có)
    ns = {'svg': 'http://www.w3.org/2000/svg'}
    groups = root.findall('.//svg:g', ns)
    if not groups:
        groups = root.findall('.//g')

    for g in groups:
        g_class = g.attrib.get('class', '')
        g_id = g.attrib.get('id', '')
        
        label = None
        if 'FixedFurniture' in g_class:
            label = g_class.split()[-1] 
        elif g_id in ['Window', 'Door']:
            label = g_id
            
        if not label: continue

        # Lấy ma trận transform
        transform_str = g.attrib.get('transform', '')
        matrix = parse_svg_matrix(transform_str)
        
        all_x, all_y = [], []
        
        # 2.1 Quét thẻ polygon
        polys = g.findall('.//svg:polygon', ns) or g.findall('.//polygon')
        for poly in polys:
            points_str = poly.attrib.get('points', '').strip()
            if not points_str: continue
            points = [p.split(',') for p in points_str.split() if ',' in p]
            for p in points:
                try:
                    # ÁP DỤNG MA TRẬN ĐỂ TÍNH TỌA ĐỘ THỰC
                    nx, ny = apply_transform(float(p[0]), float(p[1]), matrix)
                    all_x.append(nx)
                    all_y.append(ny)
                except: pass
                
        # 2.2 Quét thẻ rect (bồn cầu, tủ thường dùng hình chữ nhật)
        rects = g.findall('.//svg:rect', ns) or g.findall('.//rect')
        for rect in rects:
            try:
                x, y = float(rect.attrib.get('x', 0)), float(rect.attrib.get('y', 0))
                w, h = float(rect.attrib.get('width', 0)), float(rect.attrib.get('height', 0))
                corners = [(x,y), (x+w,y), (x+w,y+h), (x,y+h)]
                for cx, cy in corners:
                    nx, ny = apply_transform(cx, cy, matrix)
                    all_x.append(nx)
                    all_y.append(ny)
            except: pass

        if all_x and all_y:
            extracted_objects.append({
                'label': label,
                'xmin': min(all_x), 'ymin': min(all_y),
                'xmax': max(all_x), 'ymax': max(all_y)
            })
            
    return extracted_objects, img_width, img_height

# ==========================================
# 3. CHẠY VÒNG LẶP 5000 FILE
# ==========================================
def process_full_dataset(dataset_root, export_dir):
    os.makedirs(export_dir, exist_ok=True)
    
    # Tạo sẵn file data.yaml cho Roboflow
    yaml_path = os.path.join(export_dir, "data.yaml")
    with open(yaml_path, "w") as f:
        f.write("nc: 10\nnames:\n")
        for name in CLASS_MAPPING.keys():
            if name != "CoatCloset": # Đã gộp vào Closet
                f.write(f"  - {name}\n")

    svg_files = list(Path(dataset_root).rglob('*.svg'))
    print(f"🔍 Tìm thấy {len(svg_files)} file SVG. Bắt đầu trích xuất...")
    
    count = 0
    for svg_path in svg_files:
        folder_path = svg_path.parent
        folder_category = folder_path.parent.name
        folder_id = folder_path.name
        unique_name = f"{folder_category}_{folder_id}"
        
        # Tìm ảnh đi kèm
        image_path = None
        for ext in ['*.png', '*.jpg']:
            found_images = list(folder_path.glob(ext))
            if found_images:
                image_path = found_images[0]
                break
                
        if not image_path: continue
            
        objects, img_width, img_height = extract_cubicasa_fixed(str(svg_path))
        
        if img_width == 0 or img_height == 0 or not objects:
            continue
            
        txt_output_path = os.path.join(export_dir, f"{unique_name}.txt")
        valid_objects_count = 0
        
        with open(txt_output_path, "w") as f:
            for obj in objects:
                if obj['label'] in CLASS_MAPPING:
                    class_id = CLASS_MAPPING[obj['label']]
                    
                    # Cắt bounding box nếu nó bị tràn ra ngoài ảnh
                    xmin = max(0, obj['xmin']); ymin = max(0, obj['ymin'])
                    xmax = min(img_width, obj['xmax']); ymax = min(img_height, obj['ymax'])
                    
                    # Convert sang chuẩn YOLO
                    x_center = ((xmin + xmax) / 2) / img_width
                    y_center = ((ymin + ymax) / 2) / img_height
                    width = (xmax - xmin) / img_width
                    height = (ymax - ymin) / img_height
                    
                    if width > 0 and height > 0:
                        f.write(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}\n")
                        valid_objects_count += 1
        
        # Copy ảnh nếu có dữ liệu hợp lệ
        if valid_objects_count > 0:
            img_output_path = os.path.join(export_dir, f"{unique_name}{image_path.suffix}")
            shutil.copy2(image_path, img_output_path)
            count += 1
            
            if count % 200 == 0:
                print(f"⏳ Đã xử lý xong {count} mặt bằng...")

    print(f"\n✅ HOÀN TẤT! Đã tạo ra {count} ảnh và txt.")
    print(f"👉 Hãy nén thư mục '{export_dir}' thành file ZIP và kéo thả lên Web Roboflow cho nhanh nhé!")

if __name__ == "__main__":
    process_full_dataset(DATASET_ROOT, EXPORT_DIR)