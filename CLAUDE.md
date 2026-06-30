# CLAUDE.md — BiliShare

## 项目用途

批量抓取 B站视频评论区，通过 DeepSeek API 进行情感分类（好评/中评/差评）和主题分析，一键生成舆情报告。

## Agent 职责

当用户表示要抓取 B站评论区时，按以下流程引导：

### 第一步：收集必要信息

询问用户并逐项确认：

1. **视频 BV 号**（必填）
   - 问用户要哪些视频的评论，帮助提取 BV 号
   - 如果用户只有一个链接，从中提取：`BV[a-zA-Z0-9]{10}`
   - 如果用户有大量链接，建议用浏览器插件批量提取（见 README）

2. **B站 SESSDATA**（必填，不登录只能抓 20 条）
   - 获取方式：浏览器登录 B站 → F12 → Application → Cookies → bilibili.com → SESSDATA
   - 确认拿到后设置：`export BILI_SESSDATA="用户的SESSDATA"`

3. **DeepSeek API Key**（必填，用于评论分类）
   - 获取方式：https://platform.deepseek.com → 创建 API Key
   - 确认拿到后设置：`export DEEPSEEK_API_KEY="sk-xxx"`
   - 如果用户有火山引擎 Ark Coding Plan 的 Key 也可以用（替换 llm_classifier.py 中的 API_URL）

### 第二步：安装依赖并创建目录

```bash
pip install httpx
mkdir -p comments/official comments/players comments/analysis
```

### 第三步：爬取评论

```bash
python batch_scraper.py BV1xx BV2xx ...
```

### 第四步：检查覆盖率 → 合并 → 分类 → 出报告

```bash
python check_stats.py && python prepare_comments.py && python llm_classifier.py
```

### 第五步：展示结果

将 `comments/analysis/llm_report.txt` 的内容整理后告诉用户核心发现：
- 好评/中评/差评占比
- 差评率最高的主题
- 典型高赞原话引用

## 常见问题处理

| 问题 | 处理 |
|:---|:---|
| API 返回 429 限流 | 增大 SLEEP_BETWEEN 到 5 秒，减小 BATCH_SIZE 到 30 |
| 只抓到 200 条但 API 显示更多 | SESSDATA 过期，让用户重新提供 |
| 爬虫报 -799 错误 | 减少请求频率，暂停后重试 |
| 用户想区分官方/玩家视频 | 官方视频请用 `comments/official/` 目录，玩家视频用 `comments/players/` |

## 项目脚本

| 脚本 | 功能 |
|:---|:---|
| `batch_scraper.py` | 批量爬取评论（主评论+楼中楼） |
| `check_stats.py` | 对比 API 总数 vs 实际抓取数 |
| `prepare_comments.py` | 合并所有评论 JSON 为一个文件 |
| `llm_classifier.py` | LLM 情感分类并生成报告 |
| `generate_report.py` | 生成报告（工具脚本） |
| `SOP_B站评论抓取与分析.md` | 详细异常排查手册 |
