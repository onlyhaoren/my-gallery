"""
generate_index.py
扫描 site/images/ 生成 images.json
"""
import json
from pathlib import Path
IMAGE_DIR = Path("./site/images")
OUTPUT = Path("./site/images.json")
images = [
    {"filename": f.name, "url": f"images/{f.name}"}
    for f in IMAGE_DIR.iterdir()
    if f.suffix.lower() in {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.avif'}
]
# 按文件名排序
images.sort(key=lambda x: x["filename"])
OUTPUT.write_text(json.dumps(images, indent=2, ensure_ascii=False), encoding='utf-8')
print(f"✅ 已生成 {OUTPUT}，共 {len(images)} 张图片")