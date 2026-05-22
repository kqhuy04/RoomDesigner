from icrawler.builtin import BingImageCrawler # Đổi từ Google sang Bing
import os

# Từ khóa tìm kiếm và số lượng ảnh
keyword = "floorplan image"
max_images = 100

# Tạo thư mục lưu ảnh nếu chưa có
save_dir = "downloaded_floorplans"
if not os.path.exists(save_dir):
    os.makedirs(save_dir)

print(f"Bắt đầu tải {max_images} ảnh '{keyword}' từ Bing...")

# Khởi tạo BingImageCrawler thay vì Google
bing_crawler = BingImageCrawler(
    storage={'root_dir': save_dir}
)

# Bắt đầu quá trình thu thập ảnh
bing_crawler.crawl(
    keyword=keyword, 
    max_num=max_images
)

print(f"Hoàn tất! Ảnh đã được lưu tại thư mục: {save_dir}")