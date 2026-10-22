# B站评论抓取与分析 SOP

由小龙整理开发，方便内部同学快速抓取和分析 B站评论区数据。

> 适用场景：抓取 B 站视频评论区 → 情感分类与观点提炼 → 出报告
> 工具栈：Python + httpx + Bilibili API + 宿主 Agent 免 Key 指针切块分析（或可选 DeepSeek / 火山引擎 API）

---

## 目录

1. [前置准备](#1-前置准备)
2. [步骤 A：查找目标视频](#2-步骤-a查找目标视频)
3. [步骤 B：爬取评论区](#3-步骤-b爬取评论区)
4. [步骤 C：合并与短序号切块](#4-步骤-c合并与短序号切块)
5. [步骤 D：情感分类与观点聚类](#5-步骤-d情感分类与观点聚类)
6. [步骤 E：生成报告](#6-步骤-e生成报告)
7. [异常排查索引](#7-异常排查索引)

---

## 1. 前置准备

### 1.1 环境依赖
```bash
pip install httpx
```

### 1.2 获取 SESSDATA（爬取必填）
> **若不提供 SESSDATA，评论区未登录状态只能拉取前 20 条**
```
Chrome → F12 → Application → Cookies → bilibili.com → SESSDATA
```
设置环境变量：
- Bash / macOS / Linux：`export BILI_SESSDATA="你的SESSDATA"`
- Windows PowerShell：`$env:BILI_SESSDATA="你的SESSDATA"`

### 1.3 LLM 额度说明（默认免 API Key）
- **推荐（Agent 免 Key 模式）**：在 WorkBuddy / Claude Code / Antigravity 中直接复用宿主 Agent 内部额度按 [`SKILL.md`](./SKILL.md) 进行指针切块分析，**无需配置任何 API Key**。
- **备选（外部 API Key 模式）**：脱离 Agent 纯命令行跑批或单次处理超大规模评论（>5,000 条）时，可配置 `export DEEPSEEK_API_KEY="sk-xxxxx"` 并运行 `llm_classifier.py`。

---

## 2. 步骤 A：查找目标视频

### 方法 1：直接给 BV 号（最快）
用户提供 B 站视频 URL，提取 BV 号：
```
https://www.bilibili.com/video/BV1icjS6CE16/  →  BV1icjS6CE16
```

### 方法 2：确认视频信息
```bash
python -c "
import httpx, datetime
r = httpx.get('https://api.bilibili.com/x/web-interface/view?bvid=BV1icjS6CE16')
d = r.json()['data']
t = datetime.datetime.fromtimestamp(d['pubdate'])
print(f\"{d['bvid']} | {d['stat']['view']}次 | {d['stat']['reply']}评论 | {t} | {d['title']}\")
"
```

---

## 3. 步骤 B：爬取评论区

### 运行
```bash
python batch_scraper.py BV1xx BV2xx ...              # 玩家/UP主视频 → 自动存入 comments/players/
python batch_scraper.py --official BV3xx ...         # 官方视频 → 自动存入 comments/official/
python batch_scraper.py --compare BV1xx              # 可选：Legacy 与 WBI 双引擎同台对比测试
```
- 支持传入多个 `BV号` 或完整 B 站视频链接，按顺序逐个爬取
- 默认采用 **WBI 动态签名引擎**（异常自动降级 Legacy），单趟最多翻 `250` 页主评论；若第 1 趟（热门排序）已见底（`is_end=True`）则自动免跑第 2 趟（时间排序）
- 楼中楼子回复优先复用主评论内联数据（省去 ~60% 请求），超出部分按需拉取并提前刹车
- 自动创建并保存到 `comments/players/` 或 `comments/official/`

### 关键代码流程
```
get_video_info()            → 获取视频元信息（标题/播放量/AID）
get_top_comments_wbi()      → WBI 签名游标爬取顶级评论（默认最高250页×20条=5000条主评论，含置顶评论）
get_top_comments_legacy()   → 备用旧版主评论引擎（支持 --engine legacy 或自动降级）
get_sub_replies()           → 内联子回复免请求复用 + 超出楼层分页拉取（最高15页/楼，不满20条即停）
run_scrape_pipeline()       → 智能单/双趟调度、按 rpid 去重并统计请求与覆盖率指标
保存 JSON                   → {video, engine, top_level_count, sub_reply_count, total_count, comments}
```

### 验证覆盖率
```bash
python check_stats.py
```
同时扫描 `comments/official/` 与 `comments/players/`，输出覆盖率统计表并保存至 `comments/analysis/stats_report.txt`。

---

## 4. 步骤 C：合并与短序号切块

```bash
python prepare_comments.py
```

1. 将所有 JSON 文件合并为扁平数组 `comments/analysis/all_comments_combined.json`：
   ```json
   [
     {
       "id": 0,
       "text": "评论内容",
       "uname": "用户名",
       "like": 201,
       "source_bvid": "BV1icjS6CE16",
       "source_title": "视频标题",
       "source_label": "official",
       "is_sub_reply": false
     }
   ]
   ```
2. 自动按 **300 条 / 12,000 字** 切分生成 `comments/analysis/chunks/chunk_01.txt ~ chunk_NN.txt` 及 `manifest.json`，并自动清空上一轮残留的 `comments/analysis/results/chunk_*_result.json`。

---

## 5. 步骤 D：情感分类与观点聚类（9大主题 × 6大意图）

### 方式 1：Agent 免 API Key 指针切块模式（默认）
由宿主 Agent（或并发 Subagent）读取 `comments/analysis/chunks/chunk_XX.txt`，合并同类观点后将短序号指针写入 `comments/analysis/results/chunk_XX_result.json`：
```json
{
  "chunk_id": "chunk_01",
  "opinions": [
    {
      "sentiment": "negative",
      "category": "平衡数值",
      "intent": "建言献策",
      "point": "吐槽威龙实战强度垫底并呼吁优化喷气后摇",
      "indices": [1, 3, 14, 22, 45]
    }
  ]
}
```
- **情感极性 (`sentiment`)**：`positive`（好评）/ `neutral`（中评）/ `negative`（差评，含反讽）
- **内容主题 (`category`，9 选 1)**：`视听剧情IP`、`平衡数值`、`玩法内容`、`技术Bug`、`商业化付费`、`运营服务`、`社区社交`、`赛事竞品`、`其他`
- **用户意图 (`intent`，6 选 1)**：`表扬认可`、`玩梗传播`、`咨询考据`、`建言献策`、`吐槽宣泄`、`维权抵制`
- **高赞红线**：带 `🔥` 标记（$\ge 10$ 赞）的评论必须 100% 归入 `opinions` 的 `indices` 中；无意义水评直接略过。

### 方式 2：外部 LLM API Key 模式（备选）
当脱离 Agent 环境或处理超大规模评论时：
```bash
export DEEPSEEK_API_KEY="sk-xxxxx"
python llm_classifier.py
```

---

## 6. 步骤 E：二级指针同义收敛与报告生成（`.md` & `.txt`）

1. **初次运行水化与高赞校验**：
   ```bash
   python generate_report.py
   ```
2. **二级指针全局收敛（当原子观点数 $> 30$ 时）**：
   - 脚本自动导出无偏原子观点清单 `comments/analysis/raw_points.json`（编号 `P001 ~ Pn`）；
   - 由主 Agent 单脑通读并归并为 20~40 个正交标准观点，写入 `comments/analysis/merged_points.json`，再次运行 `python generate_report.py`。
3. **自动产出与标准报告模板**：
   ```
   comments/analysis/
   ├── raw_points.json            ← 跨块原子观点清单 (P001 ~ Pn)
   ├── merged_points.json         ← 二级同义收敛映射表
   ├── classified_llm.json        ← 全量评论 + sentiment/category/intent/point/is_water 标签
   ├── llm_report.md              ← 标准舆情报告 (Markdown 版)
   └── llm_report.txt             ← 标准舆情报告 (纯文本版)
   ```
   最终报告严格遵循 [`report_template.md`](./report_template.md) 与 [`report_template.txt`](./report_template.txt) 的三段式结构：
   - **`# 整体结论`**：双口径并列（全量口径主展示 + 实质口径参考）+ `**好评**` / `**差评**` / `**热门话题**`；
   - **`# 评价观点明细`**：正/中/负 CAD 单句事实分点（无分类前缀，带精确条数 `（X条）`）；
   - **`# 好中差评声量明细`**：入池总数、好评、中评（拆解实质中评与日常水评）、差评 100% 闭合对账。

---

## 7. 异常排查索引

### 🚨 E1：爬取阶段 — 评论数远少于 API 显示数
```
症状：API 显示 1500+ 条，实际只抓到 ~200 条，或终端提示 [WARN] 未检测到有效的 BILI_SESSDATA
原因：BILI_SESSDATA 未配置或已过期，未登录状态只能获取前 20 条
解决：重新从浏览器复制 SESSDATA（注意保留 %2C 等 URL 编码字符），重新注入环境变量后重爬
```

### 🚨 E2：爬取阶段 — API 返回 -799 错误码
```
症状：[WARN] 主评论/楼中楼接口返回异常 (code=-799): 请求太频繁了，请稍后重试
原因：触发 B 站请求频率风控
解决：暂停 5~15 分钟后重试，或调大 batch_scraper.py 中的 sleep 间隔
```

### 🚨 E3：报告阶段 — 提示尚有切块未生成分析结果（退出码 2）
```
症状：[ERROR] 尚有 N 个切块未生成分析结果: chunk_03, chunk_04
原因：comments/analysis/results/ 下缺少对应切块的 JSON 文件
解决：让 Agent 补齐缺失的 chunk_XX_result.json 后重新运行 python generate_report.py
```

### 🚨 E4：报告阶段 — 提示发现高赞评论未归入观点
```
症状：[WARN] 发现 N 条高赞评论(>=10赞)未归入观点
原因：Agent 在聚类时遗漏了部分带 🔥 标记的高赞评论
解决：根据终端打印的 chunk_id 与 [序号]，将对应高赞评论补充进 chunk_XX_result.json 的 opinions 后重跑 generate_report.py
```

### 🚨 E5：备选 API 模式 — 401 / 404 / 429 错误
```
- 401 Unauthorized：DEEPSEEK_API_KEY 无效或未设置
- 404 ModelNotOpen / Not Found：火山引擎控制台未开通对应模型，或 Endpoint 路径未设为 /api/coding/v1/chat/completions
- 429 AccountRateLimitExceeded：触发 API 限流，脚本会自动指数退避重试；若持续限流可将 SLEEP_BETWEEN 调大至 5s
```

---

## 附录：脚本与文件清单

```
工作目录 = bilishare/

核心规范、模板与脚本：
  SKILL.md                     ← Agent Skill 指针切块与报告标准协议（主入口）
  report_template.md           ← B站评论区舆情报告标准模板 (Markdown 版)
  report_template.txt          ← B站评论区舆情报告标准模板 (纯文本版)
  CLAUDE.md                    ← Agent 引导说明
  batch_scraper.py             ← Step 1: 批量爬取评论（支持 --official）
  check_stats.py               ← Step 1+: 查看爬取覆盖率
  prepare_comments.py          ← Step 2: 合并评论并生成短序号切块
  generate_report.py           ← Step 4: 二级指针收敛、高赞校验与报告生成 (.md/.txt)
  llm_classifier.py            ← 备选: 外部 LLM API Key 批量分类

运行时数据目录（自动创建）：
  comments/
    official/                  ← 官方视频评论 JSON
    players/                   ← 玩家视频评论 JSON
    analysis/                  ← 分析产物
      stats_report.txt              ← 爬取覆盖率统计表
      all_comments_combined.json    ← 合并后的全量评论
      chunks/                       ← 短序号切块 chunk_XX.txt 与 manifest.json
      results/                      ← Agent 产出的 chunk_XX_result.json
      raw_points.json               ← 跨切块原子观点清单 (P001 ~ Pn)
      merged_points.json            ← 二级指针同义归并映射表
      classified_llm.json           ← 全量评论 + 分类标签最终底表
      llm_report.md                 ← 最终可读舆情报告 (Markdown 版)
      llm_report.txt                ← 最终可读舆情报告 (纯文本版)
```

