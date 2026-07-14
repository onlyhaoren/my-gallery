let allImages = [];
let filtered = [];
let loaded = 0;
let lbIndex = -1;
const BATCH = 40;
async function init() {
    const res = await fetch('images.json');
    allImages = await res.json();
    filtered = [...allImages];
    updateCount();
    loadMore();
    // 无限滚动
    new IntersectionObserver(entries => {
        if (entries[0].isIntersecting) loadMore();
    }, { rootMargin: '400px' }).observe(document.getElementById('sentinel'));
    // 搜索
    let timer;
    document.getElementById('search').addEventListener('input', e => {
        clearTimeout(timer);
        timer = setTimeout(() => {
            const q = e.target.value.trim().toLowerCase();
            filtered = q
                ? allImages.filter(img => img.filename.toLowerCase().includes(q))
                : [...allImages];
            document.getElementById('gallery').innerHTML = '';
            loaded = 0;
            loadMore();
        }, 300);
    });
    // 键盘
    document.addEventListener('keydown', e => {
        if (lbIndex < 0) return;
        if (e.key === 'Escape') closeLightbox();
        if (e.key === 'ArrowLeft') navigate(-1);
        if (e.key === 'ArrowRight') navigate(1);
    });
    // 触摸滑动
    let touchStartX = 0;
    const lb = document.getElementById('lightbox');
    lb.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; });
    lb.addEventListener('touchend', e => {
        const diff = e.changedTouches[0].clientX - touchStartX;
        if (Math.abs(diff) > 50) navigate(diff > 0 ? -1 : 1);
    });
}
function loadMore() {
    if (loaded >= filtered.length) return;
    const gallery = document.getElementById('gallery');
    const end = Math.min(loaded + BATCH, filtered.length);
    for (let i = loaded; i < end; i++) {
        const img = filtered[i];
        const item = document.createElement('div');
        item.className = 'gallery-item';
        item.innerHTML = `<div class="ph"></div><img data-src="${img.url}" alt="${img.filename}" loading="lazy">`;
        const imgEl = item.querySelector('img');
        const ph = item.querySelector('.ph');
        new IntersectionObserver((entries, obs) => {
            if (entries[0].isIntersecting) {
                imgEl.src = imgEl.dataset.src;
                imgEl.onload = () => { imgEl.classList.add('loaded'); ph.remove(); };
                imgEl.onerror = () => { item.remove(); };
                obs.unobserve(item);
            }
        }, { rootMargin: '200px' }).observe(item);
        const idx = i;
        item.addEventListener('click', () => openLightbox(idx));
        gallery.appendChild(item);
    }
    loaded = end;
    updateCount();
}
function openLightbox(i) {
    lbIndex = i;
    document.getElementById('lb-img').src = filtered[i].url;
    document.getElementById('lb-info').textContent =
        `${filtered[i].filename}  ·  ${i + 1} / ${filtered.length}`;
    document.getElementById('lightbox').classList.add('open');
    document.body.style.overflow = 'hidden';
}
function closeLightbox() {
    document.getElementById('lightbox').classList.remove('open');
    document.body.style.overflow = '';
    lbIndex = -1;
}
function navigate(dir) {
    if (lbIndex < 0) return;
    let n = lbIndex + dir;
    if (n < 0) n = filtered.length - 1;
    if (n >= filtered.length) n = 0;
    openLightbox(n);
}
function updateCount() {
    document.getElementById('count').textContent =
        `${Math.min(loaded, filtered.length)} / ${filtered.length} 张`;
}
init();