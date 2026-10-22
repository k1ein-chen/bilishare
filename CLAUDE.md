# CLAUDE.md — BiliShare

## 项目用途

批量抓取 B站视频评论区，无需外部 LLM API Key，直接利用当前 Agent（WorkBuddy / Claude Code / Antigravity）自身额度完成指针化切块情感分类（好评/中评/差评）与具体观点提炼，一键生成舆情报告。

## Agent 职责

当用户表示要抓取并分析 B站评论区时，详细规范见 [`SKILL.md`](./SKILL.md)，按以下四步引导执行：

### 第一步：收集必要信息（无需 API Key）

询问用户并确认：

1. **视频 BV 号**（必填）
   - 从用户提供的视频链接或列表中提取：`BV[a-zA-Z0-9]{10}`
   - 如需区分官方与玩家视频：爬取官方视频时加 `--official` 参数（自动存入 `comments/official/`），玩家视频默认存入 `comments/players/`
2. **B站 SESSDATA**（必填，不登录只能抓 20 条）
   - 获取方式：浏览器登录 B站 → F12 → Application → Cookies → `bilibili.com` → 复制 `SESSDATA`
   - 设置环境变量：`export BILI_SESSDATA="用户的SESSDATA"`（PowerShell: `$env:BILI_SESSDATA="..."`）

### 第二步：爬取评论并生成短序号切块

```bash
pip install httpx
python batch_scraper.py BV1xx BV2xx ...
python batch_scraper.py --official BV3xx ...   # 可选：官方视频加 --official
python check_stats.py && python prepare_comments.py
```

### 第三步：Agent 指针化切块分析（免 API Key，9大主题 × 6大意图）

读取 `comments/analysis/chunks/chunk_*.txt`（支持并发派发 Subagent 或主 Agent 逐块处理），对每块评论按观点合并同类项，写出 `comments/analysis/results/chunk_XX_result.json`：

```json
{
  "chunk_id": "chunk_01",
  "opinions": [
    {
      "sentiment": "negative",
      "category": "平衡数值",
      "intent": "建言献策",
      "point": "吐槽威龙实战强度垫底并呼吁优化喷气后摇",
      "indices": [1, 3, 14, 22]
    }
  ]
}
```
- `sentiment`: `"positive"` | `"neutral"` | `"negative"`（注意识别反讽）
- `category`（9选1）: `视听剧情IP` / `平衡数值` / `玩法内容` / `技术Bug` / `商业化付费` / `运营服务` / `社区社交` / `赛事竞品` / `其他`
- `intent`（6选1）: `表扬认可` / `玩梗传播` / `咨询考据` / `建言献策` / `吐槽宣泄` / `维权抵制`
- `point`: 10~25 字概括具体观点/槽点
- `indices`: 属于该观点的块内编号数组（带 `🔥` 的 $\ge 10$ 赞高赞评论必须 100% 归类，纯打卡水评直接忽略，由脚本自动计入水评）

### 第四步：二级指针收敛并按标准模板生成报告（`.md` & `.txt`）

```bash
python generate_report.py
```

1. 若跨块原子观点数 $> 30$，读取自动导出的 `comments/analysis/raw_points.json`（`P001~Pn`），将同义观点归并写入 `comments/analysis/merged_points.json` 后重跑 `python generate_report.py`；
2. 严格按照 [`report_template.md`](./report_template.md) 与 [`report_template.txt`](./report_template.txt) 的三模块结构（`# 整体结论`［双口径并列 + 好评/差评/热门话题］ $\rightarrow$ `# 评价观点明细`［无前缀分点］ $\rightarrow$ `# 好中差评声量明细`）输出最终 `.md` 与 `.txt` 报告。

> **备选（外部 API Key 模式）**：若评论量极大（>5000条）且用户主动提供 `DEEPSEEK_API_KEY`，也可直接运行 `python llm_classifier.py`。

## 项目脚本与模板

| 脚本 / 文档 | 功能 |
|:---|:---|
| `SKILL.md` | Agent Skill 完整指针切块、二级归并与报告协议规范 |
| `report_template.md` | B站评论区舆情报告标准模板（Markdown 版） |
| `report_template.txt` | B站评论区舆情报告标准模板（纯文本版） |
| `batch_scraper.py` | 批量爬取评论（WBI + Legacy 双引擎 + 楼中楼内联复用） |
| `check_stats.py` | 对比 API 总数 vs 实际抓取覆盖率 |
| `prepare_comments.py` | 合并评论并自动生成 300 条/块的短序号切块 (`chunks/`) |
| `generate_report.py` | 二级指针还原、高赞校验并产出 `.md` 与 `.txt` 报告 |
| `llm_classifier.py` | （可选备选）使用外部 DeepSeek/火山引擎 API Key 逐批分类 |
| `SOP_B站评论抓取与分析.md` | 详细操作与异常排查手册 |

