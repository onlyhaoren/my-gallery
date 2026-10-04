#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_gallery_v3.py

流程：扫描 raw_photos/ → 压缩为 site/images/*.webp + 复制原图到 site/originals/ → 生成 site/index.html

页面功能：
  - 自带检索（按作品名过滤，忽略空格与标点，自动高亮命中片段）
  - 结果计数 / 无结果提示 / 一键清除
  - 最新优先 · 最早优先 排序
  - 灯箱预览：左右切换、Esc 关闭、手机滑动、直接下载原图
  - 键盘：/ 聚焦搜索，← → 翻页
"""

import os
import re
import html
import shutil
import datetime

from PIL import Image

# ---------------------------------------------------------------- 路径配置
RAW_DIR = "./raw_photos"
SITE_DIR = "./site"
IMAGES_DIR = "./site/images"
ORIGINALS_DIR = "./site/originals"

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
WEBP_QUALITY = 80

for _folder in (RAW_DIR, SITE_DIR, IMAGES_DIR, ORIGINALS_DIR):
    os.makedirs(_folder, exist_ok=True)


def norm_key(text):
    """标题规范化，用于检索；必须与页面里 JS 的 norm() 保持一致。"""
    return re.sub(r"[\s_\-—·,，。.()（）\[\]【】]", "", text).lower()


# ---------------------------------------------------------------- 1. 处理图片
def scan_and_process():
    images_data = []
    new_count = 0
    skip_count = 0

    print("开始扫描图片...")

    for filename in sorted(os.listdir(RAW_DIR)):
        if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
            continue

        base_name, _ext = os.path.splitext(filename)
        raw_path = os.path.join(RAW_DIR, filename)
        mtime = os.path.getmtime(raw_path)
        date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

        webp_filename = base_name + ".webp"
        webp_path = os.path.join(IMAGES_DIR, webp_filename)
        original_dest_path = os.path.join(ORIGINALS_DIR, filename)

        # 已经处理过（压缩图与原图都在）就跳过
        if os.path.exists(webp_path) and os.path.exists(original_dest_path):
            skip_count += 1
        else:
            try:
                with Image.open(raw_path) as img:
                    img.save(webp_path, "WEBP", quality=WEBP_QUALITY)
            except Exception as e:
                print("❌ 压缩失败 {}: {}".format(filename, e))
                continue

            shutil.copy2(raw_path, original_dest_path)
            print(" ✨ 成功处理新图片: {}".format(filename))
            new_count += 1

        images_data.append({
            "webp": "images/" + webp_filename,
            "original": "originals/" + filename,
            "title": base_name,
            "mtime": mtime,
            "date": date_str,
            "key": norm_key(base_name),
        })

    # 默认最新在前
    images_data.sort(key=lambda x: x["mtime"], reverse=True)

    print("扫描完毕！本次共跳过已存在图片 {} 张，成功处理新图片 {} 张。".format(skip_count, new_count))
    return images_data


# ---------------------------------------------------------------- 2. 页面样式
CSS = r"""
:root {
    --bg-color: #0f172a;
    --card-bg: #1e293b;
    --text-color: #f8fafc;
    --text-muted: #94a3b8;
    --accent-color: #3b82f6;
    --accent-hover: #2563eb;
    --btn-bg: #334155;
    --line: #334155;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    background-color: var(--bg-color);
    color: var(--text-color);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    padding: 40px 20px 60px;
}

header {
    text-align: center;
    max-width: 800px;
    margin: 0 auto 26px auto;
}

header h1 {
    font-size: 2.5rem;
    margin-bottom: 15px;
    background: linear-gradient(to right, #3b82f6, #8b5cf6);
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}

.my-intro {
    font-size: 1.05rem;
    color: var(--text-muted);
    line-height: 1.75;
}

.my-intro p { margin-bottom: 6px; }

/* ---------------- 工具条：搜索 + 排序 ---------------- */
.toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    align-items: center;
    justify-content: center;
    max-width: 1400px;
    margin: 0 auto 14px auto;
}

.search-wrap { position: relative; display: flex; align-items: center; }

#search {
    width: min(420px, 78vw);
    padding: 11px 40px 11px 16px;
    border: 1px solid var(--line);
    border-radius: 24px;
    background: var(--card-bg);
    color: var(--text-color);
    font-size: 0.95rem;
    font-family: inherit;
    outline: none;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

#search::placeholder { color: #64748b; }

#search:focus {
    border-color: var(--accent-color);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.25);
}

#clear-search {
    position: absolute;
    right: 9px;
    top: 50%;
    transform: translateY(-50%);
    width: 24px;
    height: 24px;
    border: none;
    border-radius: 50%;
    background: var(--btn-bg);
    color: #cbd5e1;
    font-size: 0.72rem;
    line-height: 1;
    cursor: pointer;
    display: none;
}

#clear-search.show { display: block; }
#clear-search:hover { background: #475569; }

.controls { display: flex; gap: 10px; }

.sort-btn {
    background-color: var(--btn-bg);
    color: var(--text-color);
    border: none;
    padding: 9px 18px;
    border-radius: 20px;
    cursor: pointer;
    font-weight: 500;
    font-size: 0.9rem;
    font-family: inherit;
    transition: background-color 0.2s ease, box-shadow 0.2s ease;
}

.sort-btn.active, .sort-btn:hover {
    background-color: var(--accent-color);
    box-shadow: 0 0 10px rgba(59, 130, 246, 0.5);
}

.status-row {
    text-align: center;
    color: var(--text-muted);
    font-size: 0.85rem;
    margin-bottom: 26px;
    min-height: 1.2em;
}

/* ---------------- 网格 ---------------- */
.gallery-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 25px;
    max-width: 1400px;
    margin: 0 auto;
}

.card {
    background-color: var(--card-bg);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
    display: flex;
    flex-direction: column;
}

.card:hover {
    transform: translateY(-5px);
    box-shadow: 0 8px 30px rgba(59, 130, 246, 0.2);
}

.img-container {
    position: relative;
    width: 100%;
    padding-top: 100%;
    overflow: hidden;
    cursor: zoom-in;
    background: #0b1220;
}

.img-container img {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    object-fit: cover;
    transition: transform 0.5s ease;
}

.card:hover .img-container img { transform: scale(1.05); }

.card-info {
    padding: 15px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin-top: auto;
}

.card-title-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 10px;
}

.card-title {
    font-size: 1rem;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-grow: 1;
}

.card-title mark {
    background: var(--accent-color);
    color: #fff;
    border-radius: 3px;
    padding: 0 2px;
}

.card-date { font-size: 0.8rem; color: var(--text-muted); white-space: nowrap; }

.download-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    background-color: var(--accent-color);
    color: #fff;
    text-decoration: none;
    padding: 10px;
    border-radius: 8px;
    font-weight: 500;
    font-size: 0.9rem;
    transition: background-color 0.2s ease;
}

.download-btn:hover { background-color: var(--accent-hover); }

/* ---------------- 无结果 ---------------- */
.empty-state {
    display: none;
    text-align: center;
    color: var(--text-muted);
    padding: 70px 20px;
    font-size: 1rem;
}

.empty-state.show { display: block; }

/* ---------------- 灯箱 ---------------- */
.lightbox {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background-color: rgba(15, 23, 42, 0.96);
    display: none;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.lightbox.open { display: flex; }

.lightbox img {
    max-width: 90%;
    max-height: 80%;
    object-fit: contain;
    border-radius: 4px;
    box-shadow: 0 0 30px rgba(0, 0, 0, 0.5);
    cursor: zoom-out;
}

.lb-btn {
    position: absolute;
    border: none;
    cursor: pointer;
    background: rgba(255, 255, 255, 0.12);
    color: #fff;
    width: 44px;
    height: 44px;
    border-radius: 50%;
    font-size: 1.5rem;
    line-height: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: background-color 0.2s ease;
}

.lb-btn:hover { background: rgba(255, 255, 255, 0.28); }
.lb-close { top: 20px; right: 20px; font-size: 1.05rem; }
.lb-prev { left: 20px; top: 50%; transform: translateY(-50%); }
.lb-next { right: 20px; top: 50%; transform: translateY(-50%); }

.lb-bar {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    gap: 16px;
    padding: 12px 16px;
    background: rgba(15, 23, 42, 0.92);
    color: var(--text-color);
    font-size: 0.9rem;
}

.lb-bar .lb-count { color: var(--text-muted); }

.lb-bar a {
    color: #fff;
    background: var(--accent-color);
    text-decoration: none;
    padding: 7px 14px;
    border-radius: 8px;
    font-size: 0.85rem;
}

.lb-bar a:hover { background: var(--accent-hover); }

@media (max-width: 700px) {
    body { padding: 26px 12px 50px; }
    header h1 { font-size: 1.9rem; }
    .gallery-grid { gap: 14px; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); }
    .lb-prev { left: 8px; }
    .lb-next { right: 8px; }
    .lb-prev, .lb-next { width: 38px; height: 38px; font-size: 1.25rem; }
    .lightbox img { max-width: 96%; max-height: 74%; }
}
"""


# ---------------------------------------------------------------- 3. 页面脚本
JS = r"""
(function () {
    'use strict';

    var grid = document.getElementById('gallery-grid');
    var searchInput = document.getElementById('search');
    var clearBtn = document.getElementById('clear-search');
    var countEl = document.getElementById('result-count');
    var emptyEl = document.getElementById('empty-state');
    var lightbox = document.getElementById('lightbox');
    var lbImg = document.getElementById('lightbox-img');
    var lbTitle = document.getElementById('lb-title');
    var lbCount = document.getElementById('lb-count');
    var lbDownload = document.getElementById('lb-download');

    var lbIndex = -1;

    function norm(s) {
        return (s || '').toLowerCase().replace(/[\s_\-—·,，。.()（）\[\]【】]/g, '');
    }

    function allCards() {
        return Array.prototype.slice.call(grid.children);
    }

    function visibleCards() {
        return allCards().filter(function (c) { return c.style.display !== 'none'; });
    }

    function paintTitle(card, rawQuery) {
        var el = card.querySelector('.card-title');
        var raw = card.getAttribute('data-title') || '';
        if (!rawQuery) { el.textContent = raw; return; }

        var at = raw.toLowerCase().indexOf(rawQuery.toLowerCase());
        if (at < 0) { el.textContent = raw; return; }

        el.textContent = '';
        var frag = document.createDocumentFragment();
        frag.appendChild(document.createTextNode(raw.slice(0, at)));
        var mark = document.createElement('mark');
        mark.textContent = raw.substr(at, rawQuery.length);
        frag.appendChild(mark);
        frag.appendChild(document.createTextNode(raw.slice(at + rawQuery.length)));
        el.appendChild(frag);
    }

    function applyFilter() {
        var rawQuery = searchInput.value.trim();
        var q = norm(rawQuery);
        var cards = allCards();
        var hits = 0;

        cards.forEach(function (card) {
            var key = card.getAttribute('data-key') || '';
            var hit = !q || key.indexOf(q) !== -1;
            card.style.display = hit ? '' : 'none';
            if (hit) { hits += 1; }
            paintTitle(card, rawQuery);
        });

        countEl.textContent = q
            ? '找到 ' + hits + ' 张 / 共 ' + cards.length + ' 张'
            : '共 ' + cards.length + ' 张作品';

        emptyEl.classList.toggle('show', hits === 0);
        clearBtn.classList.toggle('show', rawQuery.length > 0);
    }

    function renderLightbox() {
        var vis = visibleCards();
        if (!vis.length) { window.closeLightbox(); return; }

        lbIndex = ((lbIndex % vis.length) + vis.length) % vis.length;
        var card = vis[lbIndex];
        var orig = card.getAttribute('data-orig') || '';

        lbImg.src = card.getAttribute('data-webp');
        lbTitle.textContent = card.getAttribute('data-title');
        lbCount.textContent = (lbIndex + 1) + ' / ' + vis.length;
        lbDownload.href = orig;
        lbDownload.setAttribute('download', orig.split('/').pop());
    }

    window.openLightbox = function (el) {
        var card = el && el.closest ? el.closest('.card') : null;
        if (!card) { return; }

        var vis = visibleCards();
        lbIndex = vis.indexOf(card);
        if (lbIndex < 0) { lbIndex = 0; }

        renderLightbox();
        lightbox.classList.add('open');
        document.body.style.overflow = 'hidden';
    };

    window.closeLightbox = function () {
        lightbox.classList.remove('open');
        document.body.style.overflow = '';
        lbIndex = -1;
    };

    window.navigate = function (dir) {
        if (lbIndex < 0) { return; }
        lbIndex += dir;
        renderLightbox();
    };

    window.sortGallery = function (order) {
        var cards = allCards();
        cards.sort(function (a, b) {
            var ta = parseFloat(a.getAttribute('data-time')) || 0;
            var tb = parseFloat(b.getAttribute('data-time')) || 0;
            return order === 'desc' ? tb - ta : ta - tb;
        });
        cards.forEach(function (c) { grid.appendChild(c); });

        document.getElementById('btn-desc').classList.toggle('active', order === 'desc');
        document.getElementById('btn-asc').classList.toggle('active', order === 'asc');
    };

    searchInput.addEventListener('input', applyFilter);

    clearBtn.addEventListener('click', function () {
        searchInput.value = '';
        applyFilter();
        searchInput.focus();
    });

    document.addEventListener('keydown', function (e) {
        if (lightbox.classList.contains('open')) {
            if (e.key === 'Escape') { window.closeLightbox(); }
            else if (e.key === 'ArrowLeft') { window.navigate(-1); }
            else if (e.key === 'ArrowRight') { window.navigate(1); }
            return;
        }
        if (e.key === '/' && document.activeElement !== searchInput) {
            e.preventDefault();
            searchInput.focus();
        } else if (e.key === 'Escape' && document.activeElement === searchInput) {
            searchInput.value = '';
            applyFilter();
        }
    });

    var touchX = 0;
    lightbox.addEventListener('touchstart', function (e) {
        touchX = e.touches[0].clientX;
    }, { passive: true });
    lightbox.addEventListener('touchend', function (e) {
        var delta = e.changedTouches[0].clientX - touchX;
        if (Math.abs(delta) > 50) { window.navigate(delta > 0 ? -1 : 1); }
    }, { passive: true });

    applyFilter();
}());
"""

DOWNLOAD_ICON = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
    '<polyline points="7 10 12 15 17 10"></polyline>'
    '<line x1="12" y1="15" x2="12" y2="3"></line></svg>'
)

PAGE_TEMPLATE = (
    '<!DOCTYPE html>\n'
    '<html lang="zh-CN">\n'
    '<head>\n'
    '    <meta charset="UTF-8">\n'
    '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    '    <title>haorenyige.top - 我的 AI 视觉工坊</title>\n'
    '    <style>' + CSS + '</style>\n'
    '</head>\n'
    '<body>\n'
    '\n'
    '    <header>\n'
    '        <h1>好人之家</h1>\n'
    '        <div class="my-intro">\n'
    '            <p>随便看看吧~</p>\n'
    '            <p><strong>点击下方按钮下载原图。手机版点开然后下载。</strong></p>\n'
    '            <p>站点在国外，网络波动大，点开下载较慢，请耐心等待~</p>\n'
    '            <p>绝对不是因为想省钱才买的便宜站点！（心虚）</p>\n'
    '        </div>\n'
    '    </header>\n'
    '\n'
    '    <div class="toolbar">\n'
    '        <div class="search-wrap">\n'
    '            <input type="text" id="search" autocomplete="off" spellcheck="false"\n'
    '                   placeholder="搜索作品名…  ( 按 / 快速聚焦 )">\n'
    '            <button type="button" id="clear-search" title="清除搜索">✕</button>\n'
    '        </div>\n'
    '        <div class="controls">\n'
    '            <button id="btn-desc" class="sort-btn active" type="button" onclick="sortGallery(\'desc\')">📅 最新优先</button>\n'
    '            <button id="btn-asc" class="sort-btn" type="button" onclick="sortGallery(\'asc\')">📅 最早优先</button>\n'
    '        </div>\n'
    '    </div>\n'
    '\n'
    '    <div class="status-row"><span id="result-count">共 __TOTAL__ 张作品</span></div>\n'
    '\n'
    '    <div class="gallery-grid" id="gallery-grid">\n'
    '__CARDS__\n'
    '    </div>\n'
    '\n'
    '    <div id="empty-state" class="empty-state">没有找到匹配的作品，换个关键词试试？</div>\n'
    '\n'
    '    <div id="lightbox" class="lightbox"\n'
    '         onclick="if (event.target === this || event.target.id === \'lightbox-img\') closeLightbox()">\n'
    '        <img id="lightbox-img" src="" alt="预览">\n'
    '        <button class="lb-btn lb-close" type="button" title="关闭 (Esc)" onclick="closeLightbox()">✕</button>\n'
    '        <button class="lb-btn lb-prev" type="button" title="上一张 (←)" onclick="navigate(-1)">‹</button>\n'
    '        <button class="lb-btn lb-next" type="button" title="下一张 (→)" onclick="navigate(1)">›</button>\n'
    '        <div class="lb-bar">\n'
    '            <span id="lb-title"></span>\n'
    '            <span id="lb-count" class="lb-count"></span>\n'
    '            <a id="lb-download" href="#" download>下载原图</a>\n'
    '        </div>\n'
    '    </div>\n'
    '\n'
    '    <script>' + JS + '</script>\n'
    '</body>\n'
    '</html>\n'
)


# ---------------------------------------------------------------- 4. 渲染页面
def render_card(img):
    title = html.escape(img["title"], quote=True)
    key = html.escape(img["key"], quote=True)

    return (
        '        <div class="card" data-time="{time}" data-key="{key}" data-title="{title}"'
        ' data-webp="{webp}" data-orig="{orig}">\n'
        '            <div class="img-container" onclick="openLightbox(this)">\n'
        '                <img src="{webp}" alt="{title}" loading="lazy">\n'
        '            </div>\n'
        '            <div class="card-info">\n'
        '                <div class="card-title-row">\n'
        '                    <div class="card-title" title="{title}">{title}</div>\n'
        '                    <div class="card-date">{date}</div>\n'
        '                </div>\n'
        '                <a href="{orig}" download class="download-btn">{icon}下载原图</a>\n'
        '            </div>\n'
        '        </div>\n'
    ).format(
        time=img["mtime"],
        key=key,
        title=title,
        webp=img["webp"],
        orig=img["original"],
        date=img["date"],
        icon=DOWNLOAD_ICON,
    )


def render_page(images_data):
    cards = "".join(render_card(img) for img in images_data)
    return (
        PAGE_TEMPLATE
        .replace("__CARDS__", cards)
        .replace("__TOTAL__", str(len(images_data)))
    )


def main():
    images_data = scan_and_process()

    out_path = os.path.join(SITE_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render_page(images_data))

    print("恭喜！网页重新生成成功。当前网页共展示了 {} 张作品。".format(len(images_data)))


if __name__ == "__main__":
    main()
