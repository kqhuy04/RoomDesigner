import os
import json

# Đường dẫn đến thư mục dataset của bạn
dataset_dir = r"D:\Floor plan reconstruction\Roboflow_Dataset"
splits = ["train", "valid", "test"]

for split in splits:
    json_path = os.path.join(dataset_dir, split, "_annotations.coco.json")
    
    if os.path.exists(json_path):
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        # Thêm mục "info" và "licenses" giả để lừa Roboflow CLI
        if "info" not in data:
            data["info"] = {
                "year": "2024",
                "version": "1",
                "description": "CubiCasa5K Fixed",
                "contributor": "",
                "url": "",
                "date_created": ""
            }
        
        # Có thể Roboflow cũng sẽ đòi cả "licenses", ta cứ cho thêm vào cho chắc
        if "licenses" not in data:
            data["licenses"] = [{"id": 1, "url": "", "name": "Unknown"}]
            
        # Ghi đè lại file
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)
            
        print(f"Đã sửa xong file JSON trong thư mục {split.upper()}!")
    else:
        print(f"Không tìm thấy file ở {json_path}")

print("Hoàn tất! Bạn có thể chạy lại lệnh roboflow import rồi nhé.")