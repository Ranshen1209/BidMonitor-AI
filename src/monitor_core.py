"""
监控核心模块 - 整合爬虫、匹配、通知功能
"""
import logging
from typing import List, Dict, Any, Optional, Callable
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from .database.storage import Storage, BidInfo
    from .matcher.keyword import KeywordMatcher
    from .results.ai_extractor import enrich_new_bid

    from .crawler.ccgp import CCGPCrawler
    from .crawler.chinabidding import ChinaBiddingCrawler
    from .crawler.ebnew import EbnewCrawler
    from .crawler.plap import PLAPCrawler
    from .crawler.ggzy import GGZYCrawler
    from .crawler.bidcenter import BidcenterCrawler
    from .crawler.qianlima import QianlimaCrawler
    from .crawler.chinatender import ChinaTenderCrawler
    from .crawler.solarbe import SolarbeCrawler
    from .crawler.pvyuan import PvyuanCrawler
    from .crawler.dlnyzb import DlnyzbCrawler
    from .crawler.youuav import YouuavCrawler
except ImportError:
    from database.storage import Storage, BidInfo
    from matcher.keyword import KeywordMatcher
    from results.ai_extractor import enrich_new_bid

    from crawler.ccgp import CCGPCrawler
    from crawler.chinabidding import ChinaBiddingCrawler
    from crawler.ebnew import EbnewCrawler
    from crawler.plap import PLAPCrawler
    from crawler.ggzy import GGZYCrawler
    from crawler.bidcenter import BidcenterCrawler
    from crawler.qianlima import QianlimaCrawler
    from crawler.chinatender import ChinaTenderCrawler
    from crawler.solarbe import SolarbeCrawler
    from crawler.pvyuan import PvyuanCrawler
    from crawler.dlnyzb import DlnyzbCrawler
    from crawler.youuav import YouuavCrawler

from crawler.browser import create_browser_crawler, shutdown_browsers

# 爬虫注册表
def get_all_crawlers():
    """获取所有爬虫类"""
    return {
        'chinabidding': ChinaBiddingCrawler,
    }

DEFAULT_URL_LIST_PATH = "/Users/cervine/Documents/Rule-Project/projects/opportunity-collection/output/materials/bid_related_url_list.txt"


def _looks_like_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


# 默认内置网站配置 (用于通用爬虫)
def get_default_sites():
    """从外部 URL 清单生成默认内置网站列表。"""
    sites = {}
    if not os.path.exists(DEFAULT_URL_LIST_PATH):
        return sites

    seen = set()
    with open(DEFAULT_URL_LIST_PATH, 'r', encoding='utf-8-sig') as f:
        for line in f:
            url = line.strip()
            if not _looks_like_url(url) or url in seen:
                continue
            seen.add(url)
            key = f"url_list_{len(sites) + 1:03d}"
            sites[key] = {
                'name': f"上海招投标URL {len(sites) + 1:03d}",
                'url': url
            }
    return sites


class MonitorCore:
    """监控核心类"""
    
    def __init__(self, 
                 keywords: List[str],
                 exclude_keywords: List[str] = None,
                 must_contain_keywords: List[str] = None,
                 notify_method: str = "email",
                 email: str = "",
                 phone: str = "",
                 email_config: Dict[str, Any] = None,
                 sms_config: Dict[str, Any] = None,
                 log_callback: Callable[[str], None] = None,
                 ai_config: Dict[str, Any] = None,
                 crawler_overrides: Dict[str, Any] = None):
        """
        初始化监控核心
        
        Args:
            keywords: 搜索关键字列表 (OR组 - 行业词)
            exclude_keywords: 排除关键字列表
            must_contain_keywords: 必须包含关键字列表 (AND组 - 产品词)
            notify_method: 通知方式 (email/sms/both)
            email: 邮箱地址
            phone: 手机号
            email_config: 邮件配置
            sms_config: 短信配置
            log_callback: 日志回调函数
        """
        self.keywords = keywords
        self.exclude_keywords = exclude_keywords or []
        self.must_contain_keywords = must_contain_keywords or []
        self.notify_method = notify_method
        self.email = email
        self.phone = phone
        self.log_callback = log_callback or (lambda x: None)
        self.crawler_overrides = crawler_overrides or {}
        self.ai_config_for_extraction = ai_config or {}
        
        # 初始化组件
        self.storage = Storage()
        self.matcher = KeywordMatcher(keywords, exclude_keywords, must_contain_keywords)
        
        # 加载配置文件
        self.config = self._load_config()
        self._apply_crawler_overrides()
        
        # 初始化通知器
        if email_config:
            from notifier.email import EmailNotifier
            self.email_notifier = EmailNotifier(email_config)
        elif self.config.get('email'):
            from notifier.email import EmailNotifier
            email_cfg = self.config['email'].copy()
            if email:
                email_cfg['receiver'] = email
            self.email_notifier = EmailNotifier(email_cfg)
        else:
            self.email_notifier = None
        
        if sms_config:
            from notifier.sms import SMSNotifier
            self.sms_notifier = SMSNotifier(sms_config)
        elif self.config.get('sms'):
            from notifier.sms import SMSNotifier
            self.sms_notifier = SMSNotifier(self.config['sms'])
        else:
            self.sms_notifier = None
        
        # 初始化 AI 守卫
        self.ai_guard = None
        if ai_config and ai_config.get('enable'):
            try:
                from ai_guard import AIGuard
                self.ai_guard = AIGuard(ai_config, log_callback=self.log)
                self.log("✅ [AI] 智能过滤已启用")
            except Exception as e:
                self.log(f"[WARN] AI初始化失败: {e}")
        
        # 初始化爬虫
        self.crawlers = self._init_crawlers()

    def _apply_crawler_overrides(self):
        """应用 Web 配置传入的爬虫相关覆盖项。"""
        if not self.crawler_overrides:
            return

        crawler_config = self.config.get('crawler', {})
        for key in ['enabled_sites', 'use_selenium']:
            if key in self.crawler_overrides:
                crawler_config[key] = self.crawler_overrides[key]
        self.config['crawler'] = crawler_config

        for key in ['custom_sites', 'csv_url_sources']:
            if key in self.crawler_overrides:
                self.config[key] = self.crawler_overrides[key]
    
    def clear_data(self):
        """清空所有历史数据"""
        self.storage.clear_all()
        self.log("All history data cleared.")

    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件"""
        config_paths = [
            'config/config.yaml',
            '../config/config.yaml',
            os.path.join(os.path.dirname(__file__), '..', 'config', 'config.yaml')
        ]
        
        for path in config_paths:
            if os.path.exists(path):
                import yaml
                with open(path, 'r', encoding='utf-8') as f:
                    return yaml.safe_load(f) or {}
        
        return {}
    
    def _init_crawlers(self) -> List:
        """初始化所有爬虫"""
        crawlers = []
        crawler_config = self.config.get('crawler', {})
        crawler_config['search_keywords'] = self.keywords[:3]
        crawler_config['log_callback'] = self.log
        
        # 获取启用的网站列表
        enabled = crawler_config.get('enabled_sites', [])
        
        # 1. 加载内置爬虫类
        crawler_classes = get_all_crawlers()
        
        for name in enabled:
            if name in crawler_classes:
                try:
                    crawler = crawler_classes[name](crawler_config)
                    crawlers.append(crawler)
                    self.log(f"[OK] Loaded crawler: {name}")
                except Exception as e:
                    self.log(f"[WARN] Failed to load crawler {name}: {e}")
        
        # 浏览器模式开关（向后兼容 use_selenium）
        use_selenium = crawler_config.get('use_selenium', False)
        self.log(f"[DEBUG] 浏览器模式: {'启用' if use_selenium else '禁用'}")

        # 2. 加载默认内置网站
        if use_selenium:
            self.log("[DEBUG] 浏览器模式已启用(CloakBrowser→Selenium→requests 降级)")

        from crawler.custom import CustomCrawler
        default_sites = get_default_sites()
        
        for key in enabled:
            if key in default_sites and key not in crawler_classes:
                site = default_sites[key]
                try:
                    if use_selenium:
                        crawler = create_browser_crawler(crawler_config, site['name'], site['url'], headless=True)
                        if crawler is None:
                            self.log(f"[WARN] 无浏览器后端,回落 requests: {site['name']}")
                            crawler = CustomCrawler(crawler_config, site['name'], site['url'])
                        else:
                            self.log(f"[OK] Loaded site (browser): {site['name']}")
                    else:
                        crawler = CustomCrawler(crawler_config, site['name'], site['url'])
                        self.log(f"[OK] Loaded site: {site['name']}")
                    crawlers.append(crawler)
                except Exception as e:
                    self.log(f"[WARN] Failed to load site {site['name']}: {e}")
        
        # 3. 加载用户自定义爬虫
        custom_sites = self.config.get('custom_sites', [])
        for site in custom_sites:
            try:
                name = site.get('name', 'Unknown')
                url = site.get('url', '')
                if name and url:
                    if use_selenium:
                        crawler = create_browser_crawler(crawler_config, name, url, headless=True)
                        if crawler is None:
                            self.log(f"[WARN] 无浏览器后端,回落 requests: {name}")
                            crawler = CustomCrawler(crawler_config, name, url)
                        else:
                            self.log(f"[OK] Loaded custom (browser): {name}")
                    else:
                        crawler = CustomCrawler(crawler_config, name, url)
                        self.log(f"[OK] Loaded custom crawler: {name}")
                    crawlers.append(crawler)
            except Exception as e:
                self.log(f"[WARN] Failed to load custom crawler {site.get('name')}: {e}")

        # 4. 加载 URL 清单爬虫（txt/csv）
        csv_url_sources = self.config.get('csv_url_sources', [])
        if csv_url_sources:
            try:
                from crawler.url_list import UrlListCrawler
                for source in csv_url_sources:
                    if not source.get('enabled', True):
                        continue
                    name = source.get('name', 'URL列表')
                    file_path = source.get('file_path', '')
                    if not file_path:
                        self.log(f"[WARN] URL list source {name} missing file_path")
                        continue
                    crawler = UrlListCrawler(crawler_config, source)
                    crawlers.append(crawler)
                    self.log(f"[OK] Loaded URL list crawler: {name}")
            except Exception as e:
                self.log(f"[WARN] Failed to load URL list crawler: {e}")
        
        return crawlers
    
    def log(self, message: str):
        """记录日志"""
        logging.info(message)
        self.log_callback(message)
    
    def run_once(self, progress_callback=None, stop_event=None) -> Dict[str, Any]:
        """
        执行一次监控
        
        Args:
            progress_callback: 进度回调函数 (current, total, site_name)
            stop_event: 停止事件，用于中断爬取
        
        Returns:
            结果字典，包含 new_count, failed_sites 等
        """
        self.log("=" * 40)
        self.log(f"Start crawling at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        all_matched_bids = []
        failed_sites = []
        total_crawlers = len(self.crawlers)
        
        # AI 过滤统计
        ai_stats = {
            'keyword_matched': [],  # 关键词匹配的项目 (title, url)
            'ai_approved': [],      # AI 判定相关的项目 (title, url, reason)
            'ai_rejected': [],      # AI 判定不相关的项目 (title, url, reason)
        }
        
        for idx, crawler in enumerate(self.crawlers, 1):
            # 检查停止信号
            if stop_event and stop_event.is_set():
                self.log("检测到停止信号，中断爬取")
                break
            
            # 调用进度回调
            if progress_callback:
                progress_callback(idx, total_crawlers, crawler.name)
            
            try:
                self.log(f"Crawling: {crawler.name}...")
                bids = crawler.crawl(stop_event=stop_event)
                
                # 爬取后再次检查停止信号
                if stop_event and stop_event.is_set():
                    self.log("检测到停止信号，中断处理")
                    break
                
                if bids is None:
                    # 爬取失败
                    failed_sites.append({
                        'name': crawler.name,
                        'error': 'Failed to fetch data (possibly blocked)'
                    })
                    self.log(f"[FAILED] {crawler.name}: Website may be blocking requests!")
                    continue
                
                # 匹配关键字
                matched_count = 0
                for bid in bids:
                    # 在匹配过程中也检查停止信号
                    if stop_event and stop_event.is_set():
                        self.log("检测到停止信号，中断匹配")
                        break
                    
                    result = self.matcher.match_any(bid.title, bid.content)
                    
                    if result.matched:
                        # 记录关键词匹配的项目
                        ai_stats['keyword_matched'].append({
                            'title': bid.title,
                            'url': bid.url
                        })
                        
                        # AI 二次过滤 (如果启用)
                        if self.ai_guard:
                            ai_relevant, ai_reason = self.ai_guard.check_relevance(bid.title, bid.content or "")
                            if not ai_relevant:
                                ai_stats['ai_rejected'].append({
                                    'title': bid.title,
                                    'url': bid.url,
                                    'reason': ai_reason
                                })
                                self.log(f"[AI过滤] 跳过: {bid.title[:30]}... (原因: {ai_reason})")
                                continue
                            else:
                                ai_stats['ai_approved'].append({
                                    'title': bid.title,
                                    'url': bid.url,
                                    'reason': ai_reason
                                })
                        
                        if not self.storage.exists(bid):
                            result_id = self.storage.save(bid, notified=False)
                            if result_id:
                                all_matched_bids.append(bid)
                                matched_count += 1
                                enrich_new_bid(
                                    self.storage,
                                    result_id,
                                    bid,
                                    self.ai_config_for_extraction,
                                    log_callback=self.log,
                                )
                
                self.log(f"[OK] {crawler.name}: Found {len(bids)} items, {matched_count} new matches")
                
            except Exception as e:
                failed_sites.append({'name': crawler.name, 'error': str(e)})
                self.log(f"[ERROR] {crawler.name}: {e}")
        
        # 发送通知
        if all_matched_bids:
            self.log(f"Sending notifications for {len(all_matched_bids)} new items...")
            self._send_notifications(all_matched_bids)
        else:
            self.log("No new matching items found")
        
        # 报告失败的网站
        if failed_sites:
            self.log("-" * 40)
            self.log(f"WARNING: {len(failed_sites)} site(s) failed:")
            for site in failed_sites:
                self.log(f"  - {site['name']}: {site['error']}")
        
        # 输出 AI 过滤汇总报告
        if self.ai_guard and (ai_stats['keyword_matched'] or ai_stats['ai_approved'] or ai_stats['ai_rejected']):
            self.log("")
            self.log("=" * 50)
            self.log("📊 本次检索汇总报告")
            self.log("=" * 50)
            self.log(f"🔍 关键词匹配结果: {len(ai_stats['keyword_matched'])} 条")
            
            if ai_stats['keyword_matched']:
                self.log("   匹配的网页链接:")
                for item in ai_stats['keyword_matched'][:10]:  # 最多显示10条
                    self.log(f"   • {item['title'][:40]}...")
                    self.log(f"     {item['url']}")
                if len(ai_stats['keyword_matched']) > 10:
                    self.log(f"   ... 还有 {len(ai_stats['keyword_matched']) - 10} 条")
            
            self.log("")
            self.log(f"✅ AI判断符合要求: {len(ai_stats['ai_approved'])} 条")
            if ai_stats['ai_approved']:
                for item in ai_stats['ai_approved'][:5]:
                    self.log(f"   ✓ {item['title'][:35]}... (理由: {item['reason']})")
            
            self.log("")
            self.log(f"❌ AI判断不符合: {len(ai_stats['ai_rejected'])} 条")
            if ai_stats['ai_rejected']:
                for item in ai_stats['ai_rejected'][:5]:
                    self.log(f"   ✗ {item['title'][:35]}... (理由: {item['reason']})")
            
            self.log("=" * 50)
        
        self.log("=" * 40)
        
        # 关闭共享浏览器以释放内存
        try:
            shutdown_browsers()
            self.log("✅ 已关闭共享浏览器,释放内存")
        except Exception:
            pass
        
        return {
            'new_count': len(all_matched_bids),
            'failed_sites': failed_sites,
            'total_crawlers': len(self.crawlers),
            'ai_stats': ai_stats
        }
    
    def _send_notifications(self, bids: List[BidInfo]):
        """发送通知"""
        success = False
        
        if self.notify_method in ('email', 'both') and self.email_notifier:
            try:
                if self.email:
                    # 临时修改收件人
                    original_receiver = self.email_notifier.receiver
                    self.email_notifier.receiver = self.email
                    success = self.email_notifier.send(bids)
                    self.email_notifier.receiver = original_receiver
                else:
                    success = self.email_notifier.send(bids)
                
                if success:
                    self.log(f"[OK] Email sent to {self.email or self.email_notifier.receiver}")
            except Exception as e:
                self.log(f"[ERROR] Email failed: {e}")
        
        if self.notify_method in ('sms', 'both') and self.sms_notifier:
            try:
                if self.phone:
                    success = self.sms_notifier.send(self.phone, bids)
                    if success:
                        self.log(f"[OK] SMS sent to {self.phone}")
            except Exception as e:
                self.log(f"[ERROR] SMS failed: {e}")
        
        if success:
            for bid in bids:
                self.storage.mark_notified(bid)
