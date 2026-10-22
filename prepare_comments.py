import json, os, sys, glob

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
players_dir = os.path.join(BASE_DIR, "comments", "players")
official_dir = os.path.join(BASE_DIR, "comments", "official")
os.makedirs(players_dir, exist_ok=True)
os.makedirs(official_dir, exist_ok=True)

all_comments = []
cid = 0

for label, d in [("official", official_dir), ("player", players_dir)]:
    files = sorted(glob.glob(os.path.join(d, "*.json")))
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        bvid = data.get("video", {}).get("bvid", "")
        title = data.get("video", {}).get("title", "")
        for c in data.get("comments", []):
            # top-level comment
            all_comments.append({
                "id": cid,
                "text": c.get("content", ""),
                "uname": c.get("uname", ""),
                "like": c.get("like", 0),
                "source_bvid": bvid,
                "source_title": title,
                "source_label": label,
                "is_sub_reply": False,
            })
            cid += 1
            # sub-replies
            for s in c.get("sub_replies", []):
                all_comments.append({
                    "id": cid,
                    "text": s.get("content", ""),
                    "uname": s.get("uname", ""),
                    "like": s.get("like", 0),
                    "source_bvid": bvid,
                    "source_title": title,
                    "source_label": label,
                    "is_sub_reply": True,
                })
                cid += 1

if not all_comments:
    print("[ERROR] 未在 comments/official/ 或 comments/players/ 下找到任何有效评论数据，请先运行 batch_scraper.py", file=sys.stderr)
    sys.exit(1)

analysis_dir = os.path.join(BASE_DIR, "comments", "analysis")
outpath = os.path.join(analysis_dir, "all_comments_combined.json")
os.makedirs(analysis_dir, exist_ok=True)
with open(outpath, "w", encoding="utf-8") as f:
    json.dump(all_comments, f, ensure_ascii=False, indent=2)

# ====== 生成自适应短序号切块（供 Agent 免 API Key 分析） ======
CHUNK_MAX_ITEMS = 300
CHUNK_MAX_CHARS = 12000

chunks_dir = os.path.join(analysis_dir, "chunks")
results_dir = os.path.join(analysis_dir, "results")
os.makedirs(chunks_dir, exist_ok=True)
os.makedirs(results_dir, exist_ok=True)

# 清理旧切块文件与上一轮残留的切块结果，防止跨批次脏数据污染
for old_f in glob.glob(os.path.join(chunks_dir, "chunk_*.txt")):
    os.remove(old_f)
for old_r in glob.glob(os.path.join(results_dir, "chunk_*_result.json")):
    os.remove(old_r)
for old_p in ("raw_points.json", "merged_points.json", "classified_llm.json"):
    p_path = os.path.join(analysis_dir, old_p)
    if os.path.exists(p_path):
        os.remove(p_path)

chunks_meta = []
cur_items = []
cur_chars = 0


def flush_chunk(items, idx):
    chunk_id = f"chunk_{idx:02d}"
    lines = []
    local_map = {}
    for local_i, item in enumerate(items, 1):
        clean_text = item["text"].replace("\r", " ").replace("\n", " ").strip()
        if len(clean_text) > 300:
            clean_text = clean_text[:300] + "..."
        like_num = item.get("like", 0)
        like_tag = f"🔥{like_num}赞" if like_num >= 10 else f"{like_num}赞"
        lines.append(f"[{local_i}] ({like_tag}) {clean_text}")
        local_map[str(local_i)] = item["id"]

    chunk_file = os.path.join(chunks_dir, f"{chunk_id}.txt")
    with open(chunk_file, "w", encoding="utf-8") as cf:
        cf.write("\n".join(lines) + "\n")

    chunks_meta.append({
        "chunk_id": chunk_id,
        "file": f"comments/analysis/chunks/{chunk_id}.txt",
        "count": len(items),
        "local_map": local_map,
    })


raw_chunks = []
for c in all_comments:
    text_len = len(c.get("text", ""))
    if cur_items and (len(cur_items) >= CHUNK_MAX_ITEMS or cur_chars + text_len > CHUNK_MAX_CHARS):
        raw_chunks.append(cur_items)
        cur_items = []
        cur_chars = 0
    cur_items.append(c)
    cur_chars += text_len

if cur_items:
    if raw_chunks and len(cur_items) < 60:
        raw_chunks[-1].extend(cur_items)
    else:
        raw_chunks.append(cur_items)

for idx, items in enumerate(raw_chunks, 1):
    flush_chunk(items, idx)

manifest_path = os.path.join(chunks_dir, "manifest.json")
with open(manifest_path, "w", encoding="utf-8") as mf:
    json.dump({
        "total_comments": len(all_comments),
        "total_chunks": len(chunks_meta),
        "chunks": chunks_meta,
    }, mf, ensure_ascii=False, indent=2)

print(f"Total comments: {len(all_comments)}")
official_count = sum(1 for c in all_comments if c["source_label"] == "official")
player_count = sum(1 for c in all_comments if c["source_label"] == "player")
print(f"Official: {official_count}, Players: {player_count}")
print(f"Generated {len(chunks_meta)} chunks in comments/analysis/chunks/ (已清空旧 results/)")


