import os
import json
import matplotlib.pyplot as plt
from collections import Counter

# 1. Cấu hình đường dẫn
folder_path = r"D:\Web\each_50_models_output"
MIN_COUNT = 10  # Ngưỡng lọc: chỉ hiện nếu số lượng >= 10

object_counter = Counter()
file_count = 0

print("Đang xử lý dữ liệu...")

# 2. Đọc và đếm
if os.path.exists(folder_path):
    for filename in os.listdir(folder_path):
        if filename.endswith(".json"):
            file_path = os.path.join(folder_path, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    obj_type = data.get("object", "Unknown")
                    object_counter[obj_type] += 1
                    file_count += 1
            except Exception as e:
                # print(f"Lỗi file {filename}: {e}") # Bỏ comment nếu muốn xem lỗi chi tiết
                pass
    print(f"Đã xử lý xong {file_count} file JSON.")
else:
    print("Đường dẫn không tồn tại.")
    exit()

# 3. Lọc và Sắp xếp dữ liệu
# Chỉ lấy những object có số lượng >= MIN_COUNT
filtered_data = {k: v for k, v in object_counter.items() if v >= MIN_COUNT}

# Sắp xếp giảm dần theo số lượng
sorted_data = sorted(filtered_data.items(), key=lambda item: item[1], reverse=True)

if not sorted_data:
    print(f"Không có object nào có số lượng >= {MIN_COUNT}.")
    exit()

objects = [item[0] for item in sorted_data]
counts = [item[1] for item in sorted_data]

# 4. Vẽ biểu đồ
plt.figure(figsize=(14, 7))  # Tăng kích thước chút cho rộng rãi
bars = plt.bar(objects, counts, color='#4CAF50') # Đổi màu xanh lá cho dịu mắt

plt.xlabel('Loại Object', fontsize=12)
plt.ylabel('Số lượng', fontsize=12)
plt.title(f'Thống kê các loại Object (Số lượng >= {MIN_COUNT})', fontsize=14)
plt.xticks(rotation=45, ha='right', fontsize=10)
plt.grid(axis='y', linestyle='--', alpha=0.5)

# Hiển thị số lượng trên cột
for bar in bars:
    height = bar.get_height()
    plt.text(bar.get_x() + bar.get_width()/2., height,
             f'{int(height)}',
             ha='center', va='bottom')

plt.tight_layout()
plt.show()