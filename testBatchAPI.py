import os
import time
import json
import glob
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Load API Key
load_dotenv()
GEMINI_API_KEY = os.getenv("ROUTE_3")
client = genai.Client(api_key=GEMINI_API_KEY)

# Cấu hình đường dẫn
INPUT_DIR = r"D:\Web\bed_previews"
OUTPUT_JSON_DIR = r"D:\Web\json_results_test" # Đổi tên folder output test cho đỡ lẫn
BATCH_INPUT_FILE = "batch_tasks_test.jsonl"

PROMPT_TEXT = """
AAnalyze this 3D model preview image.
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

def step_1_upload_images_and_prepare_jsonl():
    """
    Quét thư mục, lấy 10 ảnh đầu tiên để test.
    """
    image_paths = []
    for ext in ['*.jpg', '*.jpeg', '*.png']:
        image_paths.extend(glob.glob(os.path.join(INPUT_DIR, ext)))
    
    # --- CHỈNH SỬA QUAN TRỌNG Ở ĐÂY ---
    # Chỉ lấy 10 ảnh đầu tiên để test
    if len(image_paths) > 2:
        image_paths = image_paths[:2]
    # ----------------------------------

    print(f"--- Đang CHẠY TEST với {len(image_paths)} ảnh từ {INPUT_DIR} ---")
    
    with open(BATCH_INPUT_FILE, 'w', encoding='utf-8') as jsonl_file:
        for i, img_path in enumerate(image_paths):
            file_name = os.path.basename(img_path)
            print(f"[{i+1}/{len(image_paths)}] Uploading: {file_name} ...", end="\r")
            
            try:
                mime_type = "image/png" if file_name.lower().endswith(".png") else "image/jpeg"
                
                my_file = client.files.upload(
                    file=img_path,
                    config={'display_name': file_name}
                )
                
                entry = {
                    "custom_id": file_name, 
                    "request": {
                        "contents": [
                            {
                                "parts": [
                                    {"text": PROMPT_TEXT},
                                    {"file_data": {"mime_type": my_file.mime_type, "file_uri": my_file.uri}}
                                ]
                            }
                        ],
                        "generation_config": {
                            "response_mime_type": "application/json"
                        }
                    }
                }
                jsonl_file.write(json.dumps(entry) + "\n")
                
            except Exception as e:
                print(f"\nLỗi upload file {file_name}: {e}")

    print(f"\n--- Đã tạo xong file input test: {BATCH_INPUT_FILE} ---")
    return BATCH_INPUT_FILE
def step_2_submit_batch_job(jsonl_path):
    print("--- Đang upload file JSONL request ---")
    
    # --- SỬA LỖI TẠI ĐÂY ---
    # Thêm config={'mime_type': 'application/json'} để báo cho server biết đây là file json
    batch_input_file = client.files.upload(
        file=jsonl_path,
        config={'mime_type': 'application/json'}
    )
    # -----------------------
    
    print("--- Đang tạo Batch Job ---")
    batch_job = client.batches.create(
        model="gemini-2.5-flash-lite",
        src=batch_input_file.name,
        config={'display_name': "TEST_BATCH_10_IMAGES"} 
    )
    
    print(f"Job Created: {batch_job.name}")
    return batch_job.name

def step_3_wait_and_download(job_name):
    print(f"--- Bắt đầu theo dõi Job Test: {job_name} ---")
    
    while True:
        job = client.batches.get(name=job_name)
        # In ra số lượng request đã hoàn thành
        completed = job.batch_stats.completed_request_count if job.batch_stats else 0
        print(f"Status: {job.state} | Xong: {completed}/10", end="\r")
        
        if job.state == "JOB_STATE_SUCCEEDED":
            print(f"\nJob thành công! Đang xử lý kết quả...")
            break
        elif job.state in ["JOB_STATE_FAILED", "JOB_STATE_CANCELLED", "JOB_STATE_EXPIRED"]:
            print(f"\nJob thất bại: {job.error}")
            return
        
        time.sleep(10) # Test ít ảnh thì check nhanh hơn (10s)

    os.makedirs(OUTPUT_JSON_DIR, exist_ok=True)
    result_file_name = job.dest.file_name
    output_content = client.files.download(file=result_file_name)
    
    decoded_content = output_content.decode('utf-8')
    count_success = 0
    
    print("\n--- Kết quả chi tiết ---")
    
    for line in decoded_content.strip().split('\n'):
        try:
            item = json.loads(line)
            original_filename = item.get('custom_id', 'unknown')
            
            if 'response' in item:
                candidate = item['response']['candidates'][0]['content']['parts'][0]['text']
                final_json_data = json.loads(candidate)
                
                output_filename = f"{original_filename}.json"
                output_path = os.path.join(OUTPUT_JSON_DIR, output_filename)
                
                with open(output_path, 'w', encoding='utf-8') as f_out:
                    json.dump(final_json_data, f_out, indent=4, ensure_ascii=False)
                
                print(f"✔ Đã lưu: {output_filename}")
                count_success += 1
            else:
                print(f"✘ Lỗi request: {original_filename}")
                
        except Exception as e:
            print(f"Lỗi parse dòng: {e}")

    print(f"\n--- HOÀN TẤT TEST ---")
    print(f"Kiểm tra thư mục: {OUTPUT_JSON_DIR}")

# --- MAIN ---
if __name__ == "__main__":
    jsonl_file = step_1_upload_images_and_prepare_jsonl()
    job_name = step_2_submit_batch_job(jsonl_file)
    step_3_wait_and_download(job_name)