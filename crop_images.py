import cv2
import numpy as np
import os
import glob

def crop_white_margins(img):
    """
    Xóa các khoảng trắng thừa xung quanh icon.
    Giữ lại phần chứa nội dung nét vẽ.
    """
    # Xử lý kênh alpha nếu ảnh là PNG trong suốt
    if len(img.shape) == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3]
        mask = alpha > 0
    else:
        # Chuyển sang ảnh xám và tìm các pixel không phải màu trắng tinh (nét vẽ)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Nét vẽ màu đen hoặc xám sẽ có giá trị nhỏ hơn 250
        mask = gray < 250

    coords = np.column_stack(np.where(mask))
    
    # Nếu ảnh trắng tinh không có nét vẽ nào, trả về ảnh gốc
    if coords.size == 0:
        return img
        
    # Lấy tọa độ bounding box để gọt viền
    y_min, x_min = coords.min(axis=0)
    y_max, x_max = coords.max(axis=0) + 1 # +1 để bao gồm cả pixel ở viền
    
    return img[y_min:y_max, x_min:x_max]

def preprocess_images(input_dir, output_dir):
    # Tạo thư mục đầu ra nếu chưa có
    os.makedirs(output_dir, exist_ok=True)
    
    image_paths = glob.glob(os.path.join(input_dir, '*.*'))
    if not image_paths:
        print(f"Không tìm thấy ảnh nào trong thư mục: {input_dir}")
        return

    print(f"Tìm thấy {len(image_paths)} ảnh. Đang tiến hành gọt viền...")

    for path in image_paths:
        filename = os.path.basename(path)
        
        # Sử dụng IMREAD_UNCHANGED để giữ nguyên cấu trúc ảnh (kể cả kênh trong suốt)
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)

        if img is None:
            print(f"Lỗi: Không thể đọc được ảnh {filename}")
            continue

        # Thực hiện cắt viền
        cropped_img = crop_white_margins(img)

        # Lưu ảnh đã cắt vào thư mục mới
        output_path = os.path.join(output_dir, filename)
        cv2.imwrite(output_path, cropped_img)
        print(f"Đã xử lý xong: {filename}")

    print(f"\n[HOÀN TẤT] Toàn bộ ảnh đã được gọt viền và lưu tại:\n=> {output_dir}")

# Đường dẫn của bạn
input_directory = r'D:\Floor plan reconstruction\images'
output_directory = r'D:\Floor plan reconstruction\image_after_processing'

# Chạy hàm
preprocess_images(input_directory, output_directory)