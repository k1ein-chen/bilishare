"""
B站评论 LLM 情感分类器
使用 DeepSeek API（https://api.deepseek.com）批量分类，性价比高
"""
import json, os, httpx, time, sys
from collections import Counter, defaultdict

# ====== 配置 ======
# 推荐使用 DeepSeek API：https://platform.deepseek.com → 创建 API Key
# 火山引擎 Ark Coding Plan 也兼容，API_URL 替换为：
#   https://ark.cn-beijing.volces.com/api/coding/v1/chat/completions
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "your_api_key_here")
MODEL = "deepseek-chat"  # DeepSeek 官方 API 的模型名
API_URL = "https://api.deepseek.com/chat/completions"

# 如果用火山引擎 Ark，改为：
# API_URL = "https://ark.cn-beijing.volces.com/api/coding/v1/chat/completions"
# MODEL = "deepseek-v4-flash"

BATCH_SIZE = 40   # 每批条数
SLEEP_BETWEEN = 3  # 批次间隔(秒)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}

# ====== 加载数据 ======
with open("comments/analysis/all_comments_combined.json", "r", encoding="utf-8") as f:
    comments = json.load(f)
print(f"总评论数: {len(comments)}")

# ====== 批量分类 ======
SYSTEM_PROMPT = """你是一个专业的游戏评论情感分析专家。分析以下B站评论，判断每条评论的情感倾向。

规则：
1. 好评 (positive)：表达喜欢、满意、期待、称赞、推荐等正面情感
2. 中评 (neutral)：中立意见、客观提问、建议反馈、一般性讨论、混合评价
3. 差评 (negative)：批评、不满、失望、吐槽bug/卡顿/服务器等负面体验

注意识别反讽（如"太好玩了，一小时了都没进去"→差评）、梗、游戏黑话。

同时判断每条评论的主题：
- 性能优化：服务器、卡顿、黑屏、排队、掉帧、配置等
- 游戏性：玩法、平衡、操作、地图、AI、难度等
- 运营活动：测试资格、公测、活动、福利、更新等
- 匹配/社交：匹配、队友、单排、人机、社交等
- 国服对比：腾讯代理、国际服、国服改动等
- 收费/氪金：价格、付费、内购、皮肤等
- 画质/音效：画面、美术、音乐、音效等
- 期待/建议：建议、期待、希望等
- 其他：不属于以上分类的

输出格式为JSON数组，每个元素：{"id": 数字id, "sentiment": "positive/neutral/negative", "topic": "主题名"}
只输出JSON，不要其他文字。"""

def classify_batch(batch):
    """调用API分类一批评论"""
    texts = []
    for c in batch:
        texts.append(f'{{"id": {c["id"]}, "text": "{c.get("text","")[:300].replace(chr(34),chr(39)).replace(chr(10),chr(32)).replace(chr(13),chr(32))}"}}')

    user_content = "请分析以下评论：\n" + "\n".join(texts)

    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.0,
        "max_tokens": 4096,
    }

    for attempt in range(5):
        try:
            print(f"    API调用 attempt {attempt+1}/5...", file=sys.stderr)
            r = httpx.post(API_URL, headers=HEADERS, json=body, timeout=60)
            if r.status_code == 429:
                # 限流，指数退避
                wait = min(2 ** attempt * 2, 30)
                print(f"  429限流，等待 {wait}s 后重试...", file=sys.stderr)
                time.sleep(wait)
                continue
            if r.status_code != 200:
                print(f"  API错误: {r.status_code} {r.text[:200]}", file=sys.stderr)
                time.sleep(2)
                continue
            resp = r.json()
            content = resp["choices"][0]["message"]["content"].strip()

            # 提取JSON
            # 移除可能的 markdown 代码块标记
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content.rsplit("```", 1)[0]
            content = content.strip()
            if "```json" in content:
                content = content.replace("```json", "").replace("```", "").strip()

            results = json.loads(content)
            if isinstance(results, list):
                return results
            elif isinstance(results, dict) and "results" in results:
                return results["results"]
        except Exception as e:
            print(f"  尝试{attempt+1}失败: {e}", file=sys.stderr)
            time.sleep(3)

    # 失败返回空
    return []

# ====== 分批处理 ======
all_results = {}
total_batches = (len(comments) + BATCH_SIZE - 1) // BATCH_SIZE

for i in range(0, len(comments), BATCH_SIZE):
    batch = comments[i:i+BATCH_SIZE]
    batch_num = i // BATCH_SIZE + 1

    print(f"[{batch_num}/{total_batches}] 处理第 {i+1}-{min(i+BATCH_SIZE, len(comments))} 条...", file=sys.stderr)

    results = classify_batch(batch)
    for r in results:
        cid = r.get("id")
        if cid is not None:
            all_results[cid] = {
                "sentiment": r.get("sentiment", "neutral"),
                "topic": r.get("topic", "其他"),
            }

    # 保存进度
    if batch_num % 5 == 0:
        with open("comments/analysis/classify_progress.json", "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False)

    print(f"  -> 累计完成: {len(all_results)}/{len(comments)}", file=sys.stderr)
    time.sleep(SLEEP_BETWEEN)

# ====== 合并结果 ======
print(f"\n分类完成: {len(all_results)}/{len(comments)}", file=sys.stderr)

for c in comments:
    cid = c["id"]
    if cid in all_results:
        c["sentiment"] = all_results[cid]["sentiment"]
        c["topic"] = all_results[cid]["topic"]
    else:
        c["sentiment"] = "neutral"
        c["topic"] = "其他"

# ====== 统计 ======
total = len(comments)
pos = [c for c in comments if c["sentiment"] == "positive"]
neu = [c for c in comments if c["sentiment"] == "neutral"]
neg = [c for c in comments if c["sentiment"] == "negative"]

print(f"\n{'='*50}")
print(f"总评论数: {total}")
print(f"好评: {len(pos):>4} ({len(pos)/total*100:.1f}%)")
print(f"中评: {len(neu):>4} ({len(neu)/total*100:.1f}%)")
print(f"差评: {len(neg):>4} ({len(neg)/total*100:.1f}%)")
print(f"{'='*50}")

sentiment_topic = defaultdict(lambda: Counter())
topic_dist = Counter()
for c in comments:
    sentiment_topic[c["sentiment"]][c["topic"]] += 1
    topic_dist[c["topic"]] += 1

for sentiment, label in [("positive","好评"), ("neutral","中评"), ("negative","差评")]:
    print(f"\n{label}主题分布:")
    for topic, count in sentiment_topic[sentiment].most_common(10):
        print(f"  {topic}: {count}条 ({count/total*100:.1f}%)")

# ====== 保存 ======
with open("comments/analysis/classified_llm.json", "w", encoding="utf-8") as f:
    json.dump(comments, f, ensure_ascii=False, indent=2)
print(f"\n已保存: comments/analysis/classified_llm.json")

# ====== 生成报告 ======
lines = []
lines.append(f"B站评论区情感分析报告 (LLM分类)")
lines.append(f"{'='*50}")
lines.append(f"总评论数: {total}")
lines.append(f"好评: {len(pos)} ({len(pos)/total*100:.1f}%)")
lines.append(f"中评: {len(neu)} ({len(neu)/total*100:.1f}%)")
lines.append(f"差评: {len(neg)} ({len(neg)/total*100:.1f}%)")
lines.append("")

# 主题负面率
lines.append("=== 主题负面率排行 ===")
for topic, count in topic_dist.most_common(10):
    pct_neg = sum(1 for c in comments if c["topic"]==topic and c["sentiment"]=="negative") / count * 100
    pct_pos = sum(1 for c in comments if c["topic"]==topic and c["sentiment"]=="positive") / count * 100
    bar = "🔴" if pct_neg > 50 else ("🟡" if pct_neg > 20 else "🟢")
    lines.append(f"{bar} {topic}: {count}条 (好评{pct_pos:.0f}%/差评{pct_neg:.0f}%)")

lines.append("")
for label, c_list, icon in [("👍 好评", pos, "👍"), ("👎 差评", neg, "👎"), ("➖ 中评", neu, "➖")]:
    lines.append(f"\n=== {icon} {label} Top15 ===")
    sorted_list = sorted(c_list, key=lambda x: x.get("like", 0), reverse=True)
    for c in sorted_list[:15]:
        likes = c.get("like", 0)
        topic = c.get("topic", "")
        text = c.get("text", "")
        src_title = c.get("source_title", "")[:25]
        src_label = "官方" if c.get("source_label") == "official" else "玩家"
        lines.append(f"[{likes}赞][{topic}] {text[:120]}")
        lines.append(f"  -> ({src_label}) {src_title}")
        lines.append("")

with open("comments/analysis/llm_report.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(lines))
print(f"已保存: comments/analysis/llm_report.txt")
