/**
 * my-gallery 访问统计 Worker
 *
 * 两个接口：
 *   POST /api/track    写入一条事件（公开，只能写、不能读）
 *   GET  /api/export   按天导出原始事件（需要 X-Stats-Key 请求头）
 *
 * 其余所有请求原样交回静态资源，404 行为与之前一致。
 *
 * 设计要点：
 *   - 一个事件一条 KV 记录，记录不可变 ⇒ 没有读改写，不会并发覆盖丢数据。
 *   - 事件载荷同时写进 value 和 metadata。metadata 会随 KV list 一起返回，
 *     所以导出整天的数据只需 1 次 list 调用，不必逐条 get
 *     （Workers 免费版每次请求只有 50 个子请求，逐条 get 会超限）。
 *   - 访客标识 = SHA-256(IP + UA + 当日盐) 的前 12 位十六进制。
 *     不存 IP、不存 UA、每天变化、不可反推，只用于当天去重算 UV。
 */

const MAX_BODY = 4096;             // 上报体上限，防滥用
const MAX_DAYS_PER_CALL = 7;       // 单次导出最多覆盖几天，更长的由脚本续拉
const MAX_LIST_CALLS = 40;         // 单次导出最多几次 KV list（子请求预算内）
const PAGE_LIMIT = 1000;           // KV list 单页上限
const TZ_OFFSET_MS = 8 * 3600000;  // 按东八区切天，和你本地作息对齐

function jsonResponse(obj, status) {
  return new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: {
      'content-type': 'application/json; charset=utf-8',
      'cache-control': 'no-store',
    },
  });
}

/** 现在属于东八区的哪一天（只用来给事件打日期标签） */
function bizDay(ms) {
  return new Date(ms + TZ_OFFSET_MS).toISOString().slice(0, 10);
}

function isValidDay(s) {
  return typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s);
}

/** 日期标签的加减，纯字符串日期运算，与时区无关 */
function shiftDay(day, delta) {
  const t = Date.parse(day + 'T00:00:00Z') + delta * 86400000;
  return new Date(t).toISOString().slice(0, 10);
}

/** 当日轮换的访客标识：不存原始 IP / UA，无法反推，隔天即失效 */
async function visitorId(request, env, day) {
  const ip = request.headers.get('cf-connecting-ip') || '';
  const ua = request.headers.get('user-agent') || '';
  const salt = (env.STATS_KEY || 'no-salt') + '|' + day;
  const bytes = new TextEncoder().encode(ip + '|' + ua + '|' + salt);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  let out = '';
  const view = new Uint8Array(digest).subarray(0, 6);
  for (let i = 0; i < view.length; i++) {
    out += view[i].toString(16).padStart(2, '0');
  }
  return out;
}

/** 只接受来自本站页面的上报，挡掉随手伪造的批量灌水（不是严密防线，配合面板限流用） */
function sameSite(request) {
  const origin = request.headers.get('origin');
  if (!origin) return true;          // 部分浏览器/场景不带 Origin，放行
  try {
    return new URL(origin).host === new URL(request.url).host;
  } catch (e) {
    return false;
  }
}

async function handleTrack(request, env) {
  if (!sameSite(request)) {
    return jsonResponse({ ok: false, err: 'bad-origin' }, 403);
  }

  let body;
  try {
    const text = await request.text();
    if (!text || text.length > MAX_BODY) {
      return jsonResponse({ ok: false, err: 'bad-body' }, 400);
    }
    body = JSON.parse(text);
  } catch (e) {
    return jsonResponse({ ok: false, err: 'bad-json' }, 400);
  }

  const kind = body && body.e;
  if (kind !== 'view' && kind !== 'download') {
    return jsonResponse({ ok: false, err: 'bad-event' }, 400);
  }

  const now = Date.now();
  const day = bizDay(now);
  const rand = Math.random().toString(36).slice(2, 8);

  const rec = { t: now, e: kind };
  if (kind === 'download') {
    const work = String(body.w || '').replace(/[\r\n\t]/g, ' ').slice(0, 120);
    if (work) rec.w = work;
  }
  rec.u = await visitorId(request, env, day);
  rec.i = String(now).padStart(13, '0') + '-' + rand;   // 事件唯一 id，供本地去重

  const key = 'e:' + day + '/' + rec.i;

  try {
    await env.STATS.put(key, JSON.stringify(rec), { metadata: rec });
  } catch (e) {
    // KV 免费版每日写入有上限（1000 次），超了会抛错。统计失败不能影响页面。
    return jsonResponse({ ok: false, err: 'kv-write' }, 500);
  }
  return new Response(null, { status: 204, headers: { 'cache-control': 'no-store' } });
}

async function handleExport(request, env) {
  const expected = env.STATS_KEY || '';
  if (!expected) {
    return jsonResponse({ ok: false, err: 'server-not-configured', hint: 'STATS_KEY 未配置' }, 500);
  }
  const given = request.headers.get('x-stats-key') || '';
  if (given !== expected) {
    return jsonResponse({ ok: false, err: 'unauthorized' }, 401);
  }

  const url = new URL(request.url);
  const today = bizDay(Date.now());
  const from = url.searchParams.get('from') || today;
  const to = url.searchParams.get('to') || from;

  if (!isValidDay(from) || !isValidDay(to)) {
    return jsonResponse({ ok: false, err: 'bad-date', hint: '格式 YYYY-MM-DD' }, 400);
  }
  if (from > to) {
    return jsonResponse({ ok: true, from: from, to: to, nextFrom: null, days: {}, total: 0 });
  }

  const wanted = [];
  let cursorDay = from;
  while (cursorDay <= to && wanted.length < MAX_DAYS_PER_CALL) {
    wanted.push(cursorDay);
    cursorDay = shiftDay(cursorDay, 1);
  }
  const nextFrom = cursorDay <= to ? cursorDay : null;

  let listCalls = 0;
  const days = {};
  const truncatedDays = [];
  let total = 0;

  for (let i = 0; i < wanted.length; i++) {
    const day = wanted[i];
    const events = [];
    let cursor = undefined;
    let truncated = false;

    for (;;) {
      if (listCalls >= MAX_LIST_CALLS) { truncated = true; break; }
      let page;
      try {
        page = await env.STATS.list({ prefix: 'e:' + day + '/', cursor: cursor, limit: PAGE_LIMIT });
      } catch (e) {
        return jsonResponse({ ok: false, err: 'kv-list', day: day }, 500);
      }
      listCalls++;

      const keys = page.keys || [];
      for (let k = 0; k < keys.length; k++) {
        const meta = keys[k].metadata;
        if (meta && typeof meta.t === 'number' && meta.i) {
          events.push(meta);
        } else {
          // 兜底：metadata 缺失时至少留下记录名，脚本会单条回捞
          events.push({ t: 0, e: 'unknown', i: keys[k].name });
        }
      }
      if (page.list_complete) break;
      cursor = page.cursor;
    }

    if (truncated) truncatedDays.push(day);
    events.sort(function (a, b) { return a.t - b.t; });
    days[day] = events;
    total += events.length;
  }

  return jsonResponse({
    ok: true,
    from: wanted[0],
    to: wanted[wanted.length - 1],
    nextFrom: nextFrom,
    truncatedDays: truncatedDays,
    total: total,
    days: days,
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (path === '/api/track') {
      if (request.method === 'OPTIONS') {
        return new Response(null, { status: 204 });
      }
      if (request.method !== 'POST') {
        return jsonResponse({ ok: false, err: 'method-not-allowed' }, 405);
      }
      return handleTrack(request, env);
    }

    if (path === '/api/export') {
      if (request.method !== 'GET') {
        return jsonResponse({ ok: false, err: 'method-not-allowed' }, 405);
      }
      return handleExport(request, env);
    }

    // 其余一律走静态资源，保持与未加 Worker 时完全一致的行为
    return env.ASSETS.fetch(request);
  },
};
