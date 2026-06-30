import json, os, glob

players_dir = "comments/players"
official_dir = "comments/official"

all_comments = []
cid = 0

for label, d in [("official", official_dir), ("player", players_dir)]:
    files = sorted(glob.glob(os.path.join(d, "*.json")))
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        bvid = data["video"]["bvid"]
        title = data["video"]["title"]
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

outpath = "comments/analysis/all_comments_combined.json"
os.makedirs(os.path.dirname(outpath), exist_ok=True)
with open(outpath, "w", encoding="utf-8") as f:
    json.dump(all_comments, f, ensure_ascii=False, indent=2)

print(f"Total comments: {len(all_comments)}")
official_count = sum(1 for c in all_comments if c["source_label"] == "official")
player_count = sum(1 for c in all_comments if c["source_label"] == "player")
print(f"Official: {official_count}, Players: {player_count}")
