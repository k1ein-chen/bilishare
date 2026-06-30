import json, os
from collections import Counter, defaultdict

# Load all comments and classifications
with open("comments/analysis/all_comments_combined.json", "r", encoding="utf-8") as f:
    comments = json.load(f)
comment_map = {c["id"]: c for c in comments}

with open("comments/analysis/classifications.json", "r", encoding="utf-8") as f:
    cls = json.load(f)

# Dedup
dedup = {}
for c in cls:
    cid = c.get("id")
    if cid is not None:
        dedup[cid] = c
classifications = list(dedup.values())

# Enrich with original comment data
enriched = []
for c in classifications:
    cid = c.get("id")
    if cid in comment_map:
        enriched.append({**c, **comment_map[cid]})
    else:
        enriched.append(c)

total = len(enriched)
pos = [x for x in enriched if x.get("sentiment") == "positive"]
neu = [x for x in enriched if x.get("sentiment") == "neutral"]
neg = [x for x in enriched if x.get("sentiment") == "negative"]

# Topic distribution by sentiment
sentiment_topic = defaultdict(lambda: Counter())
for c in enriched:
    sentiment_topic[c.get("sentiment", "unknown")][c.get("topic", "其他")] += 1

# Build report
lines = []
def w(s=""):
    lines.append(s)

w("=== 情感分析数据 ===")
w(f"总评论数(含API): 2134")
w(f"已分类评论数: {total}")
w(f"好评: {len(pos)} ({len(pos)/total*100:.1f}%)")
w(f"中评: {len(neu)} ({len(neu)/total*100:.1f}%)")
w(f"差评: {len(neg)} ({len(neg)/total*100:.1f}%)")
w()

w("=== 各情感主题分布 ===")
for sentiment, label in [("positive","好评"), ("neutral","中评"), ("negative","差评")]:
    w(f"\n{label}主题分布:")
    for topic, count in sentiment_topic[sentiment].most_common(10):
        w(f"  {topic}: {count}条 ({count/total*100:.1f}%)")

w()
w("=== 好评 Top 20 ===")
pos_sorted = sorted(pos, key=lambda x: x.get("like", 0), reverse=True)
for c in pos_sorted[:20]:
    likes = c.get("like", 0)
    topic = c.get("topic", "")
    text = c.get("text", "")
    src = c.get("source_title", "")[:35]
    label = c.get("source_label", "")
    w(f"[{likes}赞][{topic}] {text}")
    w(f"  -> 来源({label}): {src}")
    w()

w()
w("=== 差评 Top 20 ===")
neg_sorted = sorted(neg, key=lambda x: x.get("like", 0), reverse=True)
for c in neg_sorted[:20]:
    likes = c.get("like", 0)
    topic = c.get("topic", "")
    text = c.get("text", "")
    src = c.get("source_title", "")[:35]
    label = c.get("source_label", "")
    w(f"[{likes}赞][{topic}] {text}")
    w(f"  -> 来源({label}): {src}")
    w()

w()
w("=== 中评 Top 15 ===")
neu_sorted = sorted(neu, key=lambda x: x.get("like", 0), reverse=True)
for c in neu_sorted[:15]:
    likes = c.get("like", 0)
    topic = c.get("topic", "")
    text = c.get("text", "")
    src = c.get("source_title", "")[:35]
    label = c.get("source_label", "")
    w(f"[{likes}赞][{topic}] {text}")
    w(f"  -> 来源({label}): {src}")
    w()

report_text = "\n".join(lines)

# Save to file
outpath = "comments/analysis/sentiment_report.txt"
with open(outpath, "w", encoding="utf-8") as f:
    f.write(report_text)

# Also save enriched data
with open("comments/analysis/enriched_classifications.json", "w", encoding="utf-8") as f:
    json.dump(enriched, f, ensure_ascii=False, indent=2)

# Print summary to stderr
import sys
print(f"Report saved to {outpath}", file=sys.stderr)
print(f"Total: {total} | 好评: {len(pos)} ({len(pos)/total*100:.1f}%) | 中评: {len(neu)} ({len(neu)/total*100:.1f}%) | 差评: {len(neg)} ({len(neg)/total*100:.1f}%)", file=sys.stderr)
