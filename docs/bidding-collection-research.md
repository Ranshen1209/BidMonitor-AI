# 八爪鱼与招投标采集产品调研报告

> 调研主题：八爪鱼的招投标采集是怎么做的，市面上类似投标采集产品如何实现，以及招投标采集最佳实践。

## 一句话结论

八爪鱼的招投标采集，本质上是：

> 用低代码/无代码采集模板，把招投标网站的搜索、列表、翻页、详情页、发布时间增量判断、字段抽取、清洗导出做成可配置流程；再叠加多源模板、定时任务、字段识别、标签化和 API/数据库/Excel 交付。

市面上类似产品大致分两类：

1. **通用网页采集器**：如八爪鱼、火车采集器、后羿采集器，核心是网页采集流程编排、浏览器自动化、规则抽取、自动识别、清洗导出。
2. **招投标垂直信息平台**：如千里马、采招网等，核心不是卖“爬虫工具”，而是把采集后的标讯做成可检索、可订阅、可监测、可下载、可 API 对接的数据产品。

最佳实践不是“写一个爬虫抓网页”，而是建设一条完整链路：

> 数据源管理 → 采集编排 → 增量判定 → 结构化抽取 → 清洗标准化 → 去重与标签 → 监测告警 → 数据交付/API/数据库/Excel

---

## 1. 八爪鱼的招投标采集是怎么做的

### 1.1 产品定位：多源招投标数据采集方案

八爪鱼官方招投标方案声称覆盖：

- 聚合类招投标网站
- 国家类招投标网站
- 行业类招投标网站
- 全国和地方公共资源交易平台
- 垂直行业招投标平台

其公开方案中提到的能力包括：

- `3000+` 全网招投标数据源覆盖
- 定时采集
- 实时监控
- 增量采集
- AI 字段识别
- 数据清洗与标准化
- 自动打标签
- Excel 导出
- 企业数据库同步
- API 接入内部系统

来源：

- <https://www.bazhuayu.com/solutions/bidding-and-tendering>
- <https://www.bazhuayu.com/resources/collect-template/tender-bidding>

需要注意：`3000+ 数据源`、`AI 精准识别` 等属于厂商自述，调研能证明它们是公开宣称，但不能独立验证真实覆盖率、成功率和稳定性。

### 1.2 使用方式：模板化、低代码/无代码

八爪鱼的招投标采集模板页面强调：

- 用户无需写代码
- 输入目标网址、关键词等参数
- 使用预设模板快速采集招投标数据
- 几分钟内获取结构化结果

这说明八爪鱼面向的是业务人员或轻技术用户，而不是纯工程团队。

它把原本需要开发人员写爬虫的动作，包装成：

- 可视化采集流程
- 预设模板
- 参数化配置
- 定时任务
- 导出与同步能力

### 1.3 具体采集流程：搜索、列表、翻页、字段抽取、增量判断

八爪鱼帮助中心中关于“全国公共资源交易平台采集当天最新招标数据”的教程，展示了比较典型的实现路径。

目标站点示例：

- `deal.ggzy.gov.cn/ds/deal/dealList.jsp`

典型流程为：

1. 打开目标招投标列表页
2. 输入关键词搜索
3. 识别列表区域
4. 设置“循环列表”
5. 抽取列表中的字段
6. 如需更多数据，设置“循环翻页”
7. 根据发布时间设置触发条件
8. 当发布时间早于采集当天 0 点时停止或跳出
9. 只采集当天最新数据

这本质上是一个规则化的网页采集流程：

```text
打开页面
  ↓
输入关键词
  ↓
点击搜索
  ↓
等待列表加载
  ↓
循环列表项
  ↓
抽取标题/地区/发布时间/项目类型/链接等字段
  ↓
判断发布时间是否属于当天
  ↓
如果是，继续采集
如果不是，停止翻页或结束任务
  ↓
导出/同步
```

来源：

- <https://www.bazhuayu.com/helpcenter/docs/quan-guo-gong-gong-zi-yuan-jiao-yi-ping-tai-yong-chu-fa-qi-cai-ji-dang-tian-zui-xin-zhao-biao-shu-ju>

---

## 2. 八爪鱼方案背后的技术实现逻辑

从公开资料和采集器通用机制来看，八爪鱼招投标采集大概率由以下能力组成。

### 2.1 数据源层

维护大量招投标数据源，包括：

- 国家公共资源交易平台
- 中国政府采购网
- 各省市公共资源交易中心
- 行业招投标平台
- 企业采购平台
- 第三方聚合平台

每个数据源需要配置：

- 入口 URL
- 搜索参数
- 关键词规则
- 地区分类
- 行业分类
- 列表页规则
- 详情页规则
- 翻页规则
- 发布时间字段
- 附件字段
- 反爬/登录/验证码处理策略

### 2.2 流程编排层

招投标页面通常不是单纯 HTML 抓取，往往需要模拟交互：

- 输入关键词
- 点击搜索
- 选择地区/时间/分类
- 等待异步请求完成
- 翻页
- 点击详情页
- 下载附件
- 回到列表继续采集

所以采集器一般会提供类似 RPA 的流程编排：

```text
打开网页
输入文本
点击按钮
等待加载
提取列表
点击详情
提取字段
下载附件
返回上一页
循环翻页
```

这也是八爪鱼、后羿、火车采集器等通用采集器的共同核心。

### 2.3 抽取层

招投标数据常见字段包括：

- 公告标题
- 公告类型
- 项目编号
- 项目名称
- 招标单位 / 采购单位
- 代理机构
- 所属地区
- 所属行业
- 发布时间
- 截止时间
- 预算金额
- 中标金额
- 中标单位
- 联系人
- 联系电话
- 原文链接
- 附件链接
- 附件文件名
- 正文内容

抽取方式通常包括：

1. CSS Selector / XPath 规则
2. 表格结构识别
3. 正则表达式
4. DOM 邻近文本识别
5. 详情页模板抽取
6. AI/LLM 辅助字段识别
7. OCR 或文档解析，用于 PDF、Word、图片化表格

八爪鱼公开提到 AI 识别招标金额、截止时间、招标单位等字段，但具体准确率未公开验证。

### 2.4 增量采集层

招投标采集非常依赖增量机制，因为全量抓取成本高、重复多、站点压力大。

常见增量判断方式：

- 发布时间晚于上次采集时间
- 发布时间属于当天
- 公告 URL 未出现过
- 公告 ID 未出现过
- 标题 + 发布单位 + 发布时间 哈希去重
- 详情页内容 hash 变更检测
- 附件 hash 变更检测
- 公告状态变更检测，例如变更公告、中标公告、废标公告

八爪鱼教程里的“发布时间早于采集当天 0 点则停止”就是一种典型的时间窗口增量采集。

### 2.5 清洗标准化层

原始招投标网页数据通常很脏，必须清洗：

- 日期格式统一
- 金额单位统一，例如元/万元/亿元
- 地区标准化到省、市、区县
- 公告类型标准化
- 行业分类标准化
- HTML 标签清理
- 空白字符清理
- 标题噪声去除
- 联系方式脱敏或规范化
- 附件 URL 补全
- 相对链接转绝对链接

垂直招投标平台的价值，很大一部分来自清洗和标准化，而不是单纯抓取。

### 2.6 去重与实体归一层

招投标公告经常被多个网站转载，容易重复。

常见去重策略：

```text
强规则：
- 原文 URL
- 公告 ID
- 项目编号
- 公告编号

弱规则：
- 标题相似度
- 采购单位相同
- 发布时间相近
- 金额相同
- 地区相同
- 正文 simhash/minhash
```

实体归一包括：

- 同一采购单位的不同写法归并
- 同一中标企业的名称归并
- 代理机构名称归并
- 项目编号和项目名称关联
- 招标公告、变更公告、中标公告串成同一项目生命周期

这是从“网页采集”升级为“招投标数据产品”的关键。

### 2.7 交付层

八爪鱼和竞品常见交付方式：

- Excel
- CSV
- 本地数据库
- 企业数据库同步
- API
- 批量下载
- 定时推送
- 邮件/微信/短信/企微/钉钉告警
- Web 控制台检索
- 看板/dashboard

八爪鱼公开方案提到 Excel、数据库和 API。采招网等垂直平台则强调批量下载、API 数据接口、数据打包下载等服务。

---

## 3. 市面上类似产品怎么实现

### 3.1 通用采集器：八爪鱼、火车采集器、后羿采集器

这类产品的核心能力是“网页数据采集工具”。

#### 共同特征

- 可视化流程配置
- 模拟浏览器交互
- 列表页/详情页采集
- 翻页采集
- 定时任务
- 数据清洗
- 导出 Excel/CSV/数据库
- 部分支持自动识别网页结构
- 部分支持代理、Cookie、登录态、验证码辅助等

#### 火车采集器

火车采集器官网将自身定位为：

- 互联网数据抓取
- 数据处理
- 数据分析
- 数据挖掘软件

它更偏传统规则型采集器，适合技术人员或半技术人员配置复杂采集规则。

来源：

- <https://www.locoy.com/>

#### 后羿采集器

后羿采集器强调：

- 输入网址即可自动识别采集内容
- 无需配置采集规则
- 流程图模式
- 支持输入文本、点击、移动鼠标、下拉框、滚动页面、等待加载等交互步骤

这说明后羿更强调自动识别和流程图式 RPA 编排。

来源：

- <https://www.houyicaiji.com/>

#### 八爪鱼

八爪鱼介于两者之间：

- 对普通用户提供无代码模板
- 对复杂场景提供可视化流程
- 对企业提供云采集、API、数据库同步、方案服务
- 在招投标场景上做了专门模板和行业方案包装

来源：

- <https://www.bazhuayu.com/>
- <https://www.bazhuayu.com/solutions/bidding-and-tendering>

### 3.2 招投标垂直平台：千里马、采招网等

这类产品不是简单采集器，而是数据服务平台。

#### 千里马招标网

千里马首页呈现的产品形态包括：

- 招标预告
- 招标公告
- 招标变更
- 招标结果
- 免费招标
- 项目
- 企业库
- 代理机构
- 标讯订阅
- 项目监测
- 企业监测

来源：

- <https://www.qianlima.com/>

这说明其核心是把采集到的标讯组织成可检索、可订阅、可监测的数据产品。

#### 采招网

采招网公开页面强调：

- 招投标信息
- 采购商机
- 结构化数据导出
- API 数据接口
- 招标数据批量下载
- 招中标数据打包下载

来源：

- <https://www.bidcenter.com.cn/>

这类平台的价值通常在：

- 数据覆盖
- 更新速度
- 去重质量
- 分类标签
- 企业主体库
- 项目生命周期追踪
- 搜索体验
- 订阅和告警
- API 和批量数据服务

---

## 4. 招投标采集的工程最佳实践

### 4.1 不要只做“爬虫”，要做“数据管道”

推荐架构：

```text
数据源注册表
  ↓
调度器
  ↓
采集 Worker
  ↓
页面解析 / API 抓取 / 浏览器渲染
  ↓
列表页抽取
  ↓
详情页抽取
  ↓
附件下载
  ↓
PDF / Word / Excel / 图片解析
  ↓
字段结构化
  ↓
清洗标准化
  ↓
去重与实体归一
  ↓
变更检测
  ↓
存储
  ↓
搜索索引
  ↓
订阅告警
  ↓
API / 导出 / 看板
```

### 4.2 数据源管理最佳实践

每个站点用配置管理，而不是硬编码：

```yaml
source_id: ggzy_national
name: 全国公共资源交易平台
base_url: https://www.ggzy.gov.cn/
category: public_resource
region: national
list_url: ...
search_params:
  keyword: required
  date_range: optional
selectors:
  list_item: ...
  title: ...
  publish_time: ...
  detail_url: ...
pagination:
  type: next_button
  selector: ...
incremental:
  field: publish_time
  stop_when_before: last_success_time
rate_limit:
  qps: 0.2
  concurrency: 1
```

这样可以做到：

- 新增站点不改代码
- 站点失效可单独禁用
- 每个站点独立限速
- 每个站点独立监控成功率
- 每个站点可单独回放和重跑

### 4.3 采集策略最佳实践

优先级建议：

1. **官方 API / JSON 接口**
2. **HTML 静态页面**
3. **站内搜索接口**
4. **浏览器渲染页面**
5. **RPA 模拟交互**
6. **OCR/视觉解析**

不要一上来就用浏览器自动化。浏览器成本高、慢、不稳定。

推荐分层：

```text
requests/httpx 抓接口
  ↓ 失败或 JS 渲染明显
Playwright/Selenium 浏览器渲染
  ↓ 有附件
文档下载和解析
  ↓ 图片化/扫描件
OCR
```

### 4.4 增量采集最佳实践

建议每个 source 维护：

- last_success_time
- last_seen_publish_time
- last_seen_ids
- last_run_status
- fail_count
- schema_version
- parser_version

增量停止条件：

```text
如果列表按发布时间倒序：
  遇到 publish_time <= last_success_time，可停止翻页

如果列表不是严格倒序：
  固定扫描最近 N 页或最近 N 天

如果站点更新不稳定：
  使用滑动窗口，例如每次回扫最近 3-7 天
```

去重键建议：

```text
primary_key = source_id + source_item_id
fallback_key = hash(normalized_title + purchaser + publish_date + region)
content_hash = simhash(normalized_body)
attachment_hash = sha256(file)
```

### 4.5 字段结构化最佳实践

招投标字段建议分三层。

#### 原始字段

保留原始页面抽取结果：

```json
{
  "raw_title": "...",
  "raw_publish_time": "...",
  "raw_amount": "...",
  "raw_body_html": "..."
}
```

#### 标准字段

清洗后的统一字段：

```json
{
  "title": "...",
  "publish_time": "2026-07-02T10:00:00+08:00",
  "budget_amount": 1200000,
  "budget_currency": "CNY",
  "province": "广东省",
  "city": "深圳市",
  "notice_type": "招标公告"
}
```

#### 置信度字段

AI 或弱规则抽取字段必须带置信度：

```json
{
  "deadline": {
    "value": "2026-07-15T17:00:00+08:00",
    "confidence": 0.86,
    "method": "llm_extract",
    "evidence": "投标截止时间：2026年7月15日17时00分"
  }
}
```

### 4.6 附件处理最佳实践

招投标公告经常包含附件：

- PDF
- Word
- Excel
- ZIP
- 图片
- 扫描件

附件处理链路：

```text
发现附件链接
  ↓
下载文件
  ↓
计算 hash
  ↓
识别文件类型
  ↓
解析文本
  ↓
提取表格
  ↓
OCR 扫描件
  ↓
与公告主记录关联
  ↓
存储原文件和解析文本
```

建议保留：

- 原始文件
- 文件 hash
- 下载时间
- 文件大小
- MIME 类型
- 解析状态
- 解析错误
- 提取文本
- 提取表格

### 4.7 监控与告警最佳实践

每个数据源必须有健康监控：

- 采集成功率
- 解析成功率
- 字段缺失率
- 数据量突降
- 数据量异常暴涨
- 页面结构变化
- HTTP 错误率
- 浏览器超时率
- 附件下载失败率
- 去重比例异常
- 最近成功时间

典型告警：

```text
某站点连续 3 次采集失败
某站点今日数据量低于 7 日均值 70%
某字段缺失率从 5% 升到 80%
列表页 selector 匹配数量为 0
详情页正文为空比例超过阈值
```

### 4.8 合规与风控最佳实践

招投标采集尤其要注意合规边界：

- 优先使用公开、合法、授权数据源
- 遵守目标网站 robots、服务条款和访问频率要求
- 不绕过登录权限获取非公开数据
- 不做破坏性高频访问
- 不采集与业务无关的个人敏感信息
- 对联系方式等字段做最小化使用和权限控制
- 记录数据来源和采集时间，方便审计
- 对第三方数据服务确认授权范围和转售限制

如果是企业产品，建议保留：

```text
source_url
source_name
source_license_or_terms
collected_at
raw_snapshot_hash
parser_version
processing_log
```

---

## 5. 如果在 BidMonitor-AI 中实现，推荐方案

结合当前项目方向，如果要做一个接近八爪鱼/招投标垂直平台最佳实践的 BidMonitor-AI，建议产品和工程分层如下。

### 5.1 MVP 阶段

先做可靠的最小闭环：

1. 数据源配置
2. 关键词采集
3. 列表页解析
4. 详情页解析
5. 发布时间增量采集
6. 去重
7. SQLite/Postgres 存储
8. Web 页面查看
9. 简单订阅/筛选
10. Excel/CSV 导出

MVP 不建议一开始追求：

- 3000+ 数据源
- 全站点自动识别
- 复杂 AI 抽取
- OCR
- 大规模并发
- 企业主体图谱

### 5.2 推荐核心数据模型

```text
sources
- id
- name
- base_url
- type
- region
- enabled
- config
- last_success_at
- last_error
- fail_count

notices
- id
- source_id
- source_item_id
- title
- notice_type
- project_name
- project_code
- purchaser
- agency
- region
- industry
- publish_time
- deadline
- budget_amount
- bid_amount
- winner
- detail_url
- content_text
- content_html
- content_hash
- created_at
- updated_at

attachments
- id
- notice_id
- url
- filename
- mime_type
- size
- sha256
- storage_path
- parsed_text
- parse_status

crawl_runs
- id
- source_id
- started_at
- finished_at
- status
- fetched_count
- parsed_count
- inserted_count
- updated_count
- skipped_count
- error_count
- error_message

subscriptions
- id
- name
- keywords
- regions
- industries
- notice_types
- delivery_channels
```

### 5.3 推荐采集器架构

```text
SourceRegistry
  ↓
Scheduler
  ↓
CrawlerRunner
  ↓
SourceAdapter
  ↓
Fetcher
  ├── HTTPFetcher
  ├── BrowserFetcher
  └── DocumentFetcher
  ↓
Parser
  ├── ListParser
  ├── DetailParser
  └── AttachmentParser
  ↓
Normalizer
  ↓
Deduplicator
  ↓
Storage
  ↓
Notifier / API / Exporter
```

每个站点一个 Adapter：

```python
class SourceAdapter:
    def search(self, keyword, since):
        ...

    def parse_list(self, html):
        ...

    def parse_detail(self, html):
        ...

    def normalize(self, item):
        ...
```

### 5.4 推荐技术路线

#### 抓取

- `httpx` / `requests`：优先抓 API 和静态页面
- `Playwright` 或 Selenium：处理 JS 渲染和复杂交互
- 限速、重试、超时、User-Agent 管理
- 每站点独立并发控制

#### 解析

- `BeautifulSoup` / `lxml`
- CSS Selector / XPath
- 正则
- `trafilatura` 或 readability 类库提取正文
- PDF：`pypdf`, `pdfplumber`
- Word：`python-docx`
- Excel：`openpyxl`
- OCR：后续再引入

#### 存储

- MVP：SQLite
- 生产：PostgreSQL
- 搜索：Postgres FTS 或 OpenSearch/Elasticsearch
- 文件：本地目录、S3、MinIO

#### 调度

- MVP：cron / APScheduler
- 生产：Celery / RQ / Dramatiq / Airflow

#### AI 抽取

AI 不应替代规则抽取，而应作为补充：

- 规则能提取的字段先用规则
- 复杂正文中抽 deadline、budget、winner 时用 LLM
- LLM 输出必须有 JSON schema 校验
- 关键字段保留 evidence
- 低置信度进入人工复核

---

## 6. 最佳实践清单

### 数据源

- [ ] 每个站点配置化
- [ ] 记录来源 URL 和采集时间
- [ ] 每站点独立限速
- [ ] 每站点独立健康状态
- [ ] 支持禁用和重跑

### 采集

- [ ] 优先抓官方接口
- [ ] 失败再用浏览器渲染
- [ ] 支持关键词、地区、时间筛选
- [ ] 支持列表页 + 详情页
- [ ] 支持附件下载
- [ ] 支持定时任务
- [ ] 支持滑动窗口增量

### 解析

- [ ] 标题、发布时间、地区、类型必填
- [ ] 正文保留原文
- [ ] 详情链接保留
- [ ] 附件链接保留
- [ ] 金额、截止时间等字段带置信度
- [ ] 解析失败可回放

### 数据质量

- [ ] URL 去重
- [ ] 标题/单位/时间弱去重
- [ ] 正文 hash 去重
- [ ] 附件 hash 去重
- [ ] 地区标准化
- [ ] 金额标准化
- [ ] 公告类型标准化

### 产品化

- [ ] 关键词订阅
- [ ] 地区筛选
- [ ] 行业筛选
- [ ] 公告类型筛选
- [ ] 新公告提醒
- [ ] 变更公告提醒
- [ ] CSV/Excel 导出
- [ ] API 查询
- [ ] 数据源健康看板

### 运维

- [ ] 成功率监控
- [ ] 数据量异常监控
- [ ] 字段缺失率监控
- [ ] Selector 失效告警
- [ ] 附件下载失败告警
- [ ] 每次采集 run 记录
- [ ] 错误日志可追踪

---

## 7. 需要谨慎看待的点

本次调研有几个限制：

1. 大部分证据来自厂商官网和帮助中心。
2. 厂商公开文案能证明其“宣称”和“产品定位”，但不能证明真实性能。
3. 无法独立验证八爪鱼 `3000+` 数据源的完整清单和稳定性。
4. 无法独立验证 AI 字段识别的准确率。
5. 招投标网站结构和反爬策略变化很快，教程的有效性有时间敏感性。
6. 对登录、验证码、附件 OCR、复杂动态页面等场景，公开资料没有足够细节。
7. 一些强断言在验证中被否定，未纳入结论，例如：
   - 火车采集器“几乎所有网页”
   - 后羿能自动识别所有具体结构类型
   - 采招网提供“招标全程跟踪”的强表述

---

## 8. 可直接落地的建议

如果要让 BidMonitor-AI 吸收这些最佳实践，建议下一步按这个顺序做：

1. **先定义 `Source` 配置模型**
   把不同招投标网站的入口、选择器、翻页、增量规则配置化。

2. **实现采集 run 记录**
   每次采集记录抓取数量、成功数量、失败原因、耗时、最后成功时间。

3. **实现发布时间增量采集**
   用 `publish_time` + 滑动窗口，避免重复全量抓取。

4. **实现 notices 标准模型**
   统一标题、公告类型、地区、发布时间、链接、正文、附件字段。

5. **实现去重层**
   先用 `source_id + url`，再加标题/单位/日期 hash。

6. **实现数据源健康看板**
   监控每个源是否失效、字段缺失率是否异常。

7. **最后再上 AI 抽取**
   用于复杂正文里的预算金额、截止时间、中标单位等字段，并保留 evidence 与置信度。

这样会比单纯“仿八爪鱼做一个网页爬虫”更稳，也更接近真正招投标数据产品的实现方式。

---

## 9. 调研来源

主要来源：

- 八爪鱼招投标方案：<https://www.bazhuayu.com/solutions/bidding-and-tendering>
- 八爪鱼招投标采集模板：<https://www.bazhuayu.com/resources/collect-template/tender-bidding>
- 八爪鱼全国公共资源交易平台采集教程：<https://www.bazhuayu.com/helpcenter/docs/quan-guo-gong-gong-zi-yuan-jiao-yi-ping-tai-yong-chu-fa-qi-cai-ji-dang-tian-zui-xin-zhao-biao-shu-ju>
- 八爪鱼官网：<https://www.bazhuayu.com/>
- 火车采集器：<https://www.locoy.com/>
- 后羿采集器：<https://www.houyicaiji.com/>
- 千里马招标网：<https://www.qianlima.com/>
- 采招网：<https://www.bidcenter.com.cn/>
- 中国政府采购网：<http://www.ccgp.gov.cn/>
- 全国公共资源交易平台：<https://www.ggzy.gov.cn/>
- Scrapy Media Pipeline 文档：<https://docs.scrapy.org/en/latest/topics/media-pipeline.html>

## 10. 调研限制

- 主要证据来自厂商官网、帮助中心和产品页面，能证明“厂商如何宣称/定位/设计教程”，不能独立验证实际覆盖率、准确率、稳定性、反爬成功率或客户效果。
- 八爪鱼的 `3000+ 数据源`、`AI 精准识别` 等属于营销口径。
- 采招网、千里马等竞品能力也主要来自其官网文案。
- 招投标网站页面结构和反爬策略具有时间敏感性。
- 对登录、验证码、动态渲染、附件 PDF/Word、图片化表格等复杂场景，各产品公开资料没有足够细节。
