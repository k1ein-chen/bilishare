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

#### 分类与归类规则（9 大内容主题 × 6 大用户意图 二维正交体系）
1. **情感极性 (`sentiment`)**：
   - `positive`（好评）：表达喜欢、满意、期待、称赞、推荐、认可玩法/美术等正面情感。
   - `neutral`（中评）：客观提问、世界观考据、配置咨询、求激活码/传火、理性建议、无明显负面情绪的机制讨论。
   - `negative`（差评）：批评、不满、失望、吐槽强度垫底/卡顿/黑屏/排队/外挂/逼氪等负面体验。**注意识别阴阳怪气与反讽**（例如 `"动画这么帅，在游戏里一定很强吧"` $\rightarrow$ `negative`）。
2. **内容主题 (`category`，回答“聊什么”，严格 9 选 1)**：
   - `视听剧情IP`：PV动画水准、角色建模特效、配音音乐、人物背景设定、世界观时间线考据、现实致敬共鸣。
   - `平衡数值`：干员/角色/武器强度梯队、技能 CD 与前后摇、数值削弱/加强诉求。
   - `玩法内容`：核心模式机制（摸金撤离/全面战场等）、地图关卡设计、受击反馈与操作手感。
   - `技术Bug`：客户端帧率卡顿、闪退黑屏、内存/包体大小、穿模断触、反作弊/外挂与误封。
   - `商业化付费`：商城皮肤品质与定价、抽卡/开箱点券爆率、通行证性价比、逼氪争议。
   - `运营服务`：周年庆/节假日福利活动、测试资格发放、暗改机制争议、官方宣发与运营态度。
   - `社区社交`：组队匹配机制、撤离点环境、玩家/老兵打卡互动、社区风气与引战乱象。
   - `赛事竞品`：职业比赛出场率、跨游戏对比、国际服/国服差异、版号政策。
   - `其他`：与游戏及视频内容完全无关的纯场外话题（如评论区求生日祝福）。
3. **用户意图 (`intent`，回答“想干嘛”，严格 6 选 1)**：
   - `表扬认可`：夸赞动画水准、认可角色塑造、支持官方制作组。
   - `玩梗传播`：造梗、名场面复读、谐音梗、欧皇晒卡吸欧气、打卡接龙。
   - `咨询考据`：设定细节推演、军衔/现实常识考据、问配置、求资格。
   - `建言献策`：提出具体技能改良方案、呼吁加强/回调、催更功能或新CG。
   - `吐槽宣泄`：抱怨角色弱势、吐槽匹配连败、反讽策划不玩游戏。
   - `维权抵制`：🚨 **高危客诉预警**（指控暗改欺诈、呼吁退坑卸载、12315投诉举报）。
4. **二级具体观点 (`point`)**：
   用 10~25 字简明动宾短语概括具体观点（如 `"吐槽威龙实战强度垫底并呼吁优化喷气后摇"`）。
5. **短序号指针 (`indices`)**：
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
      "category": "平衡数值",
      "intent": "建言献策",
      "point": "吐槽威龙实战强度垫底并呼吁优化喷气后摇",
      "indices": [1, 3, 14, 22, 45]
    },
    {
      "sentiment": "positive",
      "category": "视听剧情IP",
      "intent": "表扬认可",
      "point": "盛赞威龙个人角色PV电影级视听与叙事水准",
      "indices": [2, 5, 8, 11, 19]
    }
  ]
}
```

---

### 第四步：水化还原、二级指针同义收敛与标准报告生成

1. **运行初次汇总与高赞校验**：
   ```bash
   python generate_report.py
   ```
   - 若终端提示 `[WARN] 发现 N 条高赞评论(>=10赞)未归入观点`，请补充进对应切块的 `opinions` 后重跑。
2. **二级指针全局同义收敛（当切块较多、原子观点数 $> 30$ 时执行）**：
   - `generate_report.py` 会自动导出脱敏去条数的原子观点清单 `comments/analysis/raw_points.json`（编号 `P001 ~ Pn`）。
   - **主 Agent 单脑全局归并**：直接读取 `raw_points.json`，将跨切块同义表达合并为 20~40 个正交标准观点（单句事实陈述，差评统一用“吐槽”，好评不用浮夸副词，中评含诉求闭环），并校准 `category`（9大主题）与 `intent`（6大意图），写出至 `comments/analysis/merged_points.json`（确保 `P001 ~ Pn` 100% 全覆盖无遗漏）：
     ```json
     [
       {
         "category": "视听剧情IP",
         "intent": "表扬认可",
         "sentiment": "positive",
         "point": "玩家认可威龙个人角色PV的视听质感与叙事表现，肯定制作水准",
         "pids": ["P001", "P012", "P045"]
       }
     ]
     ```
   - **重跑生成底表**：再次运行 `python generate_report.py`，自动完成 100% 声量守恒水化并输出 `comments/analysis/llm_report.md` 与 `comments/analysis/llm_report.txt`。
3. **按标准模板输出最终舆情报告（`.md` 与 `.txt` 各一份）**：
   - 严格按照根目录下的 [`report_template.md`](./report_template.md) 与 [`report_template.txt`](./report_template.txt) 规范，补齐 `# 整体结论` 中的 `**好评**`、`**差评**`、`**热门话题**` 三段综述，同时保存 `.md` 与 `.txt` 两份定稿报告并向用户展示：
   - **报告排版与口径红线**：
     - **双口径并列**：同时展示**全量口径**（含水评归入广义中立，主口径）与**实质口径**（仅以实质观点评论为分母）；
     - **无前缀分点**：`-正面观点集中在：`、`-中性观点集中为：`、`-负面观点集中为：` 下直接写 `1. 【CAD单句事实陈述】（X条）`，**不加 `[主题·意图]` 前缀**；
     - **精简三模块**：仅保留 `# 整体结论`、`# 评价观点明细`、`# 好中差评声量明细` 三大模块（不含海外部分、不含话题拆解模块、不含重点关注预警模块、不含末尾原话堆砌）。

```markdown
# 《游戏/视频名称》B站评论区舆情报告

> 日期：YYYY年M月D日
> 监测标的：《视频标题》（BV号，播放量 XX 万，API 评论 XX 条，实际入池 XX 条，覆盖率 XX%）

# 整体结论
本期纳入分析有效评论 N 条（含实质观点评论 M 条、日常互动与水评 K 条），评论区整体舆情以正面/中性/负面为主：
- 全量口径（含水评归入广义中立）：好评 X%（X.X%）、中评 X%（X.X%）、差评 X%（X.X%），非负评价 X%（X.X%）；
- 实质口径（仅以实质观点评论为分母）：好评 X%（X.X%）、中评 X%（X.X%）、差评 X%（X.X%），非负评价 X%（X.X%）。

**好评**：【简要汇总玩家的核心正向认可点】
**差评**：【简要汇总玩家的核心吐槽点】
**热门话题**：【用1个短段落概括高声量讨论话题、玩梗方向与主要诉求；不展开具体条数】

# 评价观点明细
本期主评与楼中楼子回复总数为 N 条（实质观点 M 条、日常水评 K 条），全量口径好评 X%、中评 X%、差评 X%（实质口径好评 X.X%、中评 X.X%、差评 X.X%）

-正面观点集中在：
1. 【CAD单句事实陈述】（X条）

-中性观点集中为：
1. 【CAD单句事实陈述 + 诉求闭环】（X条）

-负面观点集中为：
1. 【CAD单句事实陈述，统一用“吐槽”】（X条）

# 好中差评声量明细
- 舆情总数：N 条（主评论 X 条、子回复 Y 条）
- 好评：X 条
- 中评：X 条（含实质中评 X 条、日常互动与水评 K 条）
- 差评：X 条
```

---

## 10 秒链路排障速查表

| 阶段 / 报错现象 | 退出码 | 根因定位 | 修复动作 |
| :--- | :---: | :--- | :--- |
| `batch_scraper.py` 提示 `[WARN] 未检测到有效的 BILI_SESSDATA` 或覆盖率仅 ~200 条 | `0` | 未注入 `BILI_SESSDATA` 环境变量或 Cookie 已过期 | 让用户重新从浏览器复制 `SESSDATA` 并设置环境变量后重爬 |
| `batch_scraper.py` 提示 `code=-799` 请求太频繁 | `0`/`1` | 触发 B 站接口高频风控 | 等待 5~10 分钟后重试，或调大脚本内的 `time.sleep` |
| `prepare_comments.py` 报 `未找到任何有效评论数据` | `1` | `comments/official/` 与 `comments/players/` 下无 JSON 或评论数为 0 | 先执行 `python batch_scraper.py <BV号>` |
| `generate_report.py` 报 `尚有 N 个切块未生成分析结果` | `2` | `comments/analysis/results/` 下缺少列出的 `chunk_XX_result.json` | 补齐缺失切块的 JSON 分析结果后重跑 `python generate_report.py` |
| `generate_report.py` 报 `切块结果/二次归并文件 JSON 格式损坏` | `1` | `chunk_XX_result.json` 或 `merged_points.json` 存在语法错误 | 修复报错指明的 JSON 文件后重跑 |
| `generate_report.py` 提示 `[WARN] merged_points.json 遗漏了 N 个原子编号` | `0` | 二次归并时漏掉了部分 `Pxxx` 编号（脚本已自动保留原观点兜底） | 将提示的 `Pxxx` 补入 `merged_points.json` 对应分类后重跑 |
| `generate_report.py` 提示 `[WARN] 发现 N 条高赞评论(>=10赞)未归入观点` | `0` | 切块聚类时遗漏了带 `🔥` 的高赞评论 | 按提示的 `chunk_id [序号]` 补入对应 `chunk_XX_result.json` 后重跑 |

---

## 备选模式：外部 API Key 批量跑批（可选）

当评论量超过 5,000 条或脱离 Agent 在纯命令行环境运行时，仍可使用 `llm_classifier.py` 调用外部 DeepSeek / 火山引擎 API：

```bash
export DEEPSEEK_API_KEY="sk-xxx"
python llm_classifier.py
```

