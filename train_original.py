import cv2
import numpy as np
import os
import random
import glob
import yaml
import re

def crop_white_margins(img):
    if len(img.shape) == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3]
        mask = alpha > 0
    else:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mask = gray < 250

    coords = np.column_stack(np.where(mask))
    if coords.size == 0:
        return img
        
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0) + 1
    
    return img[y_min:y_max, x_min:x_max]

def augment_icon(icon_path):
    icon = cv2.imread(icon_path, cv2.IMREAD_UNCHANGED)
    if icon is None:
        return None

    # 1. SCALE
    scale = random.uniform(1.2, 2.5) # Giảm scale một chút để tránh ảnh quá bự
    new_w = int(icon.shape[1] * scale)
    new_h = int(icon.shape[0] * scale)
    icon = cv2.resize(icon, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    # 2. THICKNESS
    thickness_choice = random.choices(
        ['normal', 'thicker', 'thinner'], 
        weights=[0.5, 0.4, 0.1], 
        k=1
    )[0]

    if thickness_choice != 'normal':
        kernel = np.ones((2, 2), np.uint8)
        if thickness_choice == 'thicker':
            icon = cv2.erode(icon, kernel, iterations=1)
        elif thickness_choice == 'thinner':
            thinned_icon = cv2.dilate(icon, kernel, iterations=1)
            # Fix lỗi addWeighted cho ảnh 4 kênh màu
            if icon.shape[2] == 4:
                icon[:,:,:3] = cv2.addWeighted(icon[:,:,:3], 0.7, thinned_icon[:,:,:3], 0.3, 0)
            else:
                icon = cv2.addWeighted(icon, 0.7, thinned_icon, 0.3, 0)

    filename = os.path.basename(icon_path).lower()

    # 3. ROTATE
    if "table" in filename or "sofa" in filename:
        angle = random.uniform(0, 360)
        (h, w) = icon.shape[:2]
        (cX, cY) = (w // 2, h // 2)
        
        M = cv2.getRotationMatrix2D((cX, cY), angle, 1.0)
        cos = np.abs(M[0, 0])
        sin = np.abs(M[0, 1])
        nW = int((h * sin) + (w * cos))
        nH = int((h * cos) + (w * sin))
        
        M[0, 2] += (nW / 2) - cX
        M[1, 2] += (nH / 2) - cY
        
        if len(icon.shape) == 3 and icon.shape[2] == 4:
            border_val = (255, 255, 255, 0)
        else:
            border_val = (255, 255, 255)
            
        icon = cv2.warpAffine(icon, M, (nW, nH), borderMode=cv2.BORDER_CONSTANT, borderValue=border_val)
        
    else:
        angles = [0, 90, 180, 270]
        angle = random.choice(angles)
        
        if angle == 90:
            icon = cv2.rotate(icon, cv2.ROTATE_90_CLOCKWISE)
        elif angle == 180:
            icon = cv2.rotate(icon, cv2.ROTATE_180)
        elif angle == 270:
            icon = cv2.rotate(icon, cv2.ROTATE_90_COUNTERCLOCKWISE)

    # 4. GỌT LẠI VIỀN KẾT THÚC
    icon = crop_white_margins(icon)

    # 5. ÉP VỀ NỀN TRẮNG 3 KÊNH MÀU ĐỂ LƯU JPG KHÔNG BỊ LỖI
    if len(icon.shape) == 3 and icon.shape[2] == 4:
        alpha_channel = icon[:, :, 3] / 255.0
        bg = np.ones((icon.shape[0], icon.shape[1], 3), dtype=np.uint8) * 255
        for c in range(3):
            bg[:, :, c] = (alpha_channel * icon[:, :, c] + (1 - alpha_channel) * bg[:, :, c])
        icon = bg

    return icon

def generate_augmented_single_dataset(img_dir, output_dir, variations_per_icon=10):
    images_out_dir = os.path.join(output_dir, 'images')
    labels_out_dir = os.path.join(output_dir, 'labels')
    os.makedirs(images_out_dir, exist_ok=True)
    os.makedirs(labels_out_dir, exist_ok=True)

    icon_paths = glob.glob(os.path.join(img_dir, '*.*'))
    if not icon_paths:
        print(f"Không tìm thấy ảnh tại {img_dir}")
        return

    # 1. Quét file và tự động gán Class ID (Xử lý tên file bathtub1 -> bathtub)
    class_map = {}
    current_id = 0
    
    for path in icon_paths:
        filename = os.path.basename(path).lower()
        name_without_ext = os.path.splitext(filename)[0]
        match = re.match(r"([a-z]+)", name_without_ext)
        class_name = match.group(1) if match else "unknown"
        
        if class_name not in class_map:
            class_map[class_name] = current_id
            current_id += 1

    print("[THÔNG TIN] Các class được phát hiện:", class_map)
    print(f"Sẽ tạo {variations_per_icon} biến thể cho mỗi icon...")

    # 2. Xử lý Augment ảnh và tạo label
    total_generated = 0
    for path in icon_paths:
        filename = os.path.basename(path)
        name_without_ext = os.path.splitext(filename.lower())[0]
        
        # Lấy class ID
        match = re.match(r"([a-z]+)", name_without_ext)
        class_name = match.group(1) if match else "unknown"
        class_id = class_map[class_name]

        # Tạo N biến thể cho mỗi icon
        for i in range(variations_per_icon):
            aug_icon = augment_icon(path)
            if aug_icon is None: continue

            # Lưu ảnh
            new_filename = f"{name_without_ext}_aug_{i:03d}.jpg"
            cv2.imwrite(os.path.join(images_out_dir, new_filename), aug_icon)

            # Tạo label YOLO bao trọn ảnh
            label_filename = f"{name_without_ext}_aug_{i:03d}.txt"
            with open(os.path.join(labels_out_dir, label_filename), 'w') as f:
                f.write(f"{class_id} 0.500000 0.500000 1.000000 1.000000")
            
            total_generated += 1

    # 3. Tạo file data.yaml
    yaml_content = {
        'train': 'images', 
        'val': 'images', 
        'nc': len(class_map), 
        'names': list(class_map.keys())
    }
    with open(os.path.join(output_dir, 'data.yaml'), 'w') as f:
        yaml.dump(yaml_content, f, sort_keys=False)

    print(f"\n[HOÀN THÀNH] Đã tạo tổng cộng {total_generated} ảnh tại: {output_dir}")

# ĐƯỜNG DẪN CỦA BẠN
input_dir = r'D:\Floor plan reconstruction\image_after_processing'
output_dir = r'D:\Floor plan reconstruction\results_aug_icons'

# Sinh ra 10 biến thể cho mỗi icon gốc (nếu có 100 icon gốc -> 1000 ảnh train)
generate_augmented_single_dataset(input_dir, output_dir, variations_per_icon=10)