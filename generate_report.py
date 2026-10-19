import json, os, sys, glob
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
analysis_dir = os.path.join(BASE_DIR, "comments", "analysis")
combined_path = os.path.join(analysis_dir, "all_comments_combined.json")

if not os.path.exists(combined_path):
    print("[ERROR] 未找到 comments/analysis/all_comments_combined.json，请先运行 python prepare_comments.py", file=sys.stderr)
    sys.exit(1)

# 1. 加载全量原始评论
with open(combined_path, "r", encoding="utf-8") as f:
    comments = json.load(f)
if not comments:
    print("[ERROR] all_comments_combined.json 为空，无评论可生成报告。", file=sys.stderr)
    sys.exit(1)

comment_map = {c["id"]: c for c in comments}
total_comments = len(comments)

manifest_path = os.path.join(analysis_dir, "chunks", "manifest.json")
results_dir = os.path.join(analysis_dir, "results")
classified_llm_path = os.path.join(analysis_dir, "classified_llm.json")

dedup = {}
point_counter = defaultdict(lambda: Counter())  # category -> Counter({(sentiment, point): count})
missing_chunks = []

chunk_result_files = glob.glob(os.path.join(results_dir, "chunk_*_result.json"))

# 2. 优先读取指针切块结果 (comments/analysis/results/chunk_*_result.json)
if os.path.exists(manifest_path) and (chunk_result_files or not os.path.exists(classified_llm_path)):
    with open(manifest_path, "r", encoding="utf-8") as mf:
        manifest = json.load(mf)

    for chunk_info in manifest.get("chunks", []):
        cid_str = chunk_info["chunk_id"]
        local_map = chunk_info.get("local_map", {})
        res_file = os.path.join(results_dir, f"{cid_str}_result.json")
        if not os.path.exists(res_file):
            missing_chunks.append(cid_str)
            continue

        try:
            with open(res_file, "r", encoding="utf-8") as rf:
                res_data = json.load(rf)
        except Exception as e:
            print(f"[ERROR] 切块结果 JSON 格式损坏: comments/analysis/results/{cid_str}_result.json ({e})", file=sys.stderr)
            sys.exit(1)

        seen_in_chunk = set()
        opinions = res_data.get("opinions", [])
        for op in opinions:
            sentiment = op.get("sentiment", "neutral")
            if sentiment not in ("positive", "neutral", "negative"):
                sentiment = "neutral"
            category = op.get("category") or op.get("topic") or "其他"
            point = (op.get("point") or op.get("sub_topic") or "").strip()
            indices = op.get("indices") or op.get("evidence_indices") or []

            valid_hits = 0
            for loc_idx in indices:
                global_id = local_map.get(str(loc_idx))
                if global_id is not None and global_id in comment_map and global_id not in seen_in_chunk:
                    seen_in_chunk.add(global_id)
                    dedup[global_id] = {
                        "id": global_id,
                        "sentiment": sentiment,
                        "category": category,
                        "topic": category,
                        "point": point,
                    }
                    valid_hits += 1
            if point and valid_hits > 0:
                point_counter[category][(sentiment, point)] += valid_hits

    if missing_chunks:
        print(
            f"[ERROR] 尚有 {len(missing_chunks)} 个切块未生成分析结果: {', '.join(missing_chunks)}\n"
            f"请先按 SKILL.md 规范输出 comments/analysis/results/<chunk_id>_result.json 后再运行本脚本。",
            file=sys.stderr,
        )
        sys.exit(2)

    # 高赞防漏校验：检查点赞 >= 10 的评论是否被遗漏
    uncovered_high_likes = []
    for chunk_info in manifest.get("chunks", []):
        cid_str = chunk_info["chunk_id"]
        for loc_str, global_id in chunk_info.get("local_map", {}).items():
            c_obj = comment_map.get(global_id)
            if c_obj and c_obj.get("like", 0) >= 10 and global_id not in dedup:
                uncovered_high_likes.append((cid_str, loc_str, c_obj["like"], c_obj["text"][:40]))

    if uncovered_high_likes:
        print(f"[WARN] 发现 {len(uncovered_high_likes)} 条高赞评论(>=10赞)未归入观点（已默认归为日常互动/中评）：", file=sys.stderr)
        for cid_str, loc_str, lk, txt in uncovered_high_likes[:10]:
            print(f"  - {cid_str} [{loc_str}] ({lk}赞): {txt}", file=sys.stderr)

elif os.path.exists(classified_llm_path):
    with open(classified_llm_path, "r", encoding="utf-8") as f:
        cls = json.load(f)
    for c in cls:
        cid = c.get("id")
        if cid is not None and not c.get("is_water", False):
            cat = c.get("category") or c.get("topic") or "其他"
            pt = c.get("point", "")
            dedup[cid] = {
                "id": cid,
                "sentiment": c.get("sentiment", "neutral"),
                "category": cat,
                "topic": cat,
                "point": pt,
            }
            if pt:
                point_counter[cat][(c.get("sentiment", "neutral"), pt)] += 1
else:
    print(
        "[ERROR] 未找到切块文件或分类结果，请先运行 python prepare_comments.py 并完成切块分析。",
        file=sys.stderr,
    )
    sys.exit(1)

# 3. 合并回全量评论（未被观点指针命中的评论归为日常互动/水评，情感记为 neutral）
enriched = []
water_comments = []
substantive_comments = []

for c in comments:
    cid = c["id"]
    if cid in dedup:
        item = {**c, **dedup[cid], "is_water": False}
        enriched.append(item)
        substantive_comments.append(item)
    else:
        item = {**c, "sentiment": "neutral", "category": "日常互动/水评", "topic": "日常互动/水评", "point": "", "is_water": True}
        enriched.append(item)
        water_comments.append(item)

pos = [x for x in enriched if x["sentiment"] == "positive"]
neu_sub = [x for x in substantive_comments if x["sentiment"] == "neutral"]
neu_all = [x for x in enriched if x["sentiment"] == "neutral"]
neg = [x for x in enriched if x["sentiment"] == "negative"]

sub_total = len(substantive_comments) or 1
all_total = total_comments or 1

# 4. 统计主题分布（仅统计实质评论）
topic_dist = Counter()
sentiment_topic = defaultdict(lambda: Counter())
for c in substantive_comments:
    t = c.get("topic", "其他")
    s = c.get("sentiment", "neutral")
    topic_dist[t] += 1
    sentiment_topic[s][t] += 1

# 5. 生成可读报告
lines = []
def w(s=""):
    lines.append(s)

w("B站评论区情感与观点分析报告")
w("=" * 55)
w(f"总评论数: {total_comments}")
w(f"  ├─ 实质观点评论: {len(substantive_comments)} ({len(substantive_comments)/all_total*100:.1f}%)")
w(f"  └─ 日常互动/水评: {len(water_comments)} ({len(water_comments)/all_total*100:.1f}%)")
w()
w("【情感占比（以实质观点评论为分母）】")
w(f"  👍 好评: {len(pos):>4} ({len(pos)/sub_total*100:.1f}%)  [占全量 {len(pos)/all_total*100:.1f}%]")
w(f"  ➖ 中评: {len(neu_sub):>4} ({len(neu_sub)/sub_total*100:.1f}%)  [含水评广义中立占全量 {len(neu_all)/all_total*100:.1f}%]")
w(f"  👎 差评: {len(neg):>4} ({len(neg)/sub_total*100:.1f}%)  [占全量 {len(neg)/all_total*100:.1f}%]")
w("=" * 55)
w()

w("=== 主题负面率排行与核心观点明细 ===")
if not topic_dist:
    w("  （当前无实质观点评论）")
for topic, count in topic_dist.most_common(12):
    pct_neg = sentiment_topic["negative"][topic] / count * 100
    pct_pos = sentiment_topic["positive"][topic] / count * 100
    pct_neu = sentiment_topic["neutral"][topic] / count * 100
    bar = "🔴" if pct_neg > 50 else ("🟡" if pct_neg > 20 else "🟢")
    w(f"\n{bar} 【{topic}】 共 {count} 条 (占实质评论 {count/sub_total*100:.1f}% | 好评{pct_pos:.0f}% / 中评{pct_neu:.0f}% / 差评{pct_neg:.0f}%)")
    if topic in point_counter:
        for (s_label, pt), pt_cnt in point_counter[topic].most_common(6):
            s_icon = "👍" if s_label == "positive" else ("👎" if s_label == "negative" else "➖")
            w(f"    • {s_icon} [{pt_cnt}条] {pt}")

w()
for label, c_list, icon in [("好评", pos, "👍"), ("差评", neg, "👎"), ("中评", neu_sub, "➖")]:
    w(f"\n=== {icon} {label}高赞原话 Top 15 ===")
    sorted_list = sorted(c_list, key=lambda x: x.get("like", 0), reverse=True)
    for c in sorted_list[:15]:
        likes = c.get("like", 0)
        topic = c.get("topic", "")
        pt = c.get("point", "")
        tag = f"{topic}·{pt[:18]}" if pt else topic
        text = c.get("text", "").replace("\r", " ").replace("\n", " ")
        src = c.get("source_title", "")[:30]
        src_label = "官方" if c.get("source_label") == "official" else "玩家"
        w(f"[{likes}赞][{tag}] {text[:140]}")
        w(f"  -> 来源({src_label}): {src}")
        w()

report_text = "\n".join(lines)

out_report_path = os.path.join(analysis_dir, "llm_report.txt")
with open(out_report_path, "w", encoding="utf-8") as f:
    f.write(report_text)

with open(classified_llm_path, "w", encoding="utf-8") as f:
    json.dump(enriched, f, ensure_ascii=False, indent=2)

print(f"Report saved to comments/analysis/llm_report.txt", file=sys.stderr)
print(
    f"Total: {total_comments} (实质: {len(substantive_comments)}, 水评: {len(water_comments)}) | "
    f"好评: {len(pos)} ({len(pos)/sub_total*100:.1f}%) | "
    f"中评: {len(neu_sub)} ({len(neu_sub)/sub_total*100:.1f}%) | "
    f"差评: {len(neg)} ({len(neg)/sub_total*100:.1f}%)",
    file=sys.stderr,
)


