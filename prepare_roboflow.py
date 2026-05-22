import os
import json
import shutil

# Đường dẫn trên máy tính của bạn
base_img_dir = r"D:\Floor plan reconstruction\cubicasa5k\cubicasa5k"  
json_dir = r"D:\Floor plan reconstruction\cubicasa5k_coco"         
output_dir = r"D:\Floor plan reconstruction\Roboflow_Dataset"                 

splits = ["train", "val", "test"]

print("Bắt đầu xử lý dữ liệu...")
for split in splits:
    json_name = f"{split}_coco_pt.json"
    json_path = os.path.join(json_dir, json_name)
    
    out_split_dir = os.path.join(output_dir, split if split != 'val' else 'valid')
    os.makedirs(out_split_dir, exist_ok=True)
    
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
        
    print(f"Đang xử lý tập {split.upper()} với {len(data['images'])} ảnh...")
    
    for img in data['images']:
        raw_path_in_json = img['file_name'] 
        
        # 1. XÓA BỎ ĐƯỜNG DẪN KAGGLE BỊ DÍNH TRONG JSON
        # Nếu đường dẫn có chữ cubicasa5k/, ta chỉ cắt lấy phần đuôi phía sau
        if "cubicasa5k/" in raw_path_in_json:
            clean_path = raw_path_in_json.split("cubicasa5k/")[-1]
        else:
            clean_path = raw_path_in_json
            
        # 2. SỬA LỖI ORIGINAL THÀNH SCALED
        clean_path = clean_path.replace("F1_original.png", "F1_scaled.png")
        
        # 3. Ghép phần đuôi sạch sẽ với đường dẫn ổ D: của bạn
        old_path = os.path.join(base_img_dir, clean_path)
        
        # Tạo tên file mới phẳng hóa (vd: colorful_30_F1_scaled.png)
        new_filename = clean_path.replace('/', '_').replace('\\', '_')
        new_path = os.path.join(out_split_dir, new_filename)
        
        # Copy ảnh sang thư mục Roboflow
        if os.path.exists(old_path):
            shutil.copy(old_path, new_path)
        else:
            print(f"Cảnh báo: Không tìm thấy ảnh {old_path}")
            
        # Cập nhật lại tên file trong JSON cho chuẩn
        img['file_name'] = new_filename
        
    # Lưu file JSON mới
    new_json_path = os.path.join(out_split_dir, '_annotations.coco.json')
    with open(new_json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f)

print("Hoàn tất! Hãy kiểm tra thư mục Roboflow_Dataset.")