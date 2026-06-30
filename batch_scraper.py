import httpx
import json
import sys
import time
import os

# 从环境变量读取 SESSDATA，或在此处直接填写
# 获取方式：浏览器登录 B站 → F12 → Application → Cookies → bilibili.com → SESSDATA
SESSDATA = os.environ.get("BILI_SESSDATA", "your_sessdata_here")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com",
    "Cookie": f"SESSDATA={SESSDATA}",
}

OUTPUT_DIR = "comments/players"

def get_video_info(bvid):
    r = httpx.get(f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}", headers=HEADERS, timeout=30)
    data = r.json()
    if data.get("code") != 0:
        print(f"  [ERROR] {data.get('message')}", file=sys.stderr)
        return None
    d = data["data"]
    return {
        "title": d.get("title"),
        "view": d.get("stat", {}).get("view", 0),
        "like": d.get("stat", {}).get("like", 0),
        "reply": d.get("stat", {}).get("reply", 0),
        "aid": d.get("aid", 0),
        "bvid": d.get("bvid", bvid),
        "owner": d.get("owner", {}).get("name", ""),
        "pubdate": d.get("pubdate", 0),
    }

def get_top_comments(aid, mode=2, max_pages=50):
    all_replies = []
    cursor = 0
    page_count = 0
    while page_count < max_pages:
        params = {"oid": aid, "type": 1, "mode": mode, "ps": 20}
        if cursor:
            params["next"] = cursor
        else:
            params["pn"] = page_count + 1
        r = httpx.get("https://api.bilibili.com/x/v2/reply/main", headers=HEADERS, params=params, timeout=30)
        data = r.json()
        if data.get("code") != 0:
            break
        replies = data.get("data", {}).get("replies", [])
        if not replies:
            break
        for reply in replies:
            all_replies.append({
                "rpid": reply.get("rpid"),
                "uname": reply.get("member", {}).get("uname", ""),
                "content": reply.get("content", {}).get("message", ""),
                "like": reply.get("like", 0),
                "rcount": reply.get("rcount", 0),
                "ctime": reply.get("ctime", 0),
            })
        page_count += 1
        cursor = data.get("data", {}).get("cursor", {}).get("next", 0)
        print(f"    Page {page_count}: +{len(replies)} (total {len(all_replies)})", file=sys.stderr)
        if not cursor:
            break
        time.sleep(0.3)
    return all_replies

def get_sub_replies(aid, rpid, max_pages=5):
    all_subs = []
    for pn in range(1, max_pages + 1):
        params = {"oid": aid, "type": 1, "root": rpid, "ps": 20, "pn": pn}
        r = httpx.get("https://api.bilibili.com/x/v2/reply/reply", headers=HEADERS, params=params, timeout=30)
        data = r.json()
        if data.get("code") != 0:
            break
        replies = data.get("data", {}).get("replies", [])
        if not replies:
            break
        for s in replies:
            all_subs.append({
                "rpid": s.get("rpid"),
                "uname": s.get("member", {}).get("uname", ""),
                "content": s.get("content", {}).get("message", ""),
                "like": s.get("like", 0),
            })
        time.sleep(0.15)
    return all_subs

if __name__ == "__main__":
    bvs = sys.argv[1:] if len(sys.argv) > 1 else []
    if not bvs:
        print("Usage: python batch_scraper.py BVxxx BVxxx ...", file=sys.stderr)
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    for idx, bvid in enumerate(bvs, 1):
        print(f"\n{'='*70}", file=sys.stderr)
        print(f"[{idx}/{len(bvs)}] 开始处理: {bvid}", file=sys.stderr)

        info = get_video_info(bvid)
        if not info:
            print(f"  [SKIP] 无法获取视频信息", file=sys.stderr)
            continue

        print(f"  标题: {info['title']}", file=sys.stderr)
        print(f"  播放: {info['view']} | 评论: {info['reply']} | UP: {info['owner']}", file=sys.stderr)

        # 爬取主评论
        print(f"  [1/4] 爬取主评论(热度排序)...", file=sys.stderr)
        hot = get_top_comments(info["aid"], mode=2, max_pages=50)
        print(f"  [2/4] 爬取主评论(时间排序)...", file=sys.stderr)
        time_c = get_top_comments(info["aid"], mode=3, max_pages=50)

        # 去重
        seen = set()
        merged = []
        for c in hot + time_c:
            if c["rpid"] not in seen:
                seen.add(c["rpid"])
                merged.append(c)
        print(f"  [3/4] 主评论去重后: {len(merged)}条", file=sys.stderr)

        # 爬取子回复
        print(f"  [4/4] 爬取楼中楼...", file=sys.stderr)
        subs_total = 0
        with_replies = [c for c in merged if c.get("rcount", 0) > 0]
        print(f"    有回复的评论: {len(with_replies)}条", file=sys.stderr)

        for i, c in enumerate(with_replies):
            subs = get_sub_replies(info["aid"], c["rpid"], max_pages=5)
            if subs:
                c["sub_replies"] = subs
                subs_total += len(subs)
            if (i + 1) % 10 == 0 or i == len(with_replies) - 1:
                print(f"    子回复进度: {i+1}/{len(with_replies)}, 已获 {subs_total}条", file=sys.stderr)
            time.sleep(0.1)

        # 保存
        output = {
            "video": info,
            "top_level_count": len(merged),
            "sub_reply_count": subs_total,
            "total_count": len(merged) + subs_total,
            "comments": merged
        }

        safe_title = info['title'].replace('/', '／').replace('\\', '＼').replace(':', '：').replace('*', '＊').replace('?', '？').replace('"', '＂').replace('<', '＜').replace('>', '＞').replace('|', '｜')[:30]
        fname = f"{idx:02d}_{safe_title}_{bvid}.json"
        fpath = os.path.join(OUTPUT_DIR, fname)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        print(f"\n  ✅ [{idx}/{len(bvs)}] {bvid} 完成!", file=sys.stderr)
        print(f"     主评论: {len(merged)} | 子回复: {subs_total} | 总计: {len(merged)+subs_total}", file=sys.stderr)
        print(f"     保存: {fname}", file=sys.stderr)

        time.sleep(1)  # 视频间间隔

    print(f"\n{'='*70}", file=sys.stderr)
    print(f"🎉 全部完成! 共处理 {len(bvs)} 个视频", file=sys.stderr)
