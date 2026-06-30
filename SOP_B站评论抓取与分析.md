# B站评论抓取与分析 SOP

由小龙整理开发，方便内部同学快速抓取和分析 B站评论区数据。

> 适用场景：抓取 B 站视频评论区 → 情感分类 → 出报告
> 工具栈：Python + httpx + Bilibili API + 火山引擎 Ark LLM API
> 更新日期：2026-06-25

---

## 目录

1. [前置准备](#1-前置准备)
2. [步骤 A：查找目标视频](#2-步骤-a查找目标视频)
3. [步骤 B：爬取评论区](#3-步骤-b爬取评论区)
4. [步骤 C：合并数据](#4-步骤-c合并数据)
5. [步骤 D：LLM 情感分类](#5-步骤-dllm-情感分类)
6. [步骤 E：生成报告](#6-步骤-e生成报告)
7. [异常排查索引](#7-异常排查索引)

---

## 1. 前置准备

### 1.1 环境依赖
```bash
pip install httpx
```

### 1.2 获取 SESSDATA（爬取用）
> **若不提供 SESSDATA，评论区只能拉取前 20 条**
```
Chrome → F12 → Application → Cookies → bilibili.com → SESSDATA
```
格式：`857843af%2C1797923450%2C22549%2A...`

### 1.3 获取 LLM API Key（分类用）

**推荐：DeepSeek 官方 API（性价比高）**
1. 注册：https://platform.deepseek.com
2. 创建 API Key，复制 `sk-` 开头字符串
3. 设置环境变量：`export DEEPSEEK_API_KEY="sk-xxxxx"`

**备选：火山引擎 Ark（已有 Coding Plan 时）**
```
1. 登录 https://console.volcengine.com/ark/
2. 模型开通 → 搜索 deepseek-v4-flash → 开通
3. API Key 管理 → 创建 Key
```
API URL 替换为：
```python
API_URL = "https://ark.cn-beijing.volces.com/api/coding/v1/chat/completions"
MODEL   = "deepseek-v4-flash"
```

---

## 2. 步骤 A：查找目标视频

### 方法 1：直接给 BV 号（最快）
用户提供 B 站视频 URL，提取 BV 号：
```
https://www.bilibili.com/video/BV1icjS6CE16/  →  BV1icjS6CE16
```

### 方法 2：搜索 B 站（备选）
当需要主动找视频时，用 B 站搜索 API：
```python
# 搜索接口（需要 Cookie，否则可能返回 HTML 而非 JSON）
r = httpx.get("https://api.bilibili.com/x/web-interface/search/type", params={
    "search_type": "video",
    "keyword": "弧光猎人",
    "order": "click",  # click=播放量排序
    "page": 1
})
```

### 方法 3：确认视频信息
```bash
python3 -c "
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
python batch_scraper.py BV1icjS6CE16 BV1Gpjd6XEER ...
```
- 支持传入多个 BV 号，按顺序逐个爬取
- 每个视频：先爬热度排序 + 时间排序主评论 → 去重 → 再爬楼中楼子回复
- 自动保存到 `comments/players/` 或 `comments/official/`

### 关键代码流程
```
get_video_info()         → 获取视频元信息（标题/播放量/AID）
get_top_comments()       → 爬取顶级评论（分页，最多50页×20条=1000条）
get_sub_replies()        → 爬取每条热评的子回复（最多5页）
合并去重                 → 按 rpid 去重
保存 JSON                → {video, comments, top_level_count, sub_reply_count}
```

### 验证覆盖率
```bash
python check_stats.py
```
输出示例：
```
#  BV号               播放量    API总数  已抓   覆盖率
1  BV1Gpjd6XEER       9,240   136      136    100%  ✅
2  BV1KFjU6xEpU       7,809    91       91    100%  ✅
...
合计                         655      650   99.2%  ✅
```

---

## 4. 步骤 C：合并数据

```bash
python comments/analysis/prepare_comments.py
```

将所有 JSON 文件合并为一个扁平数组：
```json
[
  {
    "id": 0,
    "text": "评论内容",
    "uname": "用户名",
    "like": 201,
    "source_bvid": "BV1icjS6CE16",
    "source_title": "视频标题",
    "source_label": "official",       // 或 "player"
    "is_sub_reply": false
  },
  ...
]
```

输出：`comments/analysis/all_comments_combined.json`

---

## 5. 步骤 D：LLM 情感分类

### 5.1 配置
在 `llm_classifier.py` 顶部修改：
```python
API_KEY = "sk-xxxxx"              # DeepSeek API Key
MODEL = "deepseek-chat"            # DeepSeek 官方模型名
API_URL = "https://api.deepseek.com/chat/completions"
BATCH_SIZE = 40                    # 每批条数
```

### 5.2 运行
```bash
python llm_classifier.py
```

### 5.3 工作原理
```
读取 all_comments_combined.json (2134条)
  ↓ 分片（每批80条, 共27批）
  ↓ 逐批调用 LLM API（system prompt 定义分类规则）
  ↓ 返回 JSON 数组：[{id, sentiment, topic}, ...]
  ↓ 合并到原数据
  ↓ 统计 + 生成报告
```

### 5.4 System Prompt（分类规则）
```text
你是一个专业的游戏评论情感分析专家。判断每条评论的情感倾向：
- positive: 表达喜欢、满意、期待、称赞
- neutral: 中立意见、客观提问、建议、一般讨论
- negative: 批评、不满、吐槽bug/卡顿/服务器

注意识别反讽（例如"太好玩了，一小时了都没进去"→negative）
同时判断主题：性能优化/游戏性/运营活动/匹配/社交/国服对比/收费/画质/期待建议/其他
```

### 5.5 耗时与成本

Coding Plan 的限流更严格，建议 `BATCH_SIZE=40`、`SLEEP_BETWEEN=3s`。

| 评论量 | 批次 | 耗时 | 成本(DeepSeek) |
|:-----:|:----:|:---:|:-------------:|
| 2,000 | ~50批 | ~2-3分钟 | ~0.5-1元 |
| 10,000 | ~250批 | ~12-15分钟 | ~3-5元 |
| 100,000 | ~2500批 | ~1.5-2小时 | ~30-50元 |

如果遇到 `429 AccountRateLimitExceeded`：
1. 增大 `SLEEP_BETWEEN`（3秒 → 5秒）
2. 减小 `BATCH_SIZE`（50 → 30）
3. 脚本已内置指数退避重试机制

---

## 6. 步骤 E：生成报告

### 6.1 自动产出
LLM 分类完成后，脚本自动生成：
```
comments/analysis/
├── classified_llm.json        ← 全量数据+分类标签（可复用做更多分析）
└── llm_report.txt             ← 可读报告（含统计+原话引用+来源）
```

### 6.2 报告包含内容
- 总体概览：好评/中评/差评占比
- 主题负面率排行（按差评率从高到低排序）
- 好评 Top15（按点赞数排序，含原话+来源）
- 差评 Top15
- 中评 Top15

---

## 7. 异常排查索引

### 🚨 E1：爬取阶段 — 评论数远少于 API 显示数

```
症状：API 说 1520 条，只抓到 200 条
原因：SESSDATA 过期/缺失，只能获取未登录状态下的前 20 页（~200 条）
解决：
  1. 重新从浏览器复制 SESSDATA（注意 %2C 等编码字符不要被解码）
  2. 登录状态至少能抓到 700+ 条顶级评论
  3. 不登录状态：修改 max_pages=1 快速确认（但数据不完整）
```

### 🚨 E2：爬取阶段 — API 返回 -799 错误码

```
症状：{'code': -799, 'message': '请求太频繁了，请稍后重试'}
原因：频率限制触发
解决：
  1. 当前代码已内置 0.3s sleep，如需继续降低频率 → 改大 SLEEP_BETWEEN
  2. 如果批量爬多个视频，视频间有 1s sleep
  3. 若持续触发，暂停 30 分钟后再试
```

### 🚨 E3：分类阶段 — LLM API 返回 404 ModelNotOpen

```
症状：{"code":"ModelNotOpen","message":"Your account xxx has not activated the model..."}
原因：模型未在火山引擎控制台开通
解决：
  1. 打开 https://console.volcengine.com/ark/region:ark+cn-beijing/model
  2. 搜索模型名（如 deepseek-v4-flash-260425）
  3. 点击「开通」
  4. 如果是要用 Endpoint 形式：
     - 去「推理接入点」创建接入点
     - 用 ep-xxxxx 作为 model 参数
```

### 🚨 E4：分类阶段 — LLM API 返回 401 / 404

```
症状：401 Unauthorized
原因：API Key 无效或未配置
解决：
  1. 检查 API_KEY 变量是否有值
  2. 去控制台重新创建 Key：https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey
```

```
症状：404 Not Found（Coding Plan 用户）
原因：调用了错误的 endpoint
解决：
  - 正确：/api/coding/v1/chat/completions
  - 正确：/api/coding/v1/messages
  - 错误：/api/coding（根路径）
```

### 🚨 E5：分类阶段 — 部分评论未分类（统计 < 总数）

```
症状：累计完成 1912/2134 后停止
原因：某个批次 API 调用超时或返回异常
解决：
  1. 脚本已有 3 次重试机制，若连续失败则跳过该批
  2. 重新运行：已分类的 ID 会跳过？（当前脚本不缓存已分类结果）
  3. 临时兜底：没有 LLM 分类结果的评论默认判为 neutral
```

### 🚨 E6：爬取阶段 — 搜索 API 返回 HTML 而非 JSON

```
症状：r.json() 解析失败，返回 HTML 页面内容
原因：搜索 API 反爬升级，直接返回登录页
解决：
  1. 添加更多请求头（Referer、Origin、完整的 Cookie）
  2. 或直接用 WebFetch 抓 B 站搜索页面提取视频链接
  3. 或让用户直接提供目标视频的 BV 号（最快）
```

### 🚨 E7：输出文件编码问题

```
症状：终端打印乱码 / UnicodeEncodeError: 'gbk' codec can't encode character
原因：Windows 终端用 GBK 编码，无法显示 emoji 和部分中文
解决：
  1. 不影响数据文件（JSON/JSON 文件用 UTF-8 写入，内容正确）
  2. 查看文件内容时用 -Encoding utf8 参数：
     Get-Content file.json -Encoding utf8
  3. 或直接打开 JSON 文件查看
```

---

## 附录：脚本与文件清单

```
CWD = C:\Users\v_clulcchen\Desktop\RYu\Coding\biliark\

工具脚本：
  batch_scraper.py             ← 批量爬取评论（入口）
  llm_classifier.py            ← LLM 情感分类（入口）
  classifier.py                ← 词典规则分类（备选）
  check_stats.py               ← 查看爬取覆盖率
  generate_report.py           ← 生成报告
  extract_classifications.py   ← 提取分类结果

数据目录：
  comments/
    official/                  ← 官方视频评论
    players/                   ← 玩家视频评论
    raw/                       ← 原始数据
    analysis/                  ← 分析结果
      all_comments_combined.json    ← 合并后的全量数据
      classified_llm.json           ← LLM 分类结果 ✅ 最终产出
      llm_report.txt                ← 最终报告

标准运行流程（完整）：
  Step 1:  python batch_scraper.py BVxxx BVxxx ...    # 爬取
  Step 2:  python comments/analysis/prepare_comments.py  # 合并
  Step 3:  python llm_classifier.py                     # 分类
  Step 4:  # 报告已自动生成到 llm_report.txt
```
