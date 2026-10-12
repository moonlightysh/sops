# -*- coding: utf-8 -*-
"""SOPS PluginNode: HTTP Health Check (my_http_check)"""

from __future__ import absolute_import
import logging
import time
import urllib.request
import urllib.error

from django.utils.translation import ugettext_lazy as _

from pipeline.conf import settings
from pipeline.component_framework.component import Component
from pipeline.core.flow.activity import Service
from pipeline.core.flow.io import StringItemSchema, IntItemSchema, BooleanItemSchema

__group_name__ = _("Custom Plugins")
logger = logging.getLogger(__name__)


class MyHttpCheckService(Service):

    def inputs_format(self):
        return [
            self.InputItem(
                name=_('Target URL'),
                key='url',
                type='string',
                schema=StringItemSchema(description=_('Target URL')),
            ),
            self.InputItem(
                name=_('Method (default GET)'),
                key='method',
                type='string',
                schema=StringItemSchema(description=_('Method (default GET)')),
            ),
            self.InputItem(
                name=_('Timeout sec (default 10)'),
                key='timeout',
                type='int',
                schema=IntItemSchema(description=_('Timeout sec (default 10)')),
            ),
            self.InputItem(
                name=_('Expected status (default 200)'),
                key='expect_status',
                type='int',
                schema=IntItemSchema(description=_('Expected status (default 200)')),
            ),
            self.InputItem(
                name=_('Keyword in body (optional)'),
                key='keyword',
                type='string',
                schema=StringItemSchema(description=_('Keyword in body (optional)')),
            ),
        ]

    def outputs_format(self):
        return [
            self.OutputItem(
                name=_('Actual status'),
                key='status_code',
                type='int',
                schema=IntItemSchema(description=_('Actual status')),
            ),
            self.OutputItem(
                name=_('Response ms'),
                key='response_time',
                type='int',
                schema=IntItemSchema(description=_('Response ms')),
            ),
            self.OutputItem(
                name=_('Body preview (first 200 chars)'),
                key='body_preview',
                type='string',
                schema=StringItemSchema(description=_('Body preview (first 200 chars)')),
            ),
            self.OutputItem(
                name=_('Passed'),
                key='ok',
                type='bool',
                schema=BooleanItemSchema(description=_('Passed')),
            ),
        ]

    def execute(self, data, parent_data):
        """执行 HTTP 健康检查：请求 URL → 比对状态码 → 可选关键词匹配。

        返回 True 表示检查逻辑本身执行成功（无论 HTTP 结果是否符合预期）。
        调用方通过 data.outputs.ok 判断"Passed"。
        """
        url = data.get_one_of_inputs('url') or ''
        if not url:
            logger.error('my_http_check: url is empty')
            data.outputs.ok = False
            data.outputs.status_code = 0
            data.outputs.response_time = 0
            data.outputs.body_preview = ''
            return True

        method = (data.get_one_of_inputs('method') or 'GET').upper()
        timeout = int(data.get_one_of_inputs('timeout') or 10)
        expect = int(data.get_one_of_inputs('expect_status') or 200)
        keyword = data.get_one_of_inputs('keyword') or ''

        status_code = 0
        body_preview = ''
        ok = False

        start = time.time()
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status_code = resp.getcode()
                body = resp.read().decode('utf-8', errors='replace')
                body_preview = body[:200]
        except urllib.error.HTTPError as e:
            status_code = e.code
            try:
                body_preview = e.read().decode('utf-8', errors='replace')[:200]
            except Exception:
                body_preview = ''
        except urllib.error.URLError as e:
            logger.warning('my_http_check URL error %s: %s', url, e)
            body_preview = str(e)[:200]
        except Exception as e:
            logger.warning('my_http_check request failed %s: %r', url, e)
            body_preview = str(e)[:200]

        elapsed_ms = int((time.time() - start) * 1000)

        # 判定：状态码匹配 +（关键词为空或关键词命中响应体）
        status_ok = (status_code == expect)
        keyword_ok = (not keyword) or (keyword in body_preview)
        ok = status_ok and keyword_ok

        data.outputs.status_code = status_code
        data.outputs.response_time = elapsed_ms
        data.outputs.body_preview = body_preview
        data.outputs.ok = ok

        logger.info('my_http_check %s %s -> status=%d expect=%d ok=%s time=%dms',
                    method, url, status_code, expect, ok, elapsed_ms)
        return True


class MyHttpCheckComponent(Component):
    name = _("HTTP Health Check")
    code = "my_http_check"
    bound_service = MyHttpCheckService
    form = '%scomponents/atoms/custom/my_http_check.js' % settings.STATIC_URL
