import cv2
import numpy as np
import os
import glob
import re

def add_white_margin(img_path, padding_size=30):
    """
    Đọc ảnh, xử lý nền trong suốt (nếu có) và thêm viền trắng xung quanh.
    """
    img = cv2.imread(img_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None

    # 1. Xử lý nền trong suốt thành nền trắng (để không bị lỗi đen nền khi viền)
    if len(img.shape) == 3 and img.shape[2] == 4:
        # Tạo một bức ảnh toàn màu trắng có cùng kích thước
        white_bg = np.ones((img.shape[0], img.shape[1], 3), dtype=np.uint8) * 255
        alpha_channel = img[:, :, 3] / 255.0
        
        # Đè ảnh có kênh alpha lên nền trắng
        for c in range(3):
            white_bg[:, :, c] = (alpha_channel * img[:, :, c] + (1 - alpha_channel) * white_bg[:, :, c])
        img = white_bg
    elif len(img.shape) == 2: # Nếu là ảnh xám
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

    # 2. Thêm khoảng trắng ở 4 viền
    # Hàm copyMakeBorder sinh ra để làm việc này
    padded_img = cv2.copyMakeBorder(
        img,
        top=padding_size, 
        bottom=padding_size, 
        left=padding_size, 
        right=padding_size,
        borderType=cv2.BORDER_CONSTANT,
        value=[255, 255, 255] # Mã màu BGR của màu Trắng
    )
    
    return padded_img

def prepare_classification_dataset(img_dir, output_dir, padding=30):
    # Tạo thư mục gốc chứa dataset
    os.makedirs(output_dir, exist_ok=True)

    icon_paths = glob.glob(os.path.join(img_dir, '*.*'))
    if not icon_paths:
        print(f"Không tìm thấy ảnh nào trong {img_dir}!")
        return

    print("Bắt đầu xử lý và phân loại ảnh...")
    success_count = 0

    for path in icon_paths:
        filename = os.path.basename(path).lower()
        name_without_ext = os.path.splitext(filename)[0]
        
        # Dùng Regex lấy phần chữ cái làm tên Class (giống y hệt code cũ)
        match = re.match(r"([a-z]+)", name_without_ext)
        class_name = match.group(1) if match else "unknown"
        
        # Tạo thư mục mang tên Class đó (VD: output_dir/bed/)
        class_dir = os.path.join(output_dir, class_name)
        os.makedirs(class_dir, exist_ok=True)
        
        # Xử lý thêm viền trắng
        processed_img = add_white_margin(path, padding_size=padding)
        
        if processed_img is not None:
            # Lưu ảnh vào đúng thư mục của nó. Chuyển đuôi sang .jpg
            out_filename = f"{name_without_ext}.jpg"
            out_path = os.path.join(class_dir, out_filename)
            
            cv2.imwrite(out_path, processed_img)
            success_count += 1

    print(f"\n[HOÀN THÀNH] Đã xử lý thành công {success_count} ảnh!")
    print(f"Dữ liệu được lưu gọn gàng tại: {output_dir}")

# ĐƯỜNG DẪN CỦA BẠN
input_directory = r'D:\Floor plan reconstruction\image_after_processing'
output_directory = r'D:\Floor plan reconstruction\classification_dataset'

# Chạy hàm với độ dày viền trắng là 30 pixel (Bạn có thể đổi số này)
prepare_classification_dataset(input_directory, output_directory, padding=15)