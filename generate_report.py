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
point_counter = defaultdict(lambda: Counter())  # category -> Counter({(sentiment, intent, point): count})
missing_chunks = []

def infer_default_intent(sentiment, category, point):
    if any(k in point for k in ("暗改", "欺诈", "维权", "卸载", "退坑", "举报", "投诉", "12315")):
        return "维权抵制"
    if any(k in point for k in ("梗", "调侃", "整活", "笑", "賀生", "贺生", "祝福", "吸欧气", "打卡", "报到", "报道")):
        return "玩梗传播"
    if any(k in point for k in ("建议", "呼吁", "希望", "献策", "催更", "期待", "请求", "回调")):
        return "建言献策"
    if sentiment == "positive":
        return "表扬认可"
    if sentiment == "negative":
        return "吐槽宣泄"
    return "咨询考据"

chunk_result_files = glob.glob(os.path.join(results_dir, "chunk_*_result.json"))
raw_points_path = os.path.join(analysis_dir, "raw_points.json")
merged_points_path = os.path.join(analysis_dir, "merged_points.json")

# 2. 优先读取指针切块结果 (comments/analysis/results/chunk_*_result.json)
if os.path.exists(manifest_path) and (chunk_result_files or not os.path.exists(classified_llm_path)):
    with open(manifest_path, "r", encoding="utf-8") as mf:
        manifest = json.load(mf)

    atomic_key_to_pid = {}
    atomic_points = {}  # pid -> {"pid", "category", "intent", "sentiment", "point", "gids": []}

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
            intent = (op.get("intent") or "").strip() or infer_default_intent(sentiment, category, point)
            indices = op.get("indices") or op.get("evidence_indices") or []

            matched_gids = []
            for loc_idx in indices:
                global_id = local_map.get(str(loc_idx))
                if global_id is not None and global_id in comment_map and global_id not in seen_in_chunk:
                    seen_in_chunk.add(global_id)
                    matched_gids.append(global_id)

            if point and matched_gids:
                akey = (sentiment, category, point)
                if akey not in atomic_key_to_pid:
                    pid = f"P{len(atomic_key_to_pid) + 1:03d}"
                    atomic_key_to_pid[akey] = pid
                    atomic_points[pid] = {
                        "pid": pid,
                        "category": category,
                        "intent": intent,
                        "sentiment": sentiment,
                        "point": point,
                        "gids": [],
                    }
                atomic_points[atomic_key_to_pid[akey]]["gids"].extend(matched_gids)

    if missing_chunks:
        print(
            f"[ERROR] 尚有 {len(missing_chunks)} 个切块未生成分析结果: {', '.join(missing_chunks)}\n"
            f"请先按 SKILL.md 规范输出 comments/analysis/results/<chunk_id>_result.json 后再运行本脚本。",
            file=sys.stderr,
        )
        sys.exit(2)

    # 导出无偏原子观点清单 (隐去条数防大模型注意力偏见)
    raw_points_export = [
        {
            "pid": item["pid"],
            "category": item["category"],
            "intent": item["intent"],
            "sentiment": item["sentiment"],
            "point": item["point"],
        }
        for item in atomic_points.values()
    ]
    with open(raw_points_path, "w", encoding="utf-8") as rpf:
        json.dump(raw_points_export, rpf, ensure_ascii=False, indent=2)

    # 检测是否存在二级同义归并表 merged_points.json
    pid_override = {}
    if os.path.exists(merged_points_path):
        try:
            with open(merged_points_path, "r", encoding="utf-8") as mpf:
                merged_data = json.load(mpf)
            merged_list = merged_data.get("merged_opinions", merged_data) if isinstance(merged_data, dict) else merged_data
        except Exception as e:
            print(f"[ERROR] 二次归并文件 JSON 格式损坏: comments/analysis/merged_points.json ({e})", file=sys.stderr)
            sys.exit(1)

        seen_pids = set()
        for m_op in merged_list:
            m_cat = m_op.get("category") or "其他"
            m_sent = m_op.get("sentiment") or "neutral"
            if m_sent not in ("positive", "neutral", "negative"):
                m_sent = "neutral"
            m_pt = (m_op.get("point") or "").strip()
            m_intent = (m_op.get("intent") or "").strip() or infer_default_intent(m_sent, m_cat, m_pt)
            for pid in m_op.get("pids", []):
                if pid in atomic_points and pid not in seen_pids:
                    seen_pids.add(pid)
                    pid_override[pid] = {
                        "category": m_cat,
                        "intent": m_intent,
                        "sentiment": m_sent,
                        "point": m_pt,
                    }

        uncovered_pids = [p for p in atomic_points if p not in seen_pids]
        if uncovered_pids:
            print(
                f"[WARN] merged_points.json 遗漏了 {len(uncovered_pids)} 个原子编号 ({', '.join(uncovered_pids[:8])}...)，已自动保留其原始归类确保 100% 守恒。",
                file=sys.stderr,
            )
        else:
            print(
                f"[INFO] 已加载 merged_points.json：将 {len(atomic_points)} 个跨块原子观点 100% 无损收敛为 {len(merged_list)} 个标准观点。",
                file=sys.stderr,
            )
    elif len(atomic_points) > 30:
        print(
            f"[INFO] 当前共有 {len(atomic_points)} 个跨切块原子观点（已导出至 comments/analysis/raw_points.json）。\n"
            f"       如需消除跨块同义词发散，请将其归并输出至 comments/analysis/merged_points.json 后重跑本脚本。",
            file=sys.stderr,
        )

    # 水化映射回底层评论 ID
    for pid, info in atomic_points.items():
        final_meta = pid_override.get(pid, info)
        cat = final_meta["category"]
        intent = final_meta["intent"]
        sent = final_meta["sentiment"]
        pt = final_meta["point"]
        gids = info["gids"]
        for gid in gids:
            dedup[gid] = {
                "id": gid,
                "sentiment": sent,
                "category": cat,
                "topic": cat,
                "intent": intent,
                "point": pt,
            }
        if pt and gids:
            point_counter[cat][(sent, intent, pt)] += len(gids)

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
            sent = c.get("sentiment", "neutral")
            pt = c.get("point", "")
            intent = c.get("intent") or infer_default_intent(sent, cat, pt)
            dedup[cid] = {
                "id": cid,
                "sentiment": sent,
                "category": cat,
                "topic": cat,
                "intent": intent,
                "point": pt,
            }
            if pt:
                point_counter[cat][(sent, intent, pt)] += 1
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
        item = {**c, "sentiment": "neutral", "category": "日常互动/水评", "topic": "日常互动/水评", "intent": "日常水评", "point": "", "is_water": True}
        enriched.append(item)
        water_comments.append(item)

pos = [x for x in enriched if x["sentiment"] == "positive"]
neu_sub = [x for x in substantive_comments if x["sentiment"] == "neutral"]
neu_all = [x for x in enriched if x["sentiment"] == "neutral"]
neg = [x for x in enriched if x["sentiment"] == "negative"]

sub_total = len(substantive_comments) or 1
all_total = total_comments or 1

# 4. 统计主题与意图分布（仅统计实质评论）
topic_dist = Counter()
intent_dist = Counter()
sentiment_topic = defaultdict(lambda: Counter())
for c in substantive_comments:
    t = c.get("topic", "其他")
    it = c.get("intent", "咨询考据")
    s = c.get("sentiment", "neutral")
    topic_dist[t] += 1
    intent_dist[it] += 1
    sentiment_topic[s][t] += 1

# 5. 生成可读报告（BiliShare 标准版）
lines = []
def w(s=""):
    lines.append(s)

main_cnt = sum(1 for c in comments if not c.get("is_sub_reply", False))
sub_reply_cnt = total_comments - main_cnt

pct_pos_all = len(pos) / all_total * 100
pct_neu_all = len(neu_all) / all_total * 100
pct_neg_all = len(neg) / all_total * 100
pct_non_neg_all = 100.0 - pct_neg_all

pct_pos_sub = len(pos) / sub_total * 100
pct_neu_sub = len(neu_sub) / sub_total * 100
pct_neg_sub = len(neg) / sub_total * 100
pct_non_neg_sub = 100.0 - pct_neg_sub

w("# B站评论区舆情分析报告")
w()
w("# 整体结论")
w(f"本期纳入分析有效评论 {total_comments} 条（含实质观点评论 {len(substantive_comments)} 条、日常互动与水评 {len(water_comments)} 条），评论区整体舆情以正面/中性/负面为主：")
w(f"- 全量口径（含水评归入广义中立）：好评 {pct_pos_all:.0f}%（{pct_pos_all:.1f}%）、中评 {pct_neu_all:.0f}%（{pct_neu_all:.1f}%）、差评 {pct_neg_all:.0f}%（{pct_neg_all:.1f}%），非负评价 {pct_non_neg_all:.0f}%（{pct_non_neg_all:.1f}%）；")
w(f"- 实质口径（仅以实质观点评论为分母）：好评 {pct_pos_sub:.0f}%（{pct_pos_sub:.1f}%）、中评 {pct_neu_sub:.0f}%（{pct_neu_sub:.1f}%）、差评 {pct_neg_sub:.0f}%（{pct_neg_sub:.1f}%），非负评价 {pct_non_neg_sub:.0f}%（{pct_non_neg_sub:.1f}%）。")
w()
w("**好评**：【请根据下方正面观点简要汇总核心正向认可点】")
w("**差评**：【请根据下方负面观点简要汇总核心吐槽点】")
w("**热门话题**：【请用1个短段落概括高声量讨论话题、玩梗方向与主要诉求】")
w()

# 按正/中/负归集所有观点
sentiment_points = defaultdict(Counter)
for cat, cnt_map in point_counter.items():
    for (s_label, it_label, pt), pt_cnt in cnt_map.items():
        sentiment_points[s_label][pt] += pt_cnt

w("# 评价观点明细")
w(
    f"本期主评与楼中楼子回复总数为 {total_comments} 条（实质观点 {len(substantive_comments)} 条、日常水评 {len(water_comments)} 条），"
    f"全量口径好评 {pct_pos_all:.0f}%、中评 {pct_neu_all:.0f}%、差评 {pct_neg_all:.0f}%"
    f"（实质口径好评 {pct_pos_sub:.1f}%、中评 {pct_neu_sub:.1f}%、差评 {pct_neg_sub:.1f}%）"
)
w()
w("-正面观点集中在：")
for idx, (pt, cnt) in enumerate(sentiment_points["positive"].most_common(), 1):
    w(f"{idx}. {pt}（{cnt}条）")
w()
w("-中性观点集中为：")
for idx, (pt, cnt) in enumerate(sentiment_points["neutral"].most_common(), 1):
    w(f"{idx}. {pt}（{cnt}条）")
w()
w("-负面观点集中为：")
for idx, (pt, cnt) in enumerate(sentiment_points["negative"].most_common(), 1):
    w(f"{idx}. {pt}（{cnt}条）")
w()

w("# 好中差评声量明细")
w(f"- 舆情总数：{total_comments} 条（主评论 {main_cnt} 条、子回复 {sub_reply_cnt} 条）")
w(f"- 好评：{len(pos)} 条")
w(f"- 中评：{len(neu_all)} 条（含实质中评 {len(neu_sub)} 条、日常互动与水评 {len(water_comments)} 条）")
w(f"- 差评：{len(neg)} 条")

report_text = "\n".join(lines) + "\n"

for ext in ("txt", "md"):
    out_report_path = os.path.join(analysis_dir, f"llm_report.{ext}")
    with open(out_report_path, "w", encoding="utf-8") as f:
        f.write(report_text)

with open(classified_llm_path, "w", encoding="utf-8") as f:
    json.dump(enriched, f, ensure_ascii=False, indent=2)

print("Report saved to comments/analysis/llm_report.md & comments/analysis/llm_report.txt", file=sys.stderr)
print(
    f"Total: {total_comments} (实质: {len(substantive_comments)}, 水评: {len(water_comments)}) | "
    f"全量口径 好/中/差: {pct_pos_all:.1f}%/{pct_neu_all:.1f}%/{pct_neg_all:.1f}% | "
    f"实质口径 好/中/差: {pct_pos_sub:.1f}%/{pct_neu_sub:.1f}%/{pct_neg_sub:.1f}%",
    file=sys.stderr,
)


