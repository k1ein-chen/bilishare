import json, os, glob

players_dir = "comments/players"

lines = []
files = sorted(glob.glob(os.path.join(players_dir, "*.json")))

lines.append(f"{'#':<3} {'BV号':<18} {'视频标题':<30} {'API总数':<8} {'主评论':<8} {'子回复':<8} {'已抓合计':<8} {'状态':<8}")
lines.append("="*100)

total_api = 0
total_captured = 0

for i, f in enumerate(files, 1):
    with open(f, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    info = data["video"]
    api_total = info["reply"]
    top = data["top_level_count"]
    sub = data["sub_reply_count"]
    captured = data["total_count"]

    rate = captured / api_total * 100 if api_total > 0 else 0
    status = "OK" if rate >= 95 else f"{rate:.0f}%"

    title = info["title"][:28]
    bvid = info["bvid"]

    lines.append(f"{i:<3} {bvid:<18} {title:<30} {api_total:<8} {top:<8} {sub:<8} {captured:<8} {status:<8}")

    total_api += api_total
    total_captured += captured

lines.append("="*100)
lines.append(f"{'':<3} {'合计':<18} {'':<30} {total_api:<8} {'':<8} {'':<8} {total_captured:<8}")
lines.append(f"覆盖率: {total_captured}/{total_api} = {total_captured/total_api*100:.1f}%")

out = "\n".join(lines)
with open("stats_report.txt", "w", encoding="utf-8") as f:
    f.write(out)
print(out)
