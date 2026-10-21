# BiliShare — B站评论区抓取与情感分析 Skill / 工具链

一个轻量通用的 B 站视频评论区抓取与舆情分析工具。**无需额外购买外部 LLM API Key**，可直接作为 Agent Skill 在 **WorkBuddy / Claude Code / Antigravity / Cursor** 中复用宿主自带 Token 额度完成情感分类（好评/中评/差评）、具体观点提炼与高赞原话统计（同时也保留外部 API Key 脚本供纯命令行跑批）。

## 目录

- [功能](#功能)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [使用指南](#使用指南)
  - [Step 1：爬取评论](#step-1爬取评论)
  - [Step 2：合并数据](#step-2合并数据)
  - [Step 3：LLM 情感分类](#step-3llm-情感分类)
  - [Step 4：查看报告](#step-4查看报告)
- [配置说明](#配置说明)
- [项目结构](#项目结构)
- [FAQ](#faq)
- [免责声明](#免责声明)

---

## 功能

- ✅ **零 API Key 开箱即用**：基于「短序号切块 + 指针聚类」协议，单块输出仅 ~400 Tokens，直接在 WorkBuddy / Claude Code / Antigravity 内用宿主额度跑通，不惧小窗口与输出截断
- ✅ **批量全量爬取**：同时抓取 B 站视频**热度排序 + 时间排序**主评论及**楼中楼子回复**，自动去重合并
- ✅ **主题 + 具体槽点双层提炼**：不仅统计 9 大主题负面率，还直接提炼每个主题下的具体玩家观点与条数
- ✅ **高赞防漏校验**：自动标记并校验 $\ge 10$ 赞热评覆盖率，确保核心热评 100% 不遗漏
- ✅ **双模兼容**：同时保留 `llm_classifier.py`，支持在无 Agent 环境下配置 DeepSeek / 火山引擎 API Key 独立跑批

## 全景视图

```
┌───────────────┐    ┌──────────────────┐    ┌───────────────────┐    ┌──────────────────┐
│ ① 爬取评论     │ -> │ ② 合并与指针切块  │ -> │ ③ Agent 观点聚类   │ -> │ ④ 水化还原出报告  │
│ batch_scraper │    │ prepare_         │    │ 宿主 Agent 免 Key  │    │ generate_report  │
│ .py           │    │ comments.py      │    │ (或 llm_classifier)│    │ .py              │
├───────────────┤    ├──────────────────┤    ├───────────────────┤    ├──────────────────┤
│ B站内部 API    │    │ 合并全量 JSON +   │    │ 合并同类项输出      │    │ 情感占比 / 水评比 │
│ + SESSDATA    │    │ 300条/块短序号切块│    │ 观点 + 序号数组     │    │ 主题与具体槽点    │
│ → JSON 文件    │    │ → chunks/*.txt   │    │ → results/*.json  │    │ 高赞原话 Top 15   │
└───────────────┘    └──────────────────┘    └───────────────────┘    └──────────────────┘
```

## 环境要求

- **Python 3.10+**
- **依赖**：`pip install httpx`

## 快速开始

### 方式一：Agent 环境免 API Key 模式（推荐，支持 WorkBuddy / Claude Code / Antigravity）

把 `bilishare/` 放入工作目录（或 `skills/` 目录），直接对 Agent 说：

> "帮我用 bilishare 抓取并分析这几个视频的评论：BV1xx BV2xx ..."

Agent 会按 [`SKILL.md`](./SKILL.md) 引导你提供 **B站 `SESSDATA`**（无需任何大模型 API Key），自动完成：
1. `python batch_scraper.py BV1xx ...`（爬取评论）
2. `python check_stats.py && python prepare_comments.py`（检查覆盖率并生成 `chunks/chunk_XX.txt` 短序号切块）
3. Agent 自身（或并发派发 Subagent）读取切块并输出指针聚类结果到 `comments/analysis/results/`
4. `python generate_report.py`（还原指针、校验高赞防漏并生成 `comments/analysis/llm_report.txt`）

### 方式二：纯命令行 + 外部 API Key 模式（备选）

如果你不在 Agent 环境中，或者希望用外部 API Key 后台挂机跑上万条评论：

```bash
cd bilishare
pip install httpx
export BILI_SESSDATA="..."
export DEEPSEEK_API_KEY="sk-..."

python batch_scraper.py <BV号1> <BV号2> ...
python check_stats.py
python prepare_comments.py && python llm_classifier.py
cat comments/analysis/llm_report.txt
```


---

## 使用指南

### Step 1：爬取评论

```bash
python batch_scraper.py <BV号或B站视频链接> ...            # 默认存入 comments/players/（采用 WBI 签名引擎）
python batch_scraper.py --official <官方视频BV号> ...     # 可选：加 --official 存入 comments/official/
python batch_scraper.py --engine legacy <BV号> ...        # 可选：切换旧版 legacy 接口引擎
python batch_scraper.py --compare <BV号>                  # 可选：双引擎（Legacy vs WBI）同台跑分对比
```

> 💡 **支持直接粘贴完整视频 URL**：脚本会自动从中正则提取 `BV号`。若需批量抓取多个视频，在 B站搜索结果/UP主主页可用以下插件一键导出 URL：
> - **Chrome 推荐**：[TabCopy](https://chromewebstore.google.com/detail/tabcopy)（复制所有打开标签页的 URL）
> - **批量提取链接**：[Link Grabber](https://chromewebstore.google.com/detail/link-grabber)（一键抓取页面所有链接，支持过滤 B站视频 URL）
> - **通用方案**：`Ctrl/⌘ + 点击` 依次打开视频 → TabCopy 导出所有 URL → 直接作为参数传给 `batch_scraper.py`

**工作原理（详见 [`BENCHMARK_评论抓取双引擎实测报告.md`](./BENCHMARK_评论抓取双引擎实测报告.md)）：**
- **WBI + Legacy 双引擎热备**：默认采用新版 `/x/v2/reply/wbi/main` 动态签名游标翻页（单趟默认上限 `250` 页 ≈ 5,000 条主评论），异常时自动无缝降级至 `legacy` 接口。
- **单/双趟智能自适应**：第 1 趟（热门排序）若已自然见底（`is_end=True`），自动免跑第 2 趟（时间排序）；仅在超大视频超出单趟页数上限时启动第 2 趟互补并按 `rpid` 去重。
- **内联子回复零请求直取**：主评论自带的子回复已满足 `rcount` 时直接复用（省去约 60% 的楼中楼 HTTP 请求）；超出部分按需请求 `/x/v2/reply/reply`（最高 `15` 页/楼，不满 20 条立即停止）。

> **实测覆盖率**：中小型视频（1,522 条评论）实抓 **1,484 条（覆盖率 97.5%）**；近万评热门视频（9,632 条评论）仅需 2.7 分钟、664 次请求即可实抓 **9,328 条（覆盖率 96.8%，已达 B 站阿瓦隆风控外全部公开可见极限）**。

**验证爬取覆盖率：**
```bash
python check_stats.py
```

### Step 2：合并数据与生成短序号切块

```bash
python prepare_comments.py
```
1. 将所有视频的评论 JSON 合并为 `comments/analysis/all_comments_combined.json`；
2. 按 **300 条 / 12,000 字** 自动切分生成 `comments/analysis/chunks/chunk_01.txt ~ chunk_NN.txt` 及映射清单 `manifest.json`（同时自动清理旧切块与旧结果）。

### Step 3：情感分类与观点提炼

- **方式 A（推荐，免 API Key）**：由宿主 Agent（WorkBuddy / Claude Code / Antigravity）按 [`SKILL.md`](./SKILL.md) 规范读取 `comments/analysis/chunks/chunk_*.txt`，合并同类观点输出局部序号数组至 `comments/analysis/results/chunk_XX_result.json`。
- **方式 B（备选，外部 API Key）**：运行 `python llm_classifier.py` 调用外部 DeepSeek / 火山引擎 API 逐批分类。

**分类规则：**

| 分类 | 定义 | 示例 |
|:---:|:---|:---|
| 👍 好评 | 表达喜欢、满意、称赞、推荐 | "红名可太好了，国际服已经搞不好了" |
| ➖ 中评 | 客观讨论、提问、建议、一般反馈 | "问下这个配置够不够" |
| 👎 差评 | 批评、不满、吐槽bug/卡顿/服务器 | "一小时了都没进去" |

**一级主题（9 大固定分类）：** `性能优化`、`游戏性`、`运营活动`、`匹配/社交`、`国服对比`、`收费/氪金`、`画质/音效`、`期待/建议`、`其他`

### Step 4：生成并查看报告

```bash
python generate_report.py
```

自动生成：
```
comments/analysis/
├── classified_llm.json        ← 全量数据 + 每条评论的 sentiment/category/point 标签
└── llm_report.txt             ← 可读舆情报告
```

报告包含：
- **总体概览**：实质观点评论 vs 日常互动水评占比，以及好评/中评/差评占比
- **主题负面率排行与核心观点明细**：按主题统计好评/差评率，并列出每个主题下的具体槽点（`point`）与条数
- **好评 / 差评 / 中评 高赞原话 Top 15**：按点赞排序 + 原话引用 + 视频来源

---

## 配置说明

### ① B站 SESSDATA（必填）

用于爬取完整评论区（不登录只能看到前 20 条）

1. 浏览器登录 [B站](https://www.bilibili.com)
2. `F12` → `Application` → `Cookies` → `bilibili.com`
3. 找到 `SESSDATA`，复制其 Value
4. 设置环境变量：
   ```bash
   export BILI_SESSDATA="你的SESSDATA值"
   ```

### ② 外部 AI API Key（可选，仅在使用 `llm_classifier.py` 时需要）

> 在 WorkBuddy / Claude Code / Antigravity 等 Agent 环境中默认使用宿主自带额度，**无需配置此项**。

#### DeepSeek 官方 API（性价比高）

- 价格：￥1/百万 token（输入），￥2/百万 token（输出），2000 条评论约 **￥0.5-1**
- 注册：https://platform.deepseek.com → 创建 API Key

```bash
export DEEPSEEK_API_KEY="sk-xxxxx"
```

#### 火山引擎 Ark

如果你有火山引擎 Coding Plan，可替换 `llm_classifier.py` 中的配置：
```python
API_URL = "https://ark.cn-beijing.volces.com/api/coding/v1/chat/completions"
MODEL = "deepseek-v4-flash"
```

---

## 项目结构

```
bilishare/
├── SKILL.md                       ← Agent Skill 指针切块协议规范（主入口）
├── CLAUDE.md                      ← Agent 引导说明
├── batch_scraper.py               ← ① 批量爬取评论（支持 --official）
├── check_stats.py                 ← 验证爬取覆盖率
├── prepare_comments.py            ← ② 合并数据并生成 300条/块 短序号切块
├── generate_report.py             ← ④ 指针还原、高赞防漏校验与生成报告
├── llm_classifier.py              ← （可选）使用外部 API Key 逐批分类
├── README.md                      ← 本文档
├── SOP_B站评论抓取与分析.md        ← 详细 SOP + 异常排查索引
└── comments/                      ← 运行时数据目录（自动创建）
    ├── official/                  ← 官方视频评论 JSON
    ├── players/                   ← 玩家视频评论 JSON
    └── analysis/                  ← 分析产物
        ├── stats_report.txt
        ├── all_comments_combined.json
        ├── chunks/                ← 短序号切块 chunk_XX.txt 与 manifest.json
        ├── results/               ← Agent 输出的 chunk_XX_result.json
        ├── classified_llm.json
        └── llm_report.txt
```

---

## FAQ

### Q: 爬虫提示 `Error(code=-799)` 是什么？
A: 请求频率太高被 B站限流。当前脚本已内置 0.3s/request 间隔。如果持续触发，增加 SLEEP_BETWEEN 或者减少 max_pages。

### Q: 只抓到 200 条，API 显示有 1500 条？
A: SESSDATA 过期或无效。从浏览器重新复制 SESSDATA 即可。

### Q: LLM 分类遇到 `429 AccountRateLimitExceeded`？
A: API 请求频率超过配额。脚本已内置指数退避重试。如果持续触发，增大 `SLEEP_BETWEEN` 到 5 秒。

### Q: 能爬弹幕吗？
A: 当前版本只支持评论区。弹幕抓取需要 B站 ProtoBuf 协议，可参考 `bilibili-api-python` 库的弹幕模块。

---

## 免责声明

- 本工具仅供**学习和研究**使用，请勿用于商业目的
- 请遵守 B站用户协议，合理控制抓取频率，尊重用户隐私
- 评论数据请勿公开传播或用于损害他人权益的用途
- 使用本工具产生的任何法律风险由使用者自行承担

---

## License

MIT
