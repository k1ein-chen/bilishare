import json, os, sys, glob

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
official_dir = os.path.join(BASE_DIR, "comments", "official")
players_dir = os.path.join(BASE_DIR, "comments", "players")
analysis_dir = os.path.join(BASE_DIR, "comments", "analysis")

file_entries = []
for label, d in [("官方", official_dir), ("玩家", players_dir)]:
    for f in sorted(glob.glob(os.path.join(d, "*.json"))):
        file_entries.append((label, f))

if not file_entries:
    print("[ERROR] 未在 comments/official/ 或 comments/players/ 下找到任何评论 JSON 文件，请先运行 batch_scraper.py", file=sys.stderr)
    sys.exit(1)

lines = []
lines.append(f"{'#':<3} {'来源':<6} {'BV号':<16} {'视频标题':<28} {'API总数':<8} {'主评论':<8} {'子回复':<8} {'已抓合计':<8} {'状态':<8}")
lines.append("=" * 105)

total_api = 0
total_captured = 0

for i, (label, f) in enumerate(file_entries, 1):
    with open(f, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    info = data.get("video", {})
    api_total = info.get("reply", 0)
    top = data.get("top_level_count", 0)
    sub = data.get("sub_reply_count", 0)
    captured = data.get("total_count", top + sub)

    rate = captured / api_total * 100 if api_total > 0 else 100.0
    status = "OK" if rate >= 95 else f"{rate:.0f}%"

    title = info.get("title", "")[:26]
    bvid = info.get("bvid", "")

    lines.append(f"{i:<3} {label:<6} {bvid:<16} {title:<28} {api_total:<8} {top:<8} {sub:<8} {captured:<8} {status:<8}")

    total_api += api_total
    total_captured += captured

overall_rate = (total_captured / total_api * 100) if total_api > 0 else 0.0
lines.append("=" * 105)
lines.append(f"{'':<3} {'合计':<6} {'':<16} {'':<28} {total_api:<8} {'':<8} {'':<8} {total_captured:<8}")
lines.append(f"总覆盖率: {total_captured}/{total_api} = {overall_rate:.1f}%")

out = "\n".join(lines)
os.makedirs(analysis_dir, exist_ok=True)
out_file = os.path.join(analysis_dir, "stats_report.txt")
with open(out_file, "w", encoding="utf-8") as f:
    f.write(out)
print(out)

