#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pull_stats.py — 把 haorenyige.top 的访问统计拉到本地

在项目根目录执行：

    python stats\\pull_stats.py                 增量拉取 + 生成报表
    python stats\\pull_stats.py --full          从 2026-01-01 起重拉（按事件 id 去重，不会重复计数）
    python stats\\pull_stats.py --from 2026-10-01
    python stats\\pull_stats.py --set-key       重新输入读取密钥
    python stats\\pull_stats.py --report-only   只用本地已有数据出报表，不联网

数据全部留在本机，这些路径已在 .gitignore 里，不会进公开仓库：

    stats\\.secret               读取密钥（只有本机有）
    stats\\data\\events.jsonl     累计的原始事件，只增不减
    stats\\data\\state.json       增量水位线
    stats\\reports\\*.md  *.csv   每次运行生成的报表

读数据要用的 STATS_KEY，就是你在 Cloudflare 给 my-gallery 配的那个密钥。
它只存在本机，脚本不会把它发到除你站点之外的任何地方。
"""

import argparse
import csv
import getpass
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REPORT_DIR = os.path.join(BASE_DIR, "reports")
SECRET_FILE = os.path.join(BASE_DIR, ".secret")
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")
STATE_FILE = os.path.join(DATA_DIR, "state.json")

DEFAULT_SITE = "https://haorenyige.top"
TZ8 = timezone(timedelta(hours=8))
FIRST_POSSIBLE_DAY = "2026-01-01"


def today8():
    return datetime.now(TZ8).strftime("%Y-%m-%d")


def day_of(ev):
    """事件属于哪一天（东八区）。优先用存下来的标签，老数据按时间戳推算。"""
    d = ev.get("day")
    if d:
        return d
    t = ev.get("t") or 0
    if not t:
        return "(未知日期)"
    return datetime.fromtimestamp(t / 1000.0, TZ8).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ 密钥
def load_secret(force=False):
    if not force and os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, encoding="utf-8") as f:
            s = f.read().strip()
        if s:
            return s

    print("第一次使用需要输入读取密钥。")
    print("就是你在 Cloudflare 给 my-gallery 配的 STATS_KEY。")
    print("它只保存在本机这个文件里，不会发给任何第三方。")
    print()
    s = getpass.getpass("粘贴 STATS_KEY（输入时屏幕不显示）: ").strip()
    if not s:
        sys.exit("没有输入密钥，已退出。")
    os.makedirs(BASE_DIR, exist_ok=True)
    with open(SECRET_FILE, "w", encoding="utf-8") as f:
        f.write(s)
    try:
        os.chmod(SECRET_FILE, 0o600)
    except Exception:
        pass
    print("已保存到 %s" % SECRET_FILE)
    print()
    return s


# ------------------------------------------------------------------ 拉取
def api_export(site, key, frm, to):
    url = "%s/api/export?from=%s&to=%s" % (site.rstrip("/"), frm, to)
    req = urllib.request.Request(url, headers={
        "X-Stats-Key": key,
        "Accept": "application/json",
        "User-Agent": "my-gallery-stats/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        if e.code == 401:
            sys.exit("密钥不对（HTTP 401）。用 --set-key 重新输入。")
        if e.code == 404:
            sys.exit(
                "读取接口不存在（HTTP 404）。\n"
                "可能原因：worker.js 还没部署成功，或 Cloudflare 那边 KV 绑定没配好。\n"
                "先在浏览器打开 %s/api/export 看一眼返回什么。" % site.rstrip("/")
            )
        sys.exit("请求失败 HTTP %s：%s" % (e.code, body))
    except Exception as e:
        sys.exit("网络错误：%s" % e)


def pull(site, key, start_day, end_day):
    """按天拉取，跟随 nextFrom 续拉，返回 {日期: [事件]} 与问题列表。"""
    collected = {}
    problems = []
    day = start_day
    rounds = 0

    while day <= end_day:
        rounds += 1
        if rounds > 500:
            problems.append("拉取轮次过多（>500），已停止")
            break

        data = api_export(site, key, day, end_day)
        if not data.get("ok"):
            problems.append("接口返回异常：%s" % data.get("err"))
            break

        for d, evs in (data.get("days") or {}).items():
            bucket = collected.setdefault(d, [])
            for ev in evs:
                ev["day"] = d
                bucket.append(ev)

        got = sum(len(v) for v in collected.values())
        print("   %s ~ %s  累计 %d 条" % (data.get("from"), data.get("to"), got))

        for d in (data.get("truncatedDays") or []):
            problems.append("这一天数据超过单次上限，本次没取全：%s（下次运行会补）" % d)

        nxt = data.get("nextFrom")
        if not nxt:
            break
        day = nxt

    return collected, problems


def load_local():
    events, ids, broken = [], set(), 0
    if not os.path.exists(EVENTS_FILE):
        return events, ids, broken
    with open(EVENTS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                broken += 1
                continue
            if not ev.get("i"):
                broken += 1
                continue
            if ev["i"] in ids:
                continue
            ids.add(ev["i"])
            events.append(ev)
    return events, ids, broken


def save_new(new_events):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(EVENTS_FILE, "a", encoding="utf-8") as f:
        for ev in new_events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def read_state():
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def write_state(obj):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------------ 报表
def summarize(events):
    per_day = {}
    downloads = {}
    total_pv = 0
    total_dl = 0

    for ev in events:
        d = day_of(ev)
        b = per_day.setdefault(d, {"pv": 0, "dl": 0, "uv": set()})
        kind = ev.get("e")
        if kind == "view":
            b["pv"] += 1
            total_pv += 1
            if ev.get("u"):
                b["uv"].add(ev["u"])
        elif kind == "download":
            b["dl"] += 1
            total_dl += 1
            downloads[ev.get("w") or "(未识别作品)"] = downloads.get(ev.get("w") or "(未识别作品)", 0) + 1

    total_uv = sum(len(b["uv"]) for b in per_day.values())
    return per_day, downloads, total_pv, total_uv, total_dl


def write_report(events, problems, site, broken_local, new_count, verbose=True):
    per_day, downloads, total_pv, total_uv, total_dl = summarize(events)
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = today8()

    days_sorted = sorted(d for d in per_day if d != "(未知日期)")
    unknown_day = per_day.get("(未知日期)")

    lines = []
    lines.append("# haorenyige.top 访问统计")
    lines.append("")
    lines.append("- 生成时间：%s（东八区）" % datetime.now(TZ8).strftime("%Y-%m-%d %H:%M:%S"))
    lines.append("- 数据来源：%s" % site)
    if days_sorted:
        lines.append("- 数据范围：%s ~ %s" % (days_sorted[0], days_sorted[-1]))
    lines.append("- 本地累计事件：%d 条" % len(events))
    lines.append("")

    lines.append("## 总览")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("| --- | --- |")
    lines.append("| 访问量 PV | %d |" % total_pv)
    lines.append("| 独立访客（按天去重后合计） | %d |" % total_uv)
    lines.append("| 下载点击数 | %d |" % total_dl)
    if total_pv:
        lines.append("| 下载 / 访问 | %.2f%% |" % (total_dl * 100.0 / total_pv))
    else:
        lines.append("| 下载 / 访问 | — |")
    lines.append("")

    lines.append("## 按天")
    lines.append("")
    lines.append("| 日期 | 访问量 | 独立访客 | 下载点击 |")
    lines.append("| --- | ---: | ---: | ---: |")
    for d in days_sorted:
        b = per_day[d]
        lines.append("| %s | %d | %d | %d |" % (d, b["pv"], len(b["uv"]), b["dl"]))
    if unknown_day:
        lines.append("| (未知日期) | %d | %d | %d |" % (
            unknown_day["pv"], len(unknown_day["uv"]), unknown_day["dl"]))
    lines.append("")

    lines.append("## 下载排行（TOP 30）")
    lines.append("")
    if downloads:
        lines.append("| # | 作品 | 下载次数 |")
        lines.append("| ---: | --- | ---: |")
        for i, (w, n) in enumerate(sorted(downloads.items(), key=lambda x: (-x[1], x[0]))[:30], 1):
            lines.append("| %d | %s | %d |" % (i, w.replace("|", "/"), n))
    else:
        lines.append("还没有下载点击记录。")
    lines.append("")

    lines.append("## 口径与备注")
    lines.append("")
    lines.append("- **PV**：每次页面加载算一次。")
    lines.append("- **UV**：访客标识是「IP + 浏览器标识 + 当日密钥」的哈希前 12 位，")
    lines.append("  每天重新生成且不可反推，所以只能当天去重；跨天的总数是每日去重后相加。")
    lines.append("  不保存 IP、不保存浏览器标识、不使用 Cookie。")
    lines.append("- **下载点击**：点卡片上的「下载原图」或灯箱里的下载链接各算一次。")
    lines.append("  记录的是作品名，不是文件路径。")
    lines.append("- 统计天数按东八区切分。")
    if new_count:
        lines.append("- 本次新增 %d 条事件。" % new_count)
    if broken_local:
        lines.append("- 本地存档里有 %d 行无法解析，已跳过。" % broken_local)
    for p in problems:
        lines.append("- ⚠ %s" % p)
    lines.append("")

    md_path = os.path.join(REPORT_DIR, "%s-统计报表.md" % stamp)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    day_csv = os.path.join(REPORT_DIR, "%s-按天.csv" % stamp)
    with open(day_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["日期", "访问量", "独立访客", "下载点击"])
        for d in days_sorted:
            b = per_day[d]
            w.writerow([d, b["pv"], len(b["uv"]), b["dl"]])

    dl_csv = os.path.join(REPORT_DIR, "%s-下载排行.csv" % stamp)
    with open(dl_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["排名", "作品", "下载次数"])
        for i, (t, n) in enumerate(sorted(downloads.items(), key=lambda x: (-x[1], x[0])), 1):
            w.writerow([i, t, n])

    if verbose:
        print()
        print("=" * 52)
        print("  访问量 PV        : %d" % total_pv)
        print("  独立访客 UV      : %d" % total_uv)
        print("  下载点击         : %d" % total_dl)
        if total_pv:
            print("  下载 / 访问      : %.2f%%" % (total_dl * 100.0 / total_pv))
        print("=" * 52)
        print()
        print("报表已生成：")
        print("  " + md_path)
        print("  " + day_csv)
        print("  " + dl_csv)
        print("原始数据存档：%s" % EVENTS_FILE)
        if problems:
            print()
            for p in problems:
                print("  ⚠ %s" % p)

    return md_path


# ------------------------------------------------------------------ 入口
def main():
    ap = argparse.ArgumentParser(description="拉取 haorenyige.top 的访问统计到本地")
    ap.add_argument("--site", default=DEFAULT_SITE, help="站点地址")
    ap.add_argument("--from", dest="frm", help="起始日期 YYYY-MM-DD")
    ap.add_argument("--to", dest="to", help="结束日期 YYYY-MM-DD（默认今天）")
    ap.add_argument("--full", action="store_true", help="从最早重拉一遍")
    ap.add_argument("--set-key", action="store_true", help="重新输入读取密钥")
    ap.add_argument("--report-only", action="store_true", help="只用本地数据出报表，不联网")
    args = ap.parse_args()

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORT_DIR, exist_ok=True)

    events, ids, broken = load_local()
    print("本地已有 %d 条事件" % len(events))

    problems = []
    new_count = 0

    if not args.report_only:
        key = load_secret(force=args.set_key)
        state = read_state()

        end_day = args.to or today8()
        if args.frm:
            start_day = args.frm
        elif args.full:
            start_day = FIRST_POSSIBLE_DAY
        elif state.get("last_day"):
            # 从上次那天重拉，覆盖"上次没取全"的情况；重复的靠事件 id 去重
            start_day = state["last_day"]
        else:
            start_day = (datetime.now(TZ8) - timedelta(days=30)).strftime("%Y-%m-%d")

        print("拉取范围：%s ~ %s" % (start_day, end_day))
        print()
        collected, problems = pull(args.site, key, start_day, end_day)

        flat = []
        for d in sorted(collected):
            for ev in collected[d]:
                if ev.get("i") and ev["i"] not in ids:
                    ids.add(ev["i"])
                    flat.append(ev)
        new_count = len(flat)
        if flat:
            save_new(flat)
            events.extend(flat)
        print()
        print("新增 %d 条（重复的已自动丢弃）" % new_count)

        # 水位线：哪里没取全就退回到那天，下次接着补
        if problems:
            back = None
            for p in problems:
                for tok in p.split():
                    if len(tok) == 10 and tok[4] == "-" and tok[7] == "-":
                        back = tok if back is None or tok < back else back
            write_state({"last_day": back or start_day, "updated": datetime.now(TZ8).isoformat()})
        else:
            write_state({"last_day": today8(), "updated": datetime.now(TZ8).isoformat()})

    write_report(events, problems, args.site, broken, new_count)


if __name__ == "__main__":
    main()
