"""
compress.py
智能压缩策略：
  - 最长边 > 2560px  → 缩放到 2560px + 转 WebP
  - 最长边 ≤ 2560px  → 不缩放，只转 WebP（减小体积）
  - 已经是 WebP 且 ≤ 2560px → 直接复制，不处理
  - 文件体积 < 100KB → 直接复制，已经够小了
  - 自动跳过已处理的文件
"""
from PIL import Image
from pathlib import Path
import shutil
import sys
# ============ 你可以修改这些参数 ============
INPUT_DIR = Path("./images")          # 原始图片文件夹
OUTPUT_DIR = Path("./site/images")    # 输出文件夹
MAX_LONG_SIDE = 2560                  # 超过这个才缩放（像素）
WEBP_QUALITY = 82                     # WebP 质量 (推荐 75-85)
SKIP_SIZE_KB = 100                    # 小于此体积的直接复制（KB）
# ==========================================
EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tiff', '.gif', '.avif'}
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
# 已有输出文件
existing = {f.stem for f in OUTPUT_DIR.iterdir() if f.is_file()}
# 扫描输入文件
files = sorted([
    f for f in INPUT_DIR.iterdir()
    if f.is_file() and f.suffix.lower() in EXTENSIONS
])
if not files:
    print(f"❌ 在 {INPUT_DIR} 中没有找到图片文件")
    print(f"   支持的格式: {', '.join(EXTENSIONS)}")
    sys.exit(1)
print(f"扫描到 {len(files)} 张图片\n")
# 统计
stats = {
    'skip_exists': 0,      # 已处理过，跳过
    'skip_copy': 0,         # 太小 / 已是合格WebP，直接复制
    'converted': 0,         # 只转格式，未缩放
    'resized': 0,           # 缩放 + 转格式
    'failed': 0,
    'total_original': 0,
    'total_output': 0,
}
def format_size(bytes_val):
    """友好显示文件大小"""
    if bytes_val < 1024:
        return f"{bytes_val}B"
    elif bytes_val < 1024 * 1024:
        return f"{bytes_val / 1024:.0f}KB"
    else:
        return f"{bytes_val / 1024 / 1024:.1f}MB"
for f in files:
    out_path = OUTPUT_DIR / (f.stem + ".webp")
    # ---- 跳过已处理的 ----
    if f.stem in existing:
        stats['skip_exists'] += 1
        continue
    file_size = f.stat().st_size
    stats['total_original'] += file_size
    # ---- 太小的文件直接复制（无需压缩） ----
    if file_size < SKIP_SIZE_KB * 1024:
        if f.suffix.lower() == '.webp':
            shutil.copy2(f, out_path)
        else:
            # 即使很小也转 WebP 统一格式
            try:
                img = Image.open(f)
                if img.mode in ('RGBA', 'P', 'LA'):
                    img = img.convert('RGB')
                img.save(out_path, 'WEBP', quality=90)
            except Exception:
                shutil.copy2(f, OUTPUT_DIR / f.name)
                out_path = OUTPUT_DIR / f.name
        out_size = out_path.stat().st_size
        stats['total_output'] += out_size
        stats['skip_copy'] += 1
        print(f"📋 复制: {f.name} ({format_size(file_size)}) → 太小无需压缩")
        continue
    # ---- 处理图片 ----
    try:
        img = Image.open(f)
        w, h = img.size
        long_side = max(w, h)
        # 转 RGB
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        # 判断是否需要缩放
        if long_side > MAX_LONG_SIDE:
            ratio = MAX_LONG_SIDE / long_side
            new_w = int(w * ratio)
            new_h = int(h * ratio)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            action = "缩放"
            detail = f"{w}x{h} → {new_w}x{new_h}"
            stats['resized'] += 1
        else:
            action = "转换"
            detail = f"{w}x{h} 保持原尺寸"
            stats['converted'] += 1
        # 保存 WebP
        img.save(out_path, 'WEBP', quality=WEBP_QUALITY)
        out_size = out_path.stat().st_size
        stats['total_output'] += out_size
        saved_pct = (1 - out_size / file_size) * 100
        icon = "🔧" if action == "缩放" else "🔄"
        print(f"{icon} {action}: {f.name}  {detail}  "
              f"({format_size(file_size)} → {format_size(out_size)}, "
              f"{'节省' if saved_pct > 0 else '增加'} {abs(saved_pct):.0f}%)")
    except Exception as e:
        print(f"❌ 失败: {f.name} - {e}")
        stats['failed'] += 1
# ============ 打印汇总 ============
print(f"\n{'=' * 55}")
print(f"  📊 处理汇总")
print(f"{'=' * 55}")
print(f"  已跳过（之前处理过）:  {stats['skip_exists']} 张")
print(f"  直接复制（体积太小）:  {stats['skip_copy']} 张")
print(f"  仅转格式（≤{MAX_LONG_SIDE}px）: {stats['converted']} 张")
print(f"  缩放+转格式（>{MAX_LONG_SIDE}px）: {stats['resized']} 张")
print(f"  处理失败:              {stats['failed']} 张")
print(f"{'─' * 55}")
total_processed = stats['skip_copy'] + stats['converted'] + stats['resized']
total_all = total_processed + stats['skip_exists']
print(f"  图片总数:  {total_all} 张")
if stats['total_original'] > 0:
    print(f"  本次处理:  {total_processed} 张")
    print(f"  原始大小:  {format_size(stats['total_original'])}")
    print(f"  输出大小:  {format_size(stats['total_output'])}")
    saved = stats['total_original'] - stats['total_output']
    if saved > 0:
        print(f"  总共节省:  {format_size(saved)} "
              f"({saved / stats['total_original'] * 100:.0f}%)")
print(f"{'=' * 55}")
# 显示输出目录中的总文件数
out_count = len(list(OUTPUT_DIR.glob("*.*")))
out_total_size = sum(f.stat().st_size for f in OUTPUT_DIR.iterdir() if f.is_file())
print(f"\n  📁 输出目录: {OUTPUT_DIR}")
print(f"  📷 总文件数: {out_count} 张")
print(f"  💾 总占用:   {format_size(out_total_size)}")