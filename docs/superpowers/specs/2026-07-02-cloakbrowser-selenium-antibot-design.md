# CloakBrowser + Selenium 反爬后端设计

- 日期: 2026-07-02
- 状态: 已确认设计,待实现
- 相关: `src/crawler/selenium_crawler.py`, `src/monitor_core.py`, `Dockerfile`

## 1. 背景与目标

BidMonitor AI 目前的浏览器反爬依赖 `src/crawler/selenium_crawler.py` 中的 `SeleniumCrawler` +
`SharedBrowserManager`,反检测手段较弱且部分自相矛盾:

- `--single-process` 在容器/无头环境会破坏 CDP 注入并导致 Chrome 崩溃。
- 仅伪造 `navigator.webdriver` 一个特征;User-Agent 写死 Chrome/120。
- `_init_driver` 与 `SharedBrowserManager._create_driver` 几乎完全重复(DRY 违反)。
- `monitor_core` 直接 `new SeleniumCrawler(...)`,没有引擎抽象,难以扩展新后端。

**目标**:引入浏览器抽象层,新增 [CloakBrowser](https://github.com/CloakHQ/cloakbrowser)
作为首选隐身后端,形成 `CloakBrowser → Selenium → requests` 的降级链,默认开启隐身 + humanize,
主打**服务器 / Docker headless** 环境。

## 2. 已确认的需求决策

| 项 | 决策 |
|---|---|
| 引擎策略 | CloakBrowser 优先 + Selenium 兜底 + requests 最终兜底 |
| 功能范围 | 默认开启隐身 + `humanize`;`proxy/geoip/timezone/locale` 预留配置接口,默认关闭,暂不接 UI |
| 运行环境 | 以服务器 / Docker headless 为主,桌面版次要 |
| 结构 | 新建 `src/crawler/browser/` 子包做抽象层 + 双后端,`parse` 共享一份 |
| Docker | build 阶段把 CloakBrowser 专用 Chromium 二进制预打进镜像,运行时不联网下载 |
| License | 新增可选 `license_key` 配置项,空则用免费二进制 |

## 3. CloakBrowser API 约束(设计依据)

- 安装:`pip install cloakbrowser`;首次运行自动下载约 200MB **自研补丁版 Chromium**
  (58+ 处 C++ 补丁修改 canvas/WebGL/audio/fonts/GPU/WebRTC/自动化信号)。
- 隐身来自这份专用二进制,**不是** `apt install chromium` 的原版 —— Docker 预打包必须缓存
  CloakBrowser 自己下载的二进制,不能用系统 Chromium 替代。
- 同步 API:`launch(headless, proxy, geoip, humanize, human_preset, timezone, locale, args,
  stealth_args, license_key, extension_paths)` 返回 Playwright `Browser` 对象。
- 用法:`browser.new_page()` / `page.goto(url)` / `page.content()` /
  `page.wait_for_load_state("networkidle")`,与 Playwright 完全兼容。

## 4. 架构

### 4.1 目录结构

```
src/crawler/
  selenium_crawler.py      # 保留:向后兼容 re-export(见 4.5)
  browser/
    __init__.py            # create_browser_crawler(...) 工厂 + 降级链 + 可用性探测
    base_browser.py        # BrowserCrawler ABC:crawl()/parse()/共享链接解析
    cloak_backend.py       # CloakBrowserCrawler(Playwright API)
    selenium_backend.py    # 由现有 selenium_crawler.py 重构迁入并清理
```

### 4.2 抽象层 `base_browser.py`

`BrowserCrawler(ABC)` 提供所有后端共享的行为:

- `name` 属性、`__init__(config, name, url, headless=True)`。
- `crawl(stop_event=None) -> Optional[List[BidInfo]]`:检查停止信号 → `fetch(url)` → `parse(html)`。
- `parse(html) -> List[BidInfo]`:**从现有 `SeleniumCrawler.parse` 抽取的唯一实现**
  (提取 `<a>` 链接、过滤 js/#/mailto、`urljoin` 补全、去重 → `BidInfo`)。两个后端逻辑一致,只写一份。
- `_fetch(url) -> Optional[str]`:**抽象方法**,各后端实现取 HTML。
- `close()`:抽象方法,释放资源。

`fetch` 层复用 base 的指数退避重试策略(参考 `BaseCrawler.fetch`)。

### 4.3 CloakBrowser 后端 `cloak_backend.py`

- `CLOAK_AVAILABLE` / `IMPORT_ERROR_MSG`:import 失败时优雅降级(照抄现有 Selenium 的模式)。
- 全局单例 `CloakBrowserManager` 复用**一个 browser 进程**(类比 `SharedBrowserManager`),
  线程锁保护;每个站点 `browser.new_context()` 隔离 cookie/状态,抓完 `context.close()`。
- `launch` 参数由 config 组装:`headless=True, humanize=True, stealth_args=True`,
  `proxy/geoip/timezone/locale/license_key` 读 config,缺省不传(用库默认)。
- `_fetch`:`page.goto(url, wait_until="domcontentloaded")` →
  `page.wait_for_load_state("networkidle", timeout=...)`(超时容忍)→ 拟人小延时 → `page.content()`。
- 超时/异常 → 返回 None,交给 base 重试。

### 4.4 Selenium 后端 `selenium_backend.py`(兜底,轻量清理)

从现有 `selenium_crawler.py` 迁入并修复:

- **移除 `--single-process`**。
- UA 改为从 `base.USER_AGENTS` 池随机取(不再写死 Chrome/120)。
- 补充 stealth 补丁:`navigator.languages`、`navigator.plugins`、WebGL vendor/renderer
  (在现有 `navigator.webdriver` 基础上)。
- 合并 `_init_driver` 与 `SharedBrowserManager._create_driver` 的重复代码为单一
  `_build_options()` + `_create_driver()`,由独立爬虫和共享管理器共用。
- 继承 `BrowserCrawler`,只实现 `_fetch`/`close`,复用共享的 `parse`。

### 4.5 工厂与降级链 `__init__.py`

```
create_browser_crawler(config, name, url, headless=True) -> BrowserCrawler | None
```

- 依次探测:CloakBrowser 可用 → 返回 `CloakBrowserCrawler`;否则 Selenium 可用 →
  `SeleniumCrawler`;都不可用 → 返回 `None`(由调用方回落 requests)。
- 探测只看 import 标志,不启动真实浏览器,便于单测 mock。

`selenium_crawler.py` 保留为**兼容 shim**:`from crawler.browser.selenium_backend import SeleniumCrawler`
以及 `SharedBrowserManager` re-export,保证 `monitor_core` 现有 import 不断。

### 4.6 接入 `monitor_core.py`

- `use_selenium` 开关语义升级为"**浏览器模式开关**"(**向后兼容**:`use_selenium: true` 仍有效)。
- 现有两处 `SeleniumCrawler(crawler_config, name, url, headless=True)`
  (默认站点 loop + 自定义站点 loop)改为 `create_browser_crawler(...)`;
  返回 `None` 时 log 警告并回落 `CustomCrawler`(requests)。
- 收尾处 `SharedBrowserManager.close()` 改为关闭两类共享浏览器(Cloak + Selenium),
  经由抽象层的统一 `shutdown_browsers()` 完成。

## 5. Docker 打包

- **系统依赖**:安装 CloakBrowser Chromium 运行所需库(`libnss3 libatk1.0-0 libatk-bridge2.0-0
  libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1
  libasound2` + 字体如 `fonts-liberation`,以最终依赖清单为准)。
- **预下载二进制**:build 阶段执行 CloakBrowser 的二进制下载(`cloakbrowser install` 或一次
  headless `launch()` 预热),把约 200MB 专用 Chromium 缓存进镜像层;下载失败**仅告警不阻断构建**
  (运行时仍可回落 Selenium/requests)。
- 记录 build 未成功预下载时的行为(首次运行降级),避免"静默假设已内置"。

## 6. 测试策略(TDD)

无需真实浏览器即可覆盖的核心逻辑,优先写:

- **降级链选择**:mock `CLOAK_AVAILABLE`/`SELENIUM_AVAILABLE` 各组合,断言 `create_browser_crawler`
  返回正确类型或 `None`。
- **共享链接解析器**:静态 HTML fixture 喂 `BrowserCrawler.parse`,断言链接提取/过滤/去重/`BidInfo` 字段。
- **config 默认值**:`humanize` 默认 True、`proxy/geoip` 默认关、`license_key` 缺省不传。
- **import 安全**:缺 `cloakbrowser` 或 `selenium` 时模块可导入且优雅降级(照现有 Selenium 测试模式)。
- **兼容 shim**:`from crawler.selenium_crawler import SeleniumCrawler, SharedBrowserManager` 仍可用。
- **Docker 打包测试**:扩展现有 `tests/test_docker_packaging.py`,断言 Dockerfile 含 Chromium 依赖与预下载步骤。

真实浏览器冒烟测(实际 `launch()` 抓一个页面)标记为 slow/optional,不进默认 CI 门禁。

## 7. 非目标(YAGNI)

- 不做代理池轮换 UI、不做验证码自动求解服务、不做 requests→浏览器的逐页自动升级。
- 不重写 40+ 个继承 `BaseCrawler` 的站点爬虫;它们继续走 requests,浏览器模式只作用于默认站点/自定义站点。
- 不引入 `undetected-chromedriver`(Selenium 仅作兜底,保持轻量)。

## 8. 风险

- CloakBrowser 为较新的第三方库,API 可能变动;抽象层隔离了它,替换成本可控。
- 200MB 二进制显著增大镜像体积;通过分层缓存与"下载失败不阻断"缓解。
- humanize 会增加单页抓取耗时;通过共享 browser 进程 + per-context 隔离平衡。
