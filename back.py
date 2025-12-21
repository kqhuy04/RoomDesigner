import os
import json
import time
import glob
from google import genai
from dotenv import load_dotenv

# Load .env
load_dotenv()
GEMINI_API_KEY = os.getenv("ROUTE_4")

# Cấu hình đường dẫn
INPUT_DIR = r"D:\Web\each_50_models"
OUTPUT_DIR = r"D:\Web\each_50_models_output" # Tạo thư mục con để lưu json cho gọn

# Tạo thư mục output nếu chưa có
os.makedirs(OUTPUT_DIR, exist_ok=True)

PROMPT = """
Analyze this 3D model preview image.
Extract and describe:
- object: Only one general name (e.g., bed, table, chair, stair, fan, television). Just one word or short phrase.
- description: A general description of the object (100-200 words).
- color: List of main colors in the object (e.g., ['red', 'yellow']).
- appropriate_room: Suitable rooms to place it (e.g., ['livingroom', 'bedroom']). Can be multiple.
- style: The design style (e.g., retro, japan, vietnam, western).
- material: Main materials (e.g., wood, metal, glass).
- size_category: Estimated size (e.g., small, medium, large).
- usage: Primary usage (e.g., functional, decorative, storage).
- mood: Atmosphere or vibe (e.g., warm, cool, vibrant, minimalist).

Return ONLY JSON format like this example:
{
  "object": "bottle",
  "description": "This is a simple yellow bottle on a red table...",
  "color": ["yellow", "red"],
  "appropriate_room": ["kitchen", "diningroom"],
  "style": "modern",
  "material": "plastic",
  "size_category": "small",
  "usage": "decorative",
  "mood": "vibrant"
}
"""

def clean_json_string(text):
    """Làm sạch chuỗi JSON trả về từ Gemini (loại bỏ markdown ```json)"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def process_single_image(client, image_path, max_retries=5):
    """Gửi ảnh lên Gemini với cơ chế thử lại khi lỗi"""
    filename = os.path.basename(image_path)
    print(f"\n--- Đang xử lý: {filename} ---")

    attempt = 0
    wait_time = 2 # Giây chờ ban đầu
    
    while attempt < max_retries:
        try:
            # Upload file (Gemini 2.0 Flash xử lý nhanh nên upload trực tiếp mỗi lần hoặc dùng cache nếu muốn 
            # tối ưu, 
            # ở đây dùng upload trực tiếp cho đơn giản logic)
            my_file = client.files.upload(file=image_path)
            
            # Generate content
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[my_file, PROMPT]
            )
            
            raw_text = response.text
            cleaned_text = clean_json_string(raw_text)
            
            # Parse JSON
            data = json.loads(cleaned_text)
            
            # Trả về kết quả thành công
            return data
            
        except Exception as e:
            attempt += 1
            print(f"Lỗi (Lần {attempt}/{max_retries}): {str(e)}")
            
            if attempt < max_retries:
                print(f"Đang đợi {wait_time}s trước khi thử lại...")
                time.sleep(wait_time)
                wait_time *= 2 # Exponential backoff (đợi lâu hơn sau mỗi lần lỗi: 2s, 4s, 8s...)
            else:
                print(f"Đã thử {max_retries} lần nhưng thất bại. Bỏ qua ảnh này.")
                return None

def save_json(data, image_filename):
    """Lưu kết quả ra file JSON"""
    base_name = os.path.splitext(image_filename)[0]
    json_filename = f"{base_name}.json"
    save_path = os.path.join(OUTPUT_DIR, json_filename)
    
    with open(save_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
    print(f"Đã lưu: {save_path}")

def main():
    # Khởi tạo client 1 lần
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Lỗi khởi tạo Client: {e}")
        return

    # Lấy danh sách ảnh (jpg, jpeg, png)
    image_extensions = ['*.jpg']
    image_files = []
    for ext in image_extensions:
        image_files.extend(glob.glob(os.path.join(INPUT_DIR, ext)))
    
    if not image_files:
        print(f"Không tìm thấy ảnh nào trong {INPUT_DIR}")
        return
    image_files = sorted(image_files)[::-1]  # đảo ngược danh sách
    print(f"Tìm thấy {len(image_files)} ảnh. Bắt đầu xử lý...")

    for img_path in image_files:
        # Kiểm tra xem file JSON đã tồn tại chưa (để có thể chạy tiếp nếu bị ngắt quãng)
        filename = os.path.basename(img_path)
        base_name = os.path.splitext(filename)[0]
        expected_json_path = os.path.join(OUTPUT_DIR, f"{base_name}.json")
        
        if os.path.exists(expected_json_path):
            print(f"Bỏ qua {filename} (đã có JSON).")
            continue

        # Xử lý
        result = process_single_image(client, img_path)
        
        if result:
            save_json(result, filename)
        
        # Nghỉ nhẹ 1 chút giữa các ảnh thành công để tránh spam API quá gắt (tuỳ chọn)
        time.sleep(1)

if __name__ == "__main__":
    main()