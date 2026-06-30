# BiliShare — B站评论区抓取与情感分析工具

一个 Python 工具链，用于批量抓取 B 站视频评论区，并通过 LLM API 进行情感分类（好评/中评/差评）和主题分析，一键生成舆情报告。

由小龙整理开发，方便内部同学快速抓取和分析 B站评论区数据。

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

- ✅ **批量爬取** B 站视频评论（含楼中楼子回复）
- ✅ **全量覆盖**：同时抓取热度排序 + 时间排序的评论，去重合并
- ✅ **LLM 情感分类**：调用 DeepSeek API 识别好评/中评/差评 + 主题归类
- ✅ **自动出报告**：统计占比、原文引用、来源标注、主题分布
- ✅ **覆盖率验证**：对比 API 显示总评论数和实际抓取数
- ✅ 爬虫频率控制和 429 限流自动重试

## 全景视图

```
┌─────────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐
│ ① 爬取评论   │ -> │ ② 合并数据    │ -> │ ③ LLM 分类    │ -> │ ④ 查看报告   │
│ batch_scraper│    │ prepare_     │    │ llm_          │    │ llm_report   │
│ .py          │    │ comments.py  │    │ classifier.py │    │ .txt         │
├─────────────┤    ├──────────────┤    ├───────────────┤    ├──────────────┤
│ B站内部 API  │    │ 多个视频 JSON │    │ DeepSeek API  │    │ 情感占比      │
│ + SESSDATA   │    │ → 扁平数组    │    │ 好评/中评/差评  │    │ 主题分布      │
│ → JSON 文件  │    │ → one JSON   │    │ + 主题归类     │    │ 原话引用      │
└─────────────┘    └──────────────┘    └───────────────┘    └──────────────┘
```

## 环境要求

- **Python 3.10+**
- **依赖**：`pip install httpx`

## 快速开始

### Agent 环境（推荐）

在 Claude Code / 方舟 / 任意 Agent 中，把 `bilishare/` 文件夹放入项目目录，然后告诉 Agent：

> "帮我用 bilishare 抓取并分析这几个视频的评论：BV1xx BV2xx ..."

Agent 会引导你提供 SESSDATA 和 API Key，然后自动完成初始化→爬取→分类→出报告全流程。

如果你想手动操作：
```bash
pip install httpx
export BILI_SESSDATA="..." DEEPSEEK_API_KEY="sk-..."
python batch_scraper.py BV1xx BV2xx ...           # 爬取
python check_stats.py && python prepare_comments.py && python llm_classifier.py  # 检查→合并→分类
```

### 普通命令行

```bash
# 1. 把 bilishare 文件夹放到工作目录，进入
cd bilishare

# 2. 安装依赖
pip install httpx

# 3. 配置环境变量
export BILI_SESSDATA="..."
export DEEPSEEK_API_KEY="sk-..."

# 4. 爬取评论
python batch_scraper.py <BV号1> <BV号2> ...

# 5. 检查覆盖率（API 显示的评论数 vs 实际抓到数）
python check_stats.py

# 6. 合并 → 分类
python prepare_comments.py && python llm_classifier.py

# 7. 查看报告
cat comments/analysis/llm_report.txt
```

---

## 使用指南

### Step 1：爬取评论

```bash
python batch_scraper.py <BV号1> <BV号2> <BV号3> ...
```

> 💡 **BV 号太多？** 在 B站搜索结果/UP主主页/合集页面，用以下浏览器插件可以一键批量复制所有视频链接，然后手动提取 BV 号：
> - **Chrome 推荐**：[TabCopy](https://chromewebstore.google.com/detail/tabcopy)（复制所有打开标签页的 URL）
> - **批量提取链接**：[Link Grabber](https://chromewebstore.google.com/detail/link-grabber)（一键抓取页面所有链接，支持过滤 B站视频 URL）
> - **通用方案**：`Ctrl/⌘ + 点击` 依次打开视频 → TabCopy 导出所有 URL → 用正则 `BV[a-zA-Z0-9]{10}` 提取 BV 号

**工作原理：**
- 每个视频拉取两遍评论：**热度排序** + **时间排序**，然后去重（确保不遗漏）
- 每遍最多翻 50 页（每页 20 条），B站 API 返回完会自动停止
- 对有回复的顶级评论，逐条展开拉取**楼中楼子回复**（最多 5 页）
- 按 `rpid` 去重后输出 JSON

> 实际拉取量取决于视频评论数。以弧光猎人官方视频（1,522 条评论）为例：最终拿到 **737 条顶级评论 + 747 条子回复 = 1,484 条**（覆盖率 97.5%）
- 输出 JSON 文件到 `comments/players/` 或 `comments/official/`

**验证爬取覆盖率：**
```bash
python check_stats.py
```

### Step 2：合并数据

```bash
python prepare_comments.py
```
将所有视频的评论 JSON 合并为一个扁平数组，输出到 `comments/analysis/all_comments_combined.json`

### Step 3：LLM 情感分类

```bash
python llm_classifier.py
```

**分类规则：**

| 分类 | 定义 | 示例 |
|:---:|:---|:---|
| 👍 好评 | 表达喜欢、满意、称赞、推荐 | "红名可太好了，国际服已经搞不好了" |
| ➖ 中评 | 客观讨论、提问、建议、一般反馈 | "问下这个配置够不够" |
| 👎 差评 | 批评、不满、吐槽bug/卡顿/服务器 | "一小时了都没进去" |

**主题归类：** 性能优化、游戏性、运营活动、匹配/社交、国服对比、收费/氪金、画质/音效、期待/建议、其他

LLM 会识别反讽、游戏黑话（如 "太好玩了，一小时了都没进去" → 差评）。

**耗时参考：**
| 评论量 | 批次 | 耗时 |
|:-----:|:----:|:---:|
| 2,000 | ~50批 | ~2-3分钟 |
| 10,000 | ~250批 | ~12-15分钟 |

### Step 4：查看报告

运行分类后自动生成：
```
comments/analysis/
├── classified_llm.json        ← 全量数据+每条评论的 sentiment/topic 标签
└── llm_report.txt             ← 可读报告
```

报告包含：
- **总体概览**：好评/中评/差评占比
- **主题负面率排行**：按差评率从高到低
- **好评 Top 15**：按点赞排序 + 原话引用 + 来源
- **差评 Top 15**
- **中评 Top 15**

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

### ② AI API Key（必填，二选一）

#### 推荐：DeepSeek 官方 API（性价比高）

- 价格：￥1/百万 token（输入），￥2/百万 token（输出）
- 2000 条评论分类成本约 **￥0.5-1**
- 注册：https://platform.deepseek.com → 创建 API Key

```bash
export DEEPSEEK_API_KEY="sk-xxxxx"
```

脚本默认使用 DeepSeek 官方 API（`https://api.deepseek.com`）。

#### 备选：火山引擎 Ark

如果你有火山引擎 Coding Plan，替换 `llm_classifier.py` 中的配置：
```python
API_URL = "https://ark.cn-beijing.volces.com/api/coding/v1/chat/completions"
MODEL = "deepseek-v4-flash"
```

---

## 项目结构

```
bilishare/
├── batch_scraper.py               ← ① 批量爬取评论
├── prepare_comments.py            ← ② 合并数据
├── llm_classifier.py              ← ③ LLM 情感分类
├── check_stats.py                 ← 验证爬取覆盖率
├── generate_report.py             ← 生成报告
├── CLAUDE.md                      ← Agent 使用说明
├── README.md                      ← 本文档
├── SOP_B站评论抓取与分析.md        ← 详细 SOP + 异常排查
├── comments/
│   ├── official/                  ← 官方视频评论 JSON（手动/自动放置）
│   ├── players/                   ← 玩家视频评论 JSON
│   └── analysis/                  ← 分析结果（自动生成）
│       ├── all_comments_combined.json
│       ├── classified_llm.json
│       └── llm_report.txt
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
