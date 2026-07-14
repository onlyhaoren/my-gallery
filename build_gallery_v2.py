import os
import shutil
from PIL import Image

# 1. 定义文件夹路径
RAW_DIR = "./raw_photos"
SITE_DIR = "./site"
IMAGES_DIR = "./site/images"
ORIGINALS_DIR = "./site/originals"

# 确保文件夹存在
for folder in [RAW_DIR, SITE_DIR, IMAGES_DIR, ORIGINALS_DIR]:
    os.makedirs(folder, exist_ok=True)

# 2. 处理图片
supported_extensions = ('.png', '.jpg', '.jpeg', '.webp')
images_data = []

print("开始扫描图片...")
new_count = 0
skip_count = 0

# 获取 raw_photos 目录下的所有文件并排序（可以按名称排序，保证网页顺序一致）
files = sorted(os.listdir(RAW_DIR))

for filename in files:
    if filename.lower().endswith(supported_extensions):
        base_name, ext = os.path.splitext(filename)
        raw_path = os.path.join(RAW_DIR, filename)
        
        # 定义输出路径
        webp_filename = f"{base_name}.webp"
        webp_path = os.path.join(IMAGES_DIR, webp_filename)
        original_dest_path = os.path.join(ORIGINALS_DIR, filename)
        
        # 💡 核心改动：检查该图片是否已经处理过
        if os.path.exists(webp_path) and os.path.exists(original_dest_path):
            # 如果缩略图和原图都存在，直接记录到网页数据中，跳过耗时的压缩和复制步骤
            images_data.append({
                "webp": f"images/{webp_filename}",
                "original": f"originals/{filename}",
                "title": base_name
            })
            skip_count += 1
            continue
            
        # A. 压缩并保存为 WebP (网页展示用)
        try:
            with Image.open(raw_path) as img:
                img.save(webp_path, "WEBP", quality=80)
        except Exception as e:
            print(f"❌ 压缩失败 {filename}: {e}")
            continue
            
        # B. 复制无损原图 (下载用)
        shutil.copy2(raw_path, original_dest_path)
        
        # 记录新图片信息
        images_data.append({
            "webp": f"images/{webp_filename}",
            "original": f"originals/{filename}",
            "title": base_name
        })
        print(f" ✨ 成功处理新图片: {filename}")
        new_count += 1

print(f"扫描完毕！本次共跳过已存在图片 {skip_count} 张，成功处理新图片 {new_count} 张。")

# 3. 生成精美的 HTML 页面
html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>haorenyige.top - 我的 AI 视觉工坊</title>
    <style>
        :root {{
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --text-muted: #94a3b8;
            --accent-color: #3b82f6;
            --accent-hover: #2563eb;
        }}
        
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        
        body {{
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            padding: 40px 20px;
        }}

        header {{
            text-align: center;
            max-width: 800px;
            margin: 0 auto 50px auto;
        }}

        header h1 {{
            font-size: 2.5rem;
            margin-bottom: 15px;
            background: linear-gradient(to right, #3b82f6, #8b5cf6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .my-intro {{
            font-size: 1.1rem;
            color: var(--text-muted);
            line-height: 1.8;
        }}

        .my-intro p {{
            margin-bottom: 8px;
        }}

        /* 网格布局 */
        .gallery-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 25px;
            max-width: 1400px;
            margin: 0 auto;
        }}

        .card {{
            background-color: var(--card-bg);
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            display: flex;
            flex-direction: column;
        }}

        .card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 30px rgba(59, 130, 246, 0.2);
        }}

        .img-container {{
            position: relative;
            width: 100%;
            padding-top: 100%; /* 1:1 正方形 */
            overflow: hidden;
            cursor: zoom-in;
        }}

        .img-container img {{
            position: absolute;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            object-fit: cover;
            transition: transform 0.5s ease;
        }}

        .card:hover .img-container img {{
            transform: scale(1.05);
        }}

        .card-info {{
            padding: 15px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: auto;
        }}

        .card-title {{
            font-size: 1rem;
            font-weight: 600;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

        /* 下载按钮 */
        .download-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            background-color: var(--accent-color);
            color: white;
            text-decoration: none;
            padding: 10px;
            border-radius: 8px;
            font-weight: 500;
            font-size: 0.9rem;
            transition: background 0.2s;
        }}

        .download-btn:hover {{
            background-color: var(--accent-hover);
        }}

        /* 灯箱 (Lightbox) */
        .lightbox {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100vw;
            height: 100vh;
            background-color: rgba(15, 23, 42, 0.95);
            display: none;
            justify-content: center;
            align-items: center;
            z-index: 1000;
            cursor: zoom-out;
        }}

        .lightbox img {{
            max-width: 90%;
            max-height: 90%;
            object-fit: contain;
            border-radius: 4px;
            box-shadow: 0 0 30px rgba(0,0,0,0.5);
        }}
    </style>
</head>
<body>

    <header>
        <h1>好人之家</h1>
        <div class="my-intro">
            <p>随便看看吧~</p>
            <p><strong>点击下方按钮下载原图。</strong></p>
        </div>
    </header>

    <div class="gallery-grid">
"""

# 填充所有图片（包括跳过的和新处理的）
for img in images_data:
    html_content += f"""
        <div class="card">
            <div class="img-container" onclick="openLightbox('{img['webp']}')">
                <img src="{img['webp']}" alt="{img['title']}" loading="lazy">
            </div>
            <div class="card-info">
                <div class="card-title" title="{img['title']}">{img['title']}</div>
                <a href="{img['original']}" download class="download-btn">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                    下载原图
                </a>
            </div>
        </div>
    """

html_content += """
    </div>

    <div id="lightbox" class="lightbox" onclick="closeLightbox()">
        <img id="lightbox-img" src="" alt="预览">
    </div>

    <script>
        function openLightbox(src) {
            document.getElementById('lightbox-img').src = src;
            document.getElementById('lightbox').style.display = 'flex';
        }
        function closeLightbox() {
            document.getElementById('lightbox').style.display = 'none';
        }
    </script>
</body>
</html>
"""

# 写入 HTML 文件
with open(f"{SITE_DIR}/index.html", "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"恭喜！网页重新生成成功。当前网页共展示了 {len(images_data)} 张作品。")