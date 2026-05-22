import os
import json

JSON_BASE_DIR = "./json"

def fix_dimensions_in_json():
    print(f"Bắt đầu quét và sửa lỗi kích thước trong: {JSON_BASE_DIR}\n")
    total_fixed = 0

    # Lặp qua từng danh mục (bed, bench, sofa...)
    for category in os.listdir(JSON_BASE_DIR):
        cat_json_path = os.path.join(JSON_BASE_DIR, category)
        
        if not os.path.isdir(cat_json_path):
            continue

        print(f"--- Đang kiểm tra danh mục: {category} ---")
        
        # Lặp qua các file .json trong danh mục
        for filename in os.listdir(cat_json_path):
            if filename.endswith(".json"):
                json_path = os.path.join(cat_json_path, filename)

                try:
                    with open(json_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)

                    # Kiểm tra xem file đã có trường dimensions chưa
                    if 'dimensions' in data:
                        dims = data['dimensions']
                        w = float(dims.get('width', 0))
                        h = float(dims.get('height', 0))
                        l = float(dims.get('length', 0))

                        # Tìm cạnh dài nhất
                        max_val = max(w, h, l)

                        # Logic chuẩn hóa
                        if max_val > 500:
                            scale_factor = 0.001   # Đổi từ mm sang m
                        elif max_val > 50:
                            scale_factor = 0.01    # Đổi từ cm sang m
                        elif max_val > 20:
                            scale_factor = 0.0254  # Đổi từ inches sang m
                        elif max_val > 5:
                            scale_factor = 0.3048  # Đổi từ feet sang m
                        else:
                            scale_factor = 1.0     # Đã chuẩn hệ mét rồi, bỏ qua

                        # Nếu phát hiện sai số (cần scale)
                        if scale_factor != 1.0:
                            data['dimensions']['width'] = round(w * scale_factor, 3)
                            data['dimensions']['height'] = round(h * scale_factor, 3)
                            data['dimensions']['length'] = round(l * scale_factor, 3)
                            data['dimensions']['unit'] = "meters"

                            # Ghi đè lại file JSON
                            with open(json_path, 'w', encoding='utf-8') as f:
                                json.dump(data, f, ensure_ascii=False, indent=4)
                            
                            total_fixed += 1
                            print(f"  [Đã sửa] {filename} | Max cũ: {max_val} -> Tỷ lệ bóp: {scale_factor}")

                except Exception as e:
                    print(f"  [Lỗi đọc file] {filename}: {e}")

    print(f"\nHOÀN TẤT! Đã phát hiện và sửa thành công {total_fixed} file JSON bị sai đơn vị.")

if __name__ == "__main__":
    fix_dimensions_in_json()