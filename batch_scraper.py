import hashlib
import httpx
import json
import os
import re
import sys
import time
import urllib.parse

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 从环境变量读取 SESSDATA，或在此处直接填写
# 获取方式：浏览器登录 B站 → F12 → Application → Cookies → bilibili.com → SESSDATA
SESSDATA = os.environ.get("BILI_SESSDATA", "your_sessdata_here").strip()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
    "Cookie": f"SESSDATA={SESSDATA}",
}

# 复用长连接并绕过本地未安装 socksio 的系统代理干扰
CLIENT = httpx.Client(headers=HEADERS, timeout=30, trust_env=False)
HTTP_STATS = {"requests": 0}

# B站 WBI 签名重排映射表
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35, 27, 43, 5, 49,
    33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13, 37, 48, 7, 16, 24, 55, 40,
    61, 26, 17, 0, 1, 60, 51, 30, 4, 22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11,
    36, 20, 34, 44, 52,
]
_WBI_KEYS_CACHE = None


def request_json(url, params=None, retries=3):
    for attempt in range(retries):
        try:
            HTTP_STATS["requests"] += 1
            r = CLIENT.get(url, params=params)
            return r.json()
        except Exception as e:
            if attempt < retries - 1:
                wait = (attempt + 1) * 2
                print(f"    [WARN] 网络请求异常 ({e})，{wait}s 后重试 ({attempt+1}/{retries})...", file=sys.stderr)
                time.sleep(wait)
            else:
                print(f"    [ERROR] 请求失败 ({url}): {e}", file=sys.stderr)
    return None


def get_wbi_keys():
    global _WBI_KEYS_CACHE
    if _WBI_KEYS_CACHE:
        return _WBI_KEYS_CACHE
    img_key = "7cd084941338484aae1ad9425b84077c"
    sub_key = "4932caff0ff746eab6f01bf08b70ac45"
    data = request_json("https://api.bilibili.com/x/web-interface/nav")
    if data and data.get("data", {}).get("wbi_img"):
        wbi_img = data["data"]["wbi_img"]
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")
        if img_url and sub_url:
            img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
            sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    _WBI_KEYS_CACHE = (img_key, sub_key)
    return _WBI_KEYS_CACHE


def sign_wbi(params):
    img_key, sub_key = get_wbi_keys()
    mixin_key = "".join((img_key + sub_key)[i] for i in MIXIN_KEY_ENC_TAB)[:32]
    signed = dict(params)
    signed["wts"] = round(time.time())
    signed = dict(sorted(signed.items()))
    clean_params = {
        k: "".join(ch for ch in str(v) if ch not in "!'()*")
        for k, v in signed.items()
    }
    query = urllib.parse.urlencode(clean_params)
    clean_params["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return clean_params


def get_video_info(bvid):
    data = request_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}")
    if not data:
        return None
    if data.get("code") != 0:
        print(f"  [ERROR] 获取视频信息失败 (code={data.get('code')}): {data.get('message')}", file=sys.stderr)
        return None
    d = data["data"]
    return {
        "title": d.get("title", ""),
        "view": d.get("stat", {}).get("view", 0),
        "like": d.get("stat", {}).get("like", 0),
        "reply": d.get("stat", {}).get("reply", 0),
        "aid": d.get("aid", 0),
        "bvid": d.get("bvid", bvid),
        "owner": d.get("owner", {}).get("name", ""),
        "pubdate": d.get("pubdate", 0),
    }


def _parse_sub_reply_item(s):
    return {
        "rpid": s.get("rpid"),
        "uname": s.get("member", {}).get("uname", ""),
        "content": s.get("content", {}).get("message", ""),
        "like": s.get("like", 0),
    }


def _parse_main_reply_item(reply):
    inline_raw = reply.get("replies") or []
    return {
        "rpid": reply.get("rpid"),
        "uname": reply.get("member", {}).get("uname", ""),
        "content": reply.get("content", {}).get("message", ""),
        "like": reply.get("like", 0),
        "rcount": reply.get("rcount", 0),
        "ctime": reply.get("ctime", 0),
        "_inline_subs": [_parse_sub_reply_item(s) for s in inline_raw],
    }


def _extract_pinned_replies(data_obj):
    pinned = []
    for item in data_obj.get("top_replies") or []:
        if item and item.get("rpid"):
            pinned.append(_parse_main_reply_item(item))
    upper_top = (data_obj.get("top") or {}).get("upper")
    if upper_top and upper_top.get("rpid"):
        pinned.append(_parse_main_reply_item(upper_top))
    return pinned


def get_top_comments_legacy(aid, mode=3, max_pages=250):
    """方案 A 主引擎：旧版 /x/v2/reply/main 接口（mode=3 热门，mode=2 最新时间）"""
    all_replies = []
    cursor = 0
    page_count = 0
    is_end = False
    while page_count < max_pages:
        params = {"oid": aid, "type": 1, "mode": mode, "ps": 20}
        if cursor:
            params["next"] = cursor
        else:
            params["pn"] = page_count + 1
        data = request_json("https://api.bilibili.com/x/v2/reply/main", params=params)
        if not data:
            break
        if data.get("code") != 0:
            print(f"    [WARN] Legacy 主评论接口返回异常 (code={data.get('code')}): {data.get('message')}", file=sys.stderr)
            break
        data_obj = data.get("data") or {}
        if page_count == 0:
            all_replies.extend(_extract_pinned_replies(data_obj))
        replies = data_obj.get("replies") or []
        if not replies:
            is_end = True
            break
        for reply in replies:
            all_replies.append(_parse_main_reply_item(reply))
        page_count += 1
        cursor_obj = data_obj.get("cursor") or {}
        cursor = cursor_obj.get("next", 0)
        is_end = bool(cursor_obj.get("is_end")) or not cursor
        if page_count % 10 == 0 or is_end or page_count == max_pages:
            print(f"    [Legacy mode={mode}] Page {page_count}: 累计 {len(all_replies)} 条", file=sys.stderr)
        if is_end:
            break
        time.sleep(0.25)
    return all_replies, is_end


def get_top_comments_wbi(aid, mode=3, max_pages=250):
    """方案 B 主引擎：新版 /x/v2/reply/wbi/main 签名接口（支持 pagination_str 深度游标翻页）"""
    all_replies = []
    offset_str = ""
    page_count = 0
    is_end = False
    while page_count < max_pages:
        pagination = json.dumps({"offset": offset_str}, separators=(",", ":"))
        raw_params = {
            "oid": aid,
            "type": 1,
            "mode": mode,
            "ps": 20,
            "plat": 1,
            "web_location": 1315875,
            "pagination_str": pagination,
        }
        params = sign_wbi(raw_params)
        data = request_json("https://api.bilibili.com/x/v2/reply/wbi/main", params=params)
        if not data:
            break
        if data.get("code") != 0:
            print(f"    [WARN] WBI 主评论接口返回异常 (code={data.get('code')}): {data.get('message')}", file=sys.stderr)
            break
        data_obj = data.get("data") or {}
        if page_count == 0:
            all_replies.extend(_extract_pinned_replies(data_obj))
        replies = data_obj.get("replies") or []
        if not replies:
            is_end = True
            break
        for reply in replies:
            all_replies.append(_parse_main_reply_item(reply))
        page_count += 1
        cursor_obj = data_obj.get("cursor") or {}
        offset_str = (cursor_obj.get("pagination_reply") or {}).get("next_offset", "")
        is_end = bool(cursor_obj.get("is_end")) or not offset_str
        if page_count % 10 == 0 or is_end or page_count == max_pages:
            print(f"    [WBI mode={mode}] Page {page_count}: 累计 {len(all_replies)} 条", file=sys.stderr)
        if is_end:
            break
        time.sleep(0.25)
    return all_replies, is_end


def get_sub_replies(aid, rpid, rcount=0, max_pages=15):
    """方案 A 楼中楼优化：一旦单页返回不足 20 条或已拿满 rcount 条，立即终止翻页"""
    all_subs = []
    for pn in range(1, max_pages + 1):
        params = {"oid": aid, "type": 1, "root": rpid, "ps": 20, "pn": pn}
        data = request_json("https://api.bilibili.com/x/v2/reply/reply", params=params)
        if not data:
            break
        if data.get("code") != 0:
            print(f"    [WARN] 楼中楼接口返回异常 (code={data.get('code')}): {data.get('message')}", file=sys.stderr)
            break
        replies = (data.get("data") or {}).get("replies") or []
        if not replies:
            break
        for s in replies:
            all_subs.append(_parse_sub_reply_item(s))
        # 提前终止条件：当前页不足 20 条，或累计数量已达预期 rcount
        if len(replies) < 20 or (rcount > 0 and len(all_subs) >= rcount):
            break
        if pn < max_pages:
            time.sleep(0.12)
    return all_subs


def run_scrape_pipeline(info, engine="wbi", max_pages=250, max_sub_pages=15):
    """执行单视频完整抓取流水线，返回结果字典与性能指标"""
    t0 = time.time()
    req_start = HTTP_STATS["requests"]
    fetch_fn = get_top_comments_wbi if engine == "wbi" else get_top_comments_legacy

    print(f"  [1/3] 爬取主评论 (引擎={engine.upper()}, 热门排序 mode=3, 上限={max_pages}页)...", file=sys.stderr)
    hot, hot_is_end = fetch_fn(info["aid"], mode=3, max_pages=max_pages)

    # 若 WBI 首趟失败且拿到 0 条，自动降级回 legacy 兜底
    if engine == "wbi" and not hot:
        print("  [WARN] WBI 接口未返回数据，自动降级至 Legacy 接口重试...", file=sys.stderr)
        hot, hot_is_end = get_top_comments_legacy(info["aid"], mode=3, max_pages=max_pages)

    # 方案 A 智能单/双趟：仅当第 1 趟未翻到底（被 max_pages 截断）时，才启动第 2 趟按时间排序互补
    if hot_is_end:
        print(f"  [2/3] 热门排序已翻到底 (is_end=True)，100% 主评论已捕获，免跑第 2 趟时间排序!", file=sys.stderr)
        time_c = []
    else:
        print(f"  [2/3] 主评论超 {max_pages} 页未见底，启动第 2 趟 (最新时间排序 mode=2) 互补...", file=sys.stderr)
        time_c, _ = fetch_fn(info["aid"], mode=2, max_pages=max_pages)

    seen = set()
    merged = []
    for c in hot + time_c:
        if c["rpid"] not in seen:
            seen.add(c["rpid"])
            merged.append(c)

    with_replies = [c for c in merged if c.get("rcount", 0) > 0]
    print(f"  [3/3] 主评论去重后: {len(merged)} 条 (含子回复主楼: {len(with_replies)} 条)...", file=sys.stderr)

    subs_total = 0
    inline_hit_count = 0
    api_sub_fetch_count = 0

    for i, c in enumerate( merged ):
        inline_subs = c.pop("_inline_subs", [])
        rcount = c.get("rcount", 0)
        if rcount <= 0:
            continue
        # 方案 A 核心优化：若主评论接口自带的 inline replies 已包含全部子回复，0 请求直接复用
        if len(inline_subs) >= rcount and inline_subs:
            c["sub_replies"] = inline_subs
            subs_total += len(inline_subs)
            inline_hit_count += 1
        else:
            api_sub_fetch_count += 1
            subs = get_sub_replies(info["aid"], c["rpid"], rcount=rcount, max_pages=max_sub_pages)
            if subs:
                c["sub_replies"] = subs
                subs_total += len(subs)
            elif inline_subs:
                c["sub_replies"] = inline_subs
                subs_total += len(inline_subs)
            if api_sub_fetch_count % 20 == 0:
                print(
                    f"    楼中楼进度: API请求 {api_sub_fetch_count} 楼 | 内联免请求 {inline_hit_count} 楼 | 已获子回复 {subs_total} 条",
                    file=sys.stderr,
                )
            time.sleep(0.08)

    elapsed = time.time() - t0
    req_used = HTTP_STATS["requests"] - req_start

    # 估算旧版未优化逻辑的请求数：2 趟主评论 + 每个 with_replies 至少请求 2 页
    old_est_requests = (len(hot) // 20 + 1) * 2 + sum(min(5, (c.get("rcount", 0) // 20) + 2) for c in with_replies)

    output = {
        "video": info,
        "engine": engine,
        "top_level_count": len(merged),
        "sub_reply_count": subs_total,
        "total_count": len(merged) + subs_total,
        "comments": merged,
    }
    metrics = {
        "engine": engine,
        "elapsed_sec": round(elapsed, 2),
        "http_requests": req_used,
        "old_est_requests": old_est_requests,
        "top_count": len(merged),
        "with_replies_count": len(with_replies),
        "inline_hit_count": inline_hit_count,
        "api_sub_fetch_count": api_sub_fetch_count,
        "sub_count": subs_total,
        "total_count": len(merged) + subs_total,
        "coverage_pct": round((len(merged) + subs_total) / max(1, info.get("reply", 1)) * 100, 1),
        "rpid_set": seen,
    }
    return output, metrics


def print_comparison_report(info, m_legacy, m_wbi):
    only_wbi = len(m_wbi["rpid_set"] - m_legacy["rpid_set"])
    only_legacy = len(m_legacy["rpid_set"] - m_wbi["rpid_set"])
    overlap = len(m_wbi["rpid_set"] & m_legacy["rpid_set"])

    print(f"\n{'='*74}", file=sys.stderr)
    print(f"📊 双方案实测同台对比报告 — {info['bvid']} 《{info['title'][:28]}》", file=sys.stderr)
    print(f"   B站官方显示总评论数 (stat.reply): {info['reply']} 条", file=sys.stderr)
    print(f"{'-'*74}", file=sys.stderr)
    print(f"{'指标维度':<24} | {'方案 A (Legacy 极速版)':<20} | {'方案 B (WBI 签名极速版)':<20}", file=sys.stderr)
    print(f"{'-'*74}", file=sys.stderr)
    print(f"{'总耗时 (秒)':<24} | {str(m_legacy['elapsed_sec']) + 's':<20} | {str(m_wbi['elapsed_sec']) + 's':<20}", file=sys.stderr)
    print(f"{'实际 HTTP 请求次数':<24} | {str(m_legacy['http_requests']) + ' 次':<20} | {str(m_wbi['http_requests']) + ' 次':<20}", file=sys.stderr)
    print(f"{'改造前旧代码预估请求数':<22} | {str(m_legacy['old_est_requests']) + ' 次 (省 ' + str(round((1 - m_legacy['http_requests']/max(1, m_legacy['old_est_requests']))*100)) + '%)':<20} | {str(m_wbi['old_est_requests']) + ' 次 (省 ' + str(round((1 - m_wbi['http_requests']/max(1, m_wbi['old_est_requests']))*100)) + '%)':<20}", file=sys.stderr)
    print(f"{'一级主评论数 (去重后)':<22} | {str(m_legacy['top_count']) + ' 条':<20} | {str(m_wbi['top_count']) + ' 条':<20}", file=sys.stderr)
    leg_hit_str = f"{m_legacy['inline_hit_count']}/{m_legacy['with_replies_count']} 楼"
    wbi_hit_str = f"{m_wbi['inline_hit_count']}/{m_wbi['with_replies_count']} 楼"
    print(f"{'楼中楼内联免请求命中':<22} | {leg_hit_str:<20} | {wbi_hit_str:<20}", file=sys.stderr)
    print(f"{'楼中楼子回复总数':<23} | {str(m_legacy['sub_count']) + ' 条':<20} | {str(m_wbi['sub_count']) + ' 条':<20}", file=sys.stderr)
    print(f"{'抓取总评论数 (主+子)':<22} | {str(m_legacy['total_count']) + ' 条':<20} | {str(m_wbi['total_count']) + ' 条':<20}", file=sys.stderr)
    print(f"{'总覆盖率 (实抓/官方显示)':<22} | {str(m_legacy['coverage_pct']) + '%':<20} | {str(m_wbi['coverage_pct']) + '%':<20}", file=sys.stderr)
    print(f"{'-'*74}", file=sys.stderr)
    print(
        f"🔍 主评论 rpid 集合对比: 重合 {overlap} 条 | 仅方案 A 抓到: {only_legacy} 条 | 仅方案 B 抓到: {only_wbi} 条",
        file=sys.stderr,
    )
    print(f"{'='*74}\n", file=sys.stderr)


def parse_cli_args(argv):
    is_official = False
    compare_mode = False
    engine = "wbi"
    max_pages = 250
    max_sub_pages = 15
    bvs = []

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--official":
            is_official = True
        elif arg in ("--compare", "--benchmark"):
            compare_mode = True
        elif arg == "--engine" and i + 1 < len(argv):
            engine = argv[i + 1].lower()
            i += 1
        elif arg.startswith("--engine="):
            engine = arg.split("=", 1)[1].lower()
        elif arg == "--max-pages" and i + 1 < len(argv):
            max_pages = int(argv[i + 1])
            i += 1
        elif arg.startswith("--max-pages="):
            max_pages = int(arg.split("=", 1)[1])
        elif arg == "--max-sub-pages" and i + 1 < len(argv):
            max_sub_pages = int(argv[i + 1])
            i += 1
        elif not arg.startswith("-"):
            m = re.search(r"(BV[0-9A-Za-z]{10})", arg)
            bvs.append(m.group(1) if m else arg)
        i += 1

    if engine not in ("wbi", "legacy"):
        print(f"[ERROR] 不支持的 --engine 参数: {engine}（可选: wbi, legacy）", file=sys.stderr)
        sys.exit(1)

    return is_official, compare_mode, engine, max_pages, max_sub_pages, bvs


if __name__ == "__main__":
    is_official, compare_mode, engine, max_pages, max_sub_pages, bvs = parse_cli_args(sys.argv[1:])

    if not bvs:
        print(
            "Usage: python batch_scraper.py [--official] [--engine wbi|legacy] [--max-pages 250] [--compare] <BV号或B站视频链接> ...",
            file=sys.stderr,
        )
        sys.exit(1)

    if not SESSDATA or SESSDATA == "your_sessdata_here":
        print(
            "[WARN] 未检测到有效的 BILI_SESSDATA 环境变量！未登录状态下每个视频仅能抓取前 20 条评论。",
            file=sys.stderr,
        )

    os.makedirs(os.path.join(BASE_DIR, "comments", "official"), exist_ok=True)
    os.makedirs(os.path.join(BASE_DIR, "comments", "players"), exist_ok=True)
    output_dir = os.path.join(BASE_DIR, "comments", "official" if is_official else "players")
    label_str = "official (官方视频)" if is_official else "players (玩家/UP主视频)"
    mode_desc = "COMPARE (方案A Legacy vs 方案B WBI 同台对比)" if compare_mode else f"ENGINE={engine.upper()}"
    print(f"输出目录: {output_dir} [{label_str}] | 运行模式: {mode_desc} | 单趟页数上限: {max_pages}", file=sys.stderr)

    success_count = 0
    for idx, bvid in enumerate(bvs, 1):
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"[{idx}/{len(bvs)}] 开始处理: {bvid}", file=sys.stderr)

        info = get_video_info(bvid)
        if not info:
            print(f"  [SKIP] 无法获取视频信息: {bvid}", file=sys.stderr)
            continue

        print(f"  标题: {info['title']}", file=sys.stderr)
        print(f"  播放: {info['view']} | 评论: {info['reply']} | UP: {info['owner']}", file=sys.stderr)

        if compare_mode:
            print(f"\n  >>> 正在运行【方案 A：Legacy 极速版】...", file=sys.stderr)
            out_legacy, m_legacy = run_scrape_pipeline(info, engine="legacy", max_pages=max_pages, max_sub_pages=max_sub_pages)
            print(f"\n  >>> 正在运行【方案 B：WBI 签名极速版】...", file=sys.stderr)
            out_wbi, m_wbi = run_scrape_pipeline(info, engine="wbi", max_pages=max_pages, max_sub_pages=max_sub_pages)
            print_comparison_report(info, m_legacy, m_wbi)
            # 择优保存抓取数量更多的结果
            if m_wbi["total_count"] >= m_legacy["total_count"]:
                output, m_best = out_wbi, m_wbi
            else:
                output, m_best = out_legacy, m_legacy
        else:
            output, m_best = run_scrape_pipeline(info, engine=engine, max_pages=max_pages, max_sub_pages=max_sub_pages)

        safe_title = (
            info["title"]
            .replace("/", "／")
            .replace("\\", "＼")
            .replace(":", "：")
            .replace("*", "＊")
            .replace("?", "？")
            .replace('"', "＂")
            .replace("<", "＜")
            .replace(">", "＞")
            .replace("|", "｜")[:30]
        )
        fname = f"{idx:02d}_{safe_title}_{bvid}.json"
        fpath = os.path.join(output_dir, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        success_count += 1
        print(f"  ✅ [{idx}/{len(bvs)}] {bvid} 完成! (胜出/采用引擎: {m_best['engine'].upper()}, 耗时: {m_best['elapsed_sec']}s, 请求数: {m_best['http_requests']})", file=sys.stderr)
        print(
            f"     主评论: {m_best['top_count']} | 子回复: {m_best['sub_count']} (内联免请求 {m_best['inline_hit_count']} 楼) | 总计: {m_best['total_count']} ({m_best['coverage_pct']}%)",
            file=sys.stderr,
        )
        print(f"     保存: {fname}", file=sys.stderr)

        if idx < len(bvs):
            time.sleep(1)

    print(f"\n{'='*70}", file=sys.stderr)
    if success_count == 0:
        print(f"[ERROR] 全部 {len(bvs)} 个视频均抓取失败，请检查 BV 号或网络连接。", file=sys.stderr)
        sys.exit(1)
    print(f"🎉 全部完成! 成功处理 {success_count}/{len(bvs)} 个视频", file=sys.stderr)


