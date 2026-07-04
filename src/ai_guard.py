import json
import logging
import re

try:
    from .utils.logging_text import strip_log_icons
except ImportError:  # pragma: no cover
    from utils.logging_text import strip_log_icons

class AIGuard:
    def __init__(self, config=None, log_callback=None):
        self.logger = logging.getLogger("AIGuard")
        self.log_callback = log_callback  # GUI日志回调
        self.update_config(config)

    def log(self, message):
        """输出日志到GUI和logger"""
        message = strip_log_icons(message)
        if self.log_callback:
            self.log_callback(message)
        self.logger.info(message)

    def update_config(self, config):
        if not config:
            self.enabled = False
            return
            
        self.api_key = config.get('api_key', '')
        self.base_url = config.get('base_url', 'https://cc.honoursoft.cn/').rstrip('/')
        self.model = config.get('model', 'claude-sonnet-4-5-20250929-thinking')
        self.endpoint_type = config.get('endpoint_type') or self._infer_endpoint_type(self.base_url)
        self.enabled = config.get('enable', False)
        self.custom_prompt = config.get('prompt', '')
        self.filter_keywords = config.get('filter_keywords') or []
        self.must_contain_keywords = config.get('must_contain_keywords') or []
        self.exclude_keywords = config.get('exclude_keywords') or []

    def _build_system_prompt(self):
        if self.custom_prompt:
            return self.custom_prompt

        filter_keywords = "、".join(self.filter_keywords) if self.filter_keywords else "当前配置的业务关键词"
        must_contain = "、".join(self.must_contain_keywords) if self.must_contain_keywords else "无"
        exclude = "、".join(self.exclude_keywords) if self.exclude_keywords else "无"
        return (
            "你是一个专业的招投标项目筛选专家。"
            "请根据当前业务关键词判断该网页是否值得进入结果中心，不要臆造信息。\n\n"
            f"业务关键词: {filter_keywords}\n"
            f"必须包含线索: {must_contain}\n"
            f"排除关键词: {exclude}\n\n"
            "判为相关: 标题或内容明确涉及业务关键词对应的工程、采购、维保、改造、建设、服务、公告、意向或结果信息。\n"
            "判为不相关: 广告页、平台推广页、纯新闻资讯、登录页、帮助页、完全无关行业、或命中排除关键词且没有有效业务线索。\n"
            "返回JSON: {\"relevant\": true/false, \"reason\": \"50字以内的判断理由\"}"
        )

    def _infer_endpoint_type(self, base_url):
        lower = (base_url or '').rstrip('/').lower()
        if lower.endswith('/chat/completions'):
            return 'chat_completions'
        if 'honoursoft' in lower:
            return 'claude_native'
        return 'responses'

    def _endpoint_url(self):
        base_url = self.base_url.rstrip('/')
        if self.endpoint_type == 'chat_completions' and base_url.endswith('/v1'):
            return f"{base_url}/chat/completions"
        if self.endpoint_type == 'responses' and base_url.endswith('/v1'):
            return f"{base_url}/responses"
        return base_url

    def _extract_response_text(self, result):
        if self.endpoint_type == 'responses':
            output_text = result.get('output_text')
            if output_text:
                return output_text
            output = result.get('output') or []
            for item in output:
                for content in item.get('content') or []:
                    if content.get('text'):
                        return content.get('text')
            return ''
        return result['choices'][0]['message']['content']

    def _extract_json_text(self, ai_content):
        """Extract a JSON object from common model response shapes."""
        text = (ai_content or "").strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.IGNORECASE | re.DOTALL)
        if fenced:
            return fenced.group(1).strip()
        if "{" in text and "}" in text:
            start = text.find("{")
            end = text.rfind("}") + 1
            return text[start:end]
        return text

    def _coerce_relevant_value(self, value):
        """Normalize model boolean output; string 'false' must not become truthy."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized = value.strip().lower()
            negative_values = {"false", "no", "n", "0", "否", "不", "不相关", "无关", "不符合", "非相关"}
            positive_values = {"true", "yes", "y", "1", "是", "相关", "符合"}
            if normalized in negative_values:
                return False
            if normalized in positive_values:
                return True
        return False

    def _infer_relevance_from_text(self, ai_content):
        """Best-effort fallback for non-JSON model output, checking negative signals first."""
        text = (ai_content or "").strip()
        lower = text.lower()

        negative_patterns = [
            r"\brelevant\s*[:：]\s*false\b",
            r"\bfalse\b",
            r"\bnot\s+relevant\b",
            r"\birrelevant\b",
            r"不\s*相关",
            r"无关",
            r"不\s*符合",
            r"非相关",
            r"无需跟进",
            r"不建议",
        ]
        if any(re.search(pattern, lower) for pattern in negative_patterns):
            return False

        unknown_patterns = [
            r"无法判断",
            r"不能判断",
            r"无法确定",
            r"不能确定",
            r"不确定",
            r"未知",
            r"无法识别",
        ]
        if any(re.search(pattern, lower) for pattern in unknown_patterns):
            return None

        positive_patterns = [
            r"\brelevant\s*[:：]\s*true\b",
            r"\btrue\b",
            r"^相关$",
            r"^是相关$",
            r"该?项目相关",
            r"相关\s*[:：]",
            r"判定.*相关",
            r"符合",
            r"建议跟进",
            r"值得",
        ]
        if any(re.search(pattern, lower) for pattern in positive_patterns):
            return True

        return None

    def check_relevance(self, title, content="", raise_on_error=False):
        """
        检查项目是否与无人机巡检相关
        返回: (is_relevant: bool, reason: str)
        """
        if not self.enabled:
            return True, "AI未启用"

        if not self.api_key:
            return True, "AI未配置Key"

        self.log(f"🤖 [AI分析] 开始分析: {title[:40]}...")

        system_prompt = self._build_system_prompt()

        user_content = f"项目标题: {title}\n项目内容: {content[:800]}"

        # 判断是否使用 Claude 原生格式（基于模型名称和URL）
        is_claude_native = (
            self.endpoint_type == 'claude_native' or (
                'claude' in self.model.lower() and
                'honoursoft' in self.base_url.lower()
            )
        )
        
        # 构造请求payload（自动兼容 Claude 和 OpenAI/DeepSeek 格式）
        if is_claude_native:
            # Claude 原生格式：system 作为顶级参数
            payload = {
                "model": self.model,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.1,
                "max_tokens": 300
            }
        elif self.endpoint_type == 'responses':
            payload = {
                "model": self.model,
                "instructions": system_prompt,
                "input": user_content,
                "temperature": 0.1,
                "max_output_tokens": 300
            }
        else:
            # OpenAI/DeepSeek 兼容格式：system 在 messages 数组中
            payload = {
                "model": self.model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                "temperature": 0.1,
                "max_tokens": 300
            }

        url = self._endpoint_url()

        self.log(f"🔗 [AI分析] 请求API: {self.base_url}")
        self.log(f"📦 [AI分析] 使用模型: {self.model}")

        try:
            import requests
            import time
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }
            
            max_retries = 3
            retry_delay = 2  # 秒
            
            for attempt in range(max_retries):
                try:
                    self.log(f"⏳ [AI分析] 正在等待AI响应...")
                    resp = requests.post(url, headers=headers, json=payload, timeout=120)
                    
                    if resp.status_code != 200:
                        error_detail = resp.text[:200]
                        self.log(f"❌ [AI分析] API返回错误: HTTP {resp.status_code}")
                        raise Exception(f"HTTP {resp.status_code}: {error_detail}")
                    
                    result = resp.json()
                    ai_content = self._extract_response_text(result)
                    
                    self.log(f"✅ [AI分析] 收到AI响应")
                    
                    # 解析AI返回的JSON
                    try:
                        json_str = self._extract_json_text(ai_content)
                        analysis = json.loads(json_str)
                        is_relevant = self._coerce_relevant_value(analysis.get('relevant', False))
                        reason = analysis.get('reason', 'AI未提供理由')
                        
                        if is_relevant:
                            self.log(f"✅ [AI判定] 相关 - {reason}")
                        else:
                            self.log(f"🚫 [AI判定] 不相关 - {reason}")
                            
                        return is_relevant, reason
                        
                    except json.JSONDecodeError:
                        # 如果无法解析JSON，尝试从文本判断
                        self.log(f"⚠️ [AI分析] 返回非标准JSON，尝试文本分析")
                        is_relevant = self._infer_relevance_from_text(ai_content)
                        if is_relevant is None:
                            self.log(f"⚠️ [AI判定] 未知 - {ai_content[:80]}")
                            return False, f"AI结果未知: {ai_content[:60]}"
                        if is_relevant:
                            self.log(f"✅ [AI判定] 相关 - {ai_content[:80]}")
                        else:
                            self.log(f"🚫 [AI判定] 不相关 - {ai_content[:80]}")
                        return is_relevant, ai_content[:80]
                        
                except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                    # 网络连接错误或超时，可以重试
                    if attempt < max_retries - 1:
                        self.log(f"⚠️ [AI分析] 网络异常，{retry_delay}秒后重试 ({attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                    else:
                        self.log(f"❌ [AI分析] 网络异常，已重试{max_retries}次仍失败")
                        if raise_on_error:
                            raise
                        return False, f"AI请求异常: 网络异常（已重试{max_retries}次）"

        except ImportError:
            self.log(f"❌ [AI分析] 缺少requests库")
            return False, "AI请求异常: 请安装 requests 库"
        except Exception as e:
            error_msg = str(e)
            self.log(f"❌ [AI分析] 请求失败: {error_msg[:100]}")
            self.logger.error(f"AI请求失败: {error_msg}")
            if raise_on_error:
                raise
            return False, f"AI请求异常: {error_msg[:50]}"
