---
name: bilishare
description: >-
  B站视频评论区批量抓取与情感观点分析 Skill。无需外部 LLM API Key，直接复用宿主 Agent（WorkBuddy / Claude Code / Antigravity）内部额度，
  通过「双排序全量爬取 -> 自适应短序号切块 -> Agent 指针化观点聚类 -> Python 水化防漏校验与报告导出」四步流水线，
  一键产出好/中/差评占比、主题负面率排行、具体槽点明细与高赞原话 Top 榜。
  适用触发词：B站评论分析、抓取B站评论、BV号评论舆情、bilishare。
---

# BiliShare — B站评论区抓取与指针切块分析 Skill

无需额外购买外部 LLM API Key，直接利用当前 Agent 自身上下文（或并发 Subagent）对 B 站视频评论区进行全量抓取、反讽识别、观点聚类与高赞原话统计。

---

## 标准执行流程（Agent 必读）

### 第一步：收集必要信息（仅需 2 项，无需 API Key）

向用户确认以下两项信息：

1. **目标视频 BV 号**（必填）
   - 支持直接给 BV 号（如 `BV1icjS6CE16`）或 B 站视频链接（从中提取 `BV[a-zA-Z0-9]{10}`）。
   - 支持区分官方视频与玩家/UP主视频：爬取官方视频时传入 `--official` 参数（自动存入 `comments/official/`），普通玩家视频默认存入 `comments/players/`。
2. **B 站 `SESSDATA`**（必填，未登录仅能抓前 20 条）
   - 获取方式：浏览器登录 `bilibili.com` → `F12` → `Application` → `Cookies` → 复制 `SESSDATA` 的值。
   - 拿到后注入环境变量：`export BILI_SESSDATA="用户的SESSDATA"`（Windows PowerShell 使用 `$env:BILI_SESSDATA="..."`）。

---

### 第二步：爬取评论并生成短序号切块

```bash
pip install httpx
python batch_scraper.py BV1xx BV2xx ...              # 抓取玩家/UP主视频评论（存入 comments/players/）
python batch_scraper.py --official BV3xx ...         # 可选：抓取官方视频评论（存入 comments/official/）
python check_stats.py                                # 校验抓取覆盖率（输出至 comments/analysis/stats_report.txt）
python prepare_comments.py                           # 合并去重并生成短序号切块（自动清空旧切块与旧结果）
```

`prepare_comments.py` 会完成两件事：
1. 将所有评论合并为 `comments/analysis/all_comments_combined.json`；
2. 按 **300 条/块（且不超过 12,000 字）** 自动生成极简编号文本 `comments/analysis/chunks/chunk_01.txt` ~ `chunk_NN.txt` 及映射清单 `manifest.json`（同时自动清理上一轮残留的 `results/chunk_*_result.json`）。

---

### 第三步：Agent 指针化切块分析（免 API Key 核心步骤）

遍历 `comments/analysis/chunks/chunk_*.txt`（若宿主环境支持 Subagent 并发，可并发派发 Subagent 分担切块；若为 WorkBuddy 等单窗口环境，逐块读取并写出结果即可）。

对每个 `chunk_XX.txt`，读取其中的 `[序号] (点赞数) 评论内容`，将**有实质内容或明确情感的评论**按相同观点合并同类项，写出到 `comments/analysis/results/chunk_XX_result.json`：

#### 分类与归类规则
1. **情感极性 (`sentiment`)**：
   - `positive`（好评）：表达喜欢、满意、期待、称赞、推荐、认可玩法/美术等正面情感。
   - `neutral`（中评）：客观提问、配置咨询、求激活码/传火、理性建议、无明显情绪的机制讨论。
   - `negative`（差评）：批评、不满、失望、吐槽卡顿/黑屏/排队/外挂/逼氪等负面体验。**注意识别阴阳怪气与反讽**（例如 `"太好玩了，一小时了都没进去"` $\rightarrow$ `negative`）。
2. **一级主题 (`category`)**：
   严格从以下 9 个固定分类中选择：`性能优化`、`游戏性`、`运营活动`、`匹配/社交`、`国服对比`、`收费/氪金`、`画质/音效`、`期待/建议`、`其他`。
3. **二级具体观点 (`point`)**：
   用 10~25 字概括该组评论的具体槽点、痛点或夸赞点（如 `"更新后严重卡顿掉帧及提示文件被篡改"`）。
4. **短序号指针 (`indices`)**：
   填入属于该观点的块内数字编号数组（如 `[1, 3, 14, 22]`）。
   - **高赞必归类红线**：带有 `🔥` 标记（$\ge 10$ 赞）的评论必须 100% 归入某个具体 `opinions` 的 `indices` 中，严禁遗漏。
   - **水评自动豁免**：0 赞或低赞的纯打卡、前排、纯表情、无意义灌水无需写入 `opinions`，汇总脚本会自动将其计入“日常互动/水评”。

#### 输出 JSON 格式（写入 `comments/analysis/results/chunk_XX_result.json`）
```json
{
  "chunk_id": "chunk_01",
  "opinions": [
    {
      "sentiment": "negative",
      "category": "性能优化",
      "point": "更新后出现严重卡顿、掉帧及提示文件被篡改",
      "indices": [1, 3, 14, 22, 45]
    },
    {
      "sentiment": "neutral",
      "category": "运营活动",
      "point": "求传火激活码与询问测试资格发放",
      "indices": [2, 5, 8, 11, 19]
    }
  ]
}
```

---

### 第四步：水化还原、高赞防漏校验与报告生成

当所有 `chunk_XX_result.json` 写入完毕后，运行：

```bash
python generate_report.py
```

- 脚本会自动将局部序号 `[1..N]` 还原为原始评论与点赞数；
- 若终端提示 `[WARN] 发现 N 条高赞评论(>=10赞)未归入观点`，请查看对应序号并补充进对应切块的 `opinions` 后重跑 `python generate_report.py`；
- 最终读取 `comments/analysis/llm_report.txt` 向用户汇报核心结论（情感占比、负面率最高主题及具体槽点、高赞原话 Top 榜）。

---

## 10 秒链路排障速查表

| 阶段 / 报错现象 | 退出码 | 根因定位 | 修复动作 |
| :--- | :---: | :--- | :--- |
| `batch_scraper.py` 提示 `[WARN] 未检测到有效的 BILI_SESSDATA` 或覆盖率仅 ~200 条 | `0` | 未注入 `BILI_SESSDATA` 环境变量或 Cookie 已过期 | 让用户重新从浏览器复制 `SESSDATA` 并设置环境变量后重爬 |
| `batch_scraper.py` 提示 `code=-799` 请求太频繁 | `0`/`1` | 触发 B 站接口高频风控 | 等待 5~10 分钟后重试，或调大脚本内的 `time.sleep` |
| `prepare_comments.py` 报 `未找到任何有效评论数据` | `1` | `comments/official/` 与 `comments/players/` 下无 JSON 或评论数为 0 | 先执行 `python batch_scraper.py <BV号>` |
| `generate_report.py` 报 `尚有 N 个切块未生成分析结果` | `2` | `comments/analysis/results/` 下缺少列出的 `chunk_XX_result.json` | 补齐缺失切块的 JSON 分析结果后重跑 `python generate_report.py` |
| `generate_report.py` 报 `切块结果 JSON 格式损坏` | `1` | 对应 `chunk_XX_result.json` 存在语法错误（如多余逗号或 Markdown 标记） | 修复报错指明的 JSON 文件后重跑 |

---

## 备选模式：外部 API Key 批量跑批（可选）

当评论量超过 5,000 条或脱离 Agent 在纯命令行环境运行时，仍可使用 `llm_classifier.py` 调用外部 DeepSeek / 火山引擎 API：

```bash
export DEEPSEEK_API_KEY="sk-xxx"
python llm_classifier.py
```

