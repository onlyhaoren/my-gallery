#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_gallery_v3.py

流程：扫描 raw_photos/ → 压缩为 site/images/*.webp + 生成 site/thumbs/*.webp 方形缩略图
      + 复制原图到 site/originals/ → 生成 site/index.html

页面功能：
  - 自带检索（按作品名过滤，忽略空格与标点，自动高亮命中片段）
  - 系列标签 chip 筛选（从文件名自动推导，可多选，与检索叠加生效）
  - 缩略图 + 真懒加载（列表只加载 560px 缩略图，点开才取大图）
  - 访问统计埋点：页面加载记 1 次访问，点「下载原图」记 1 次下载
    （上报接口见 worker.js，取数用 stats/pull_stats.py）
  - 结果计数 / 无结果提示 / 一键清除
  - 最新优先 · 最早优先 排序
  - 灯箱预览：左右切换、Esc 关闭、手机滑动、直接下载原图
  - 键盘：/ 聚焦搜索，← → 翻页

常用命令：
  python build_gallery_v3.py                                  # 正式版 → site/index.html
  python build_gallery_v3.py --out site/beta/index.html --beta # 预览版 → /beta/，不动线上首页
"""

import os
import re
import html
import shutil
import argparse
import datetime
import urllib.parse
from collections import Counter

from PIL import Image, ImageOps

# ---------------------------------------------------------------- 路径配置
RAW_DIR = "./raw_photos"
SITE_DIR = "./site"
IMAGES_DIR = "./site/images"
THUMBS_DIR = "./site/thumbs"
ORIGINALS_DIR = "./site/originals"

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")

WEBP_QUALITY = 80        # 大图（灯箱用）
THUMB_SIZE = 560         # 缩略图边长（正方形中心裁切）
THUMB_QUALITY = 72       # 缩略图画质
MIN_CHIP_COUNT = 2       # 至少几张才配变成系列标签
CHIP_COLLAPSE_AT = 20    # chip 超过这个数量就默认折叠

try:
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:      # Pillow < 9.1
    RESAMPLE = Image.LANCZOS

for _folder in (RAW_DIR, SITE_DIR, IMAGES_DIR, THUMBS_DIR, ORIGINALS_DIR):
    os.makedirs(_folder, exist_ok=True)


def norm_key(text):
    """标题规范化，用于检索；必须与页面里 JS 的 norm() 保持一致。"""
    return re.sub(r"[\s_\-—·,，。.()（）\[\]【】]", "", text).lower()


# ---------------------------------------------------------------- 系列名推导
# 依次尝试，命中即返回。想调分组规则改这里就行。
SERIES_PATTERNS = [
    re.compile(r"^(?P<n>.+?)\s*[（(]\s*\d+\s*[)）]\s*$"),   # 旗袍 (3) / 旗袍（3）
    re.compile(r"^(?P<n>.+?)__\d+_$"),                       # qingchuan__01145_
    re.compile(r"^(?P<n>.+?)_\d+_$"),                        # 酒吞_00389_
    re.compile(r"^(?P<n>[^\d]+?)\s*\d+$"),                   # 外冷内？2 / 打翻外卖1
]


def series_of(title):
    """从作品名推导所属系列；推不出来就返回自己（即独立单张）。"""
    name = title.strip()
    # 「大与小 (1)_副本」这类先剥掉副本后缀
    name = re.sub(r"[_\-]?\s*副本\s*$", "", name).strip() or name
    for pat in SERIES_PATTERNS:
        m = pat.match(name)
        if m:
            got = m.group("n").strip(" _-—·")
            if got:
                return got
    return name


# ---------------------------------------------------------------- 1. 处理图片
def make_thumb(src_path, dst_path):
    """生成正方形中心裁切缩略图——与卡片 1:1 裁切显示效果一致，但体积小得多。"""
    with Image.open(src_path) as im:
        im = ImageOps.exif_transpose(im)
        im = ImageOps.fit(im, (THUMB_SIZE, THUMB_SIZE), RESAMPLE)
        im.save(dst_path, "WEBP", quality=THUMB_QUALITY, method=5)


def scan_and_process(want_thumbs=True):
    images_data = []
    new_count = 0
    skip_count = 0
    fail_count = 0

    print("开始扫描图片...")

    for filename in sorted(os.listdir(RAW_DIR)):
        if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
            continue

        base_name, _ext = os.path.splitext(filename)
        raw_path = os.path.join(RAW_DIR, filename)
        mtime = os.path.getmtime(raw_path)
        date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

        webp_path = os.path.join(IMAGES_DIR, base_name + ".webp")
        thumb_path = os.path.join(THUMBS_DIR, base_name + ".webp")
        original_dest_path = os.path.join(ORIGINALS_DIR, filename)

        need_thumb = want_thumbs and not os.path.exists(thumb_path)
        all_ready = (os.path.exists(webp_path)
                     and os.path.exists(original_dest_path)
                     and not need_thumb)

        if all_ready:
            skip_count += 1
        else:
            try:
                if not os.path.exists(webp_path):
                    with Image.open(raw_path) as img:
                        img.save(webp_path, "WEBP", quality=WEBP_QUALITY)
                if not os.path.exists(original_dest_path):
                    shutil.copy2(raw_path, original_dest_path)
                if need_thumb:
                    make_thumb(raw_path, thumb_path)
            except Exception as e:
                print("❌ 处理失败 {}: {}".format(filename, e))
                fail_count += 1
                continue

            print(" ✨ 成功处理新图片: {}".format(filename))
            new_count += 1

        images_data.append({
            "webp": "images/" + base_name + ".webp",
            "thumb": "thumbs/" + base_name + ".webp",
            "original": "originals/" + filename,
            "title": base_name,
            "series": series_of(base_name),
            "mtime": mtime,
            "date": date_str,
            "key": norm_key(base_name),
        })

    # 默认最新在前
    images_data.sort(key=lambda x: x["mtime"], reverse=True)

    print("扫描完毕！跳过已存在 {} 张，成功处理新图片 {} 张，失败 {} 张。".format(
        skip_count, new_count, fail_count))
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

/* ---------------- 预览版提示条 ---------------- */
.beta-banner {
    max-width: 1400px;
    margin: 0 auto 22px auto;
    padding: 12px 18px;
    border: 1px solid var(--accent-color);
    border-radius: 12px;
    background: rgba(59, 130, 246, 0.12);
    color: #bfdbfe;
    font-size: 0.9rem;
    text-align: center;
    line-height: 1.7;
}

.beta-banner a { color: #fff; text-decoration: underline; }

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

/* ---------------- 系列标签 ---------------- */
.chip-bar {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
    max-width: 1180px;
    margin: 0 auto 8px auto;
}

.chip-bar.collapsed { max-height: 76px; overflow: hidden; }
.chip-bar.collapsed.expanded { max-height: none; }

.chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--card-bg);
    color: var(--text-color);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 6px 13px;
    font-size: 0.84rem;
    font-family: inherit;
    cursor: pointer;
    transition: background-color 0.18s ease, border-color 0.18s ease;
}

.chip:hover { border-color: var(--accent-color); }

.chip.active {
    background: var(--accent-color);
    border-color: var(--accent-color);
    box-shadow: 0 0 10px rgba(59, 130, 246, 0.45);
}

.chip .n { color: var(--text-muted); font-size: 0.76rem; }
.chip.active .n { color: #dbeafe; }

.chip-toggle-wrap { text-align: center; margin-bottom: 10px; }

.chip-toggle {
    background: none;
    border: none;
    color: var(--accent-color);
    cursor: pointer;
    font-family: inherit;
    font-size: 0.84rem;
    padding: 4px 10px;
}

.chip-toggle:hover { text-decoration: underline; }

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
    .chip { padding: 5px 11px; font-size: 0.8rem; }
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
    var chipBar = document.getElementById('chip-bar');
    var chipToggle = document.getElementById('chip-toggle');
    var lightbox = document.getElementById('lightbox');
    var lbImg = document.getElementById('lightbox-img');
    var lbTitle = document.getElementById('lb-title');
    var lbCount = document.getElementById('lb-count');
    var lbDownload = document.getElementById('lb-download');

    var lbIndex = -1;
    var selectedSeries = [];

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
            var ser = card.getAttribute('data-series') || '';

            var bySearch = !q || key.indexOf(q) !== -1;
            var byChip = selectedSeries.length === 0 || selectedSeries.indexOf(ser) !== -1;
            var hit = bySearch && byChip;

            card.style.display = hit ? '' : 'none';
            if (hit) { hits += 1; }
            paintTitle(card, rawQuery);
        });

        var filtering = q.length > 0 || selectedSeries.length > 0;
        countEl.textContent = filtering
            ? '找到 ' + hits + ' 张 / 共 ' + cards.length + ' 张'
            : '共 ' + cards.length + ' 张作品';

        emptyEl.classList.toggle('show', hits === 0);
        clearBtn.classList.toggle('show', rawQuery.length > 0);
    }

    function paintChips() {
        if (!chipBar) { return; }
        var chips = chipBar.querySelectorAll('.chip');
        Array.prototype.forEach.call(chips, function (b) {
            var s = b.getAttribute('data-series');
            var active = (s === '') ? selectedSeries.length === 0
                                    : selectedSeries.indexOf(s) !== -1;
            b.classList.toggle('active', active);
        });
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

    if (chipBar) {
        chipBar.addEventListener('click', function (e) {
            var node = e.target;
            while (node && node !== chipBar && !node.classList.contains('chip')) {
                node = node.parentNode;
            }
            if (!node || node === chipBar) { return; }

            var s = node.getAttribute('data-series');
            if (!s) {
                selectedSeries = [];
            } else {
                var i = selectedSeries.indexOf(s);
                if (i === -1) { selectedSeries.push(s); }
                else { selectedSeries.splice(i, 1); }
            }
            paintChips();
            applyFilter();
        });
    }

    if (chipToggle) {
        chipToggle.addEventListener('click', function () {
            var expanded = chipBar.classList.toggle('expanded');
            chipToggle.textContent = expanded ? '▴ 收起标签' : '▾ 展开全部标签';
        });
    }

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

    paintChips();
    applyFilter();
}());
"""

# ---------------------------------------------------------------- 3b. 访问统计埋点
# 只在 --no-track / --beta 之外注入。上报接口由 worker.js 提供：
#   /api/track   写入事件（只能写，读不到任何东西）
# 拿数据请在本地跑 stats/pull_stats.py
TRACK_JS = r"""
(function () {
    'use strict';
    var EP = '/api/track';

    function send(obj) {
        try {
            var body = JSON.stringify(obj);
            if (navigator.sendBeacon) {
                navigator.sendBeacon(EP, new Blob([body], { type: 'application/json' }));
            } else {
                fetch(EP, { method: 'POST', body: body, keepalive: true,
                            headers: { 'Content-Type': 'application/json' } });
            }
        } catch (e) { /* 统计失败绝不能影响页面 */ }
    }

    // 访问量：每次加载页面记一次
    send({ e: 'view' });

    // 下载点击：卡片里的「下载原图」按钮，以及灯箱里的下载链接
    document.addEventListener('click', function (ev) {
        var node = ev.target;
        while (node && node !== document &&
               !(node.tagName === 'A' &&
                 (node.classList.contains('download-btn') || node.id === 'lb-download'))) {
            node = node.parentNode;
        }
        if (!node || node === document) { return; }

        var card = node.closest ? node.closest('.card') : null;
        var work = card ? (card.getAttribute('data-title') || '') : '';
        if (!work) {
            var t = document.getElementById('lb-title');
            work = t ? t.textContent : '';
        }
        send({ e: 'download', w: work });
    }, true);
}());
"""

DOWNLOAD_ICON = (
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
    '<polyline points="7 10 12 15 17 10"></polyline>'
    '<line x1="12" y1="15" x2="12" y2="3"></line></svg>'
)

# 内联 SVG 图标：不额外产生网络请求，也不新增文件
FAVICON_SVG = (
    "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
    "<defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'>"
    "<stop offset='0' stop-color='#3b82f6'/><stop offset='1' stop-color='#8b5cf6'/>"
    "</linearGradient></defs>"
    "<rect width='64' height='64' rx='14' fill='url(%23g)'/>"
    "<text x='32' y='46' font-size='36' font-weight='700' text-anchor='middle'"
    " font-family='PingFang SC,Microsoft YaHei,sans-serif' fill='#ffffff'>好</text>"
    "</svg>"
)

HEAD_EXTRA = (
    '    <link rel="icon" href="data:image/svg+xml,'
    + urllib.parse.quote(FAVICON_SVG, safe="")
    + '">\n'
    '    <meta name="theme-color" content="#0f172a">\n'
    '    <meta name="description" content="好人之家 · AI 视觉作品画廊，支持按作品名检索与系列筛选。">\n'
)

BETA_BANNER = (
    '<div class="beta-banner">\n'
    '        🧪 <strong>预览版</strong> · 缩略图 + 系列标签已开启 · 正式版首页未受影响 '
    '· <a href="/">返回线上版</a>\n'
    '    </div>'
)

PAGE_TEMPLATE = (
    '<!DOCTYPE html>\n'
    '<html lang="zh-CN">\n'
    '<head>\n'
    '    <meta charset="UTF-8">\n'
    '    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
    '__HEAD_EXTRA__'
    '__ROBOTS__'
    '    <title>__PAGE_TITLE__</title>\n'
    '    <style>' + CSS + '</style>\n'
    '</head>\n'
    '<body>\n'
    '\n'
    '__BANNER__'
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
    '    <div class="chip-bar" id="chip-bar">\n'
    '__CHIPS__\n'
    '    </div>\n'
    '__CHIP_TOGGLE__'
    '\n'
    '    <div class="status-row"><span id="result-count">共 __TOTAL__ 张作品</span></div>\n'
    '\n'
    '    <div class="gallery-grid" id="gallery-grid">\n'
    '__CARDS__\n'
    '    </div>\n'
    '\n'
    '    <div id="empty-state" class="empty-state">没有找到匹配的作品，换个关键词或清掉筛选试试？</div>\n'
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
    '__TRACK__'
    '</body>\n'
    '</html>\n'
)


# ---------------------------------------------------------------- 4. 渲染页面
def render_card(img, asset_base=""):
    title = html.escape(img["title"], quote=True)
    key = html.escape(img["key"], quote=True)
    series = html.escape(img["series"], quote=True)

    return (
        '        <div class="card" data-time="{time}" data-key="{key}" data-title="{title}"'
        ' data-series="{series}" data-webp="{webp}" data-orig="{orig}">\n'
        '            <div class="img-container" onclick="openLightbox(this)">\n'
        '                <img src="{thumb}" alt="{title}" width="{size}" height="{size}"'
        ' loading="lazy" decoding="async">\n'
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
        series=series,
        webp=asset_base + img["webp"],
        thumb=asset_base + img["thumb"],
        orig=asset_base + img["original"],
        date=img["date"],
        size=THUMB_SIZE,
        icon=DOWNLOAD_ICON,
    )


def build_chips(images_data):
    """统计系列，返回 [(系列名, 数量), ...]，按数量降序。"""
    counter = Counter(img["series"] for img in images_data)
    items = [(name, n) for name, n in counter.items() if n >= MIN_CHIP_COUNT]
    items.sort(key=lambda x: (-x[1], x[0]))
    return items


def render_chips(images_data):
    items = build_chips(images_data)
    parts = [
        '        <button type="button" class="chip active" data-series="">'
        '全部<span class="n">{}</span></button>'.format(len(images_data))
    ]
    for name, n in items:
        parts.append(
            '        <button type="button" class="chip" data-series="{s}">{s}'
            '<span class="n">{n}</span></button>'.format(
                s=html.escape(name, quote=True), n=n)
        )
    collapsed = len(items) > CHIP_COLLAPSE_AT
    return "\n".join(parts), collapsed, len(items)


def render_page(images_data, asset_base="", beta=False, with_chips=True,
                with_track=True,
                page_title="haorenyige.top - 我的 AI 视觉工坊"):
    cards = "".join(render_card(img, asset_base) for img in images_data)

    if with_chips:
        chips_html, collapsed, _n = render_chips(images_data)
        chip_bar_open = ('    <div class="chip-bar collapsed" id="chip-bar">'
                         if collapsed else '    <div class="chip-bar" id="chip-bar">')
        toggle_html = (
            '    <div class="chip-toggle-wrap">'
            '<button type="button" class="chip-toggle" id="chip-toggle">'
            '▾ 展开全部标签</button></div>\n'
        ) if collapsed else ''
    else:
        chips_html = ''
        chip_bar_open = '    <div class="chip-bar" id="chip-bar">'
        toggle_html = ''

    banner_html = ('    ' + BETA_BANNER + '\n') if beta else ''
    robots_html = ('    <meta name="robots" content="noindex, nofollow">\n'
                   if beta else '')
    track_html = ('    <script>' + TRACK_JS + '</script>\n') if with_track else ''

    page = PAGE_TEMPLATE
    # 先换 chip 容器（因为 __CHIP_TOGGLE__ 里含 'chip-toggle' 字样，注意替换顺序）
    page = page.replace('    <div class="chip-bar" id="chip-bar">', chip_bar_open)
    page = page.replace('__CHIPS__', chips_html)
    page = page.replace('__CHIP_TOGGLE__', toggle_html)
    page = page.replace('__BANNER__', banner_html)
    page = page.replace('__HEAD_EXTRA__', HEAD_EXTRA)
    page = page.replace('__ROBOTS__', robots_html)
    page = page.replace('__TRACK__', track_html)
    page = page.replace('__PAGE_TITLE__', html.escape(page_title))
    page = page.replace('__CARDS__', cards)
    page = page.replace('__TOTAL__', str(len(images_data)))
    return page


# ---------------------------------------------------------------- 5. 命令行
def parse_args():
    ap = argparse.ArgumentParser(description="构建图片画廊站点")
    ap.add_argument("--out", default=os.path.join(SITE_DIR, "index.html"),
                    help="输出 HTML 路径（默认 site/index.html）")
    ap.add_argument("--asset-base", default=None,
                    help="资源路径前缀，例如 / （放在子目录里预览时必须指定）")
    ap.add_argument("--beta", action="store_true",
                    help="预览版：自动改用根绝对路径、加提示条、加 noindex")
    ap.add_argument("--title", default="haorenyige.top - 我的 AI 视觉工坊")
    ap.add_argument("--no-thumbs", action="store_true", help="不生成缩略图")
    ap.add_argument("--no-chips", action="store_true", help="不生成系列标签")
    ap.add_argument("--no-track", action="store_true", help="不注入访问统计埋点")
    return ap.parse_args()


def main():
    args = parse_args()

    asset_base = args.asset_base
    if args.beta and asset_base is None:
        asset_base = "/"
    if asset_base is None:
        asset_base = ""
    if asset_base and not asset_base.endswith("/"):
        asset_base += "/"

    title = args.title
    if args.beta and "预览" not in title:
        title = title + "（预览版）"

    images_data = scan_and_process(want_thumbs=not args.no_thumbs)

    # 预览版默认不埋点，免得把预览的访问混进真实统计里
    with_track = (not args.no_track) and (not args.beta)

    out_path = args.out
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(render_page(
            images_data,
            asset_base=asset_base,
            beta=args.beta,
            with_chips=not args.no_chips,
            with_track=with_track,
            page_title=title,
        ))

    chips = build_chips(images_data)
    print("恭喜！网页重新生成成功 → {}".format(out_path))
    print("  作品 {} 张 · 系列标签 {} 个 · 资源前缀 '{}' · 访问统计 {}".format(
        len(images_data), len(chips), asset_base or "(相对路径)",
        "已注入" if with_track else "未注入"))


if __name__ == "__main__":
    main()
