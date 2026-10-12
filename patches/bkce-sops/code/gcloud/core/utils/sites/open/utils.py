# -*- coding: utf-8 -*-
"""
Tencent is pleased to support the open source community by making 蓝鲸智云PaaS平台社区版 (BlueKing PaaS Community
Edition) available.
Copyright (C) 2017 THL A29 Limited, a Tencent company. All rights reserved.
Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
You may obtain a copy of the License at
http://opensource.org/licenses/MIT
Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License.
"""

import logging

from django.core.cache import cache

from gcloud.conf import settings
from gcloud import exceptions
from gcloud.core.models import EnvironmentVariables
from gcloud.core.api_adapter import get_user_info

logger = logging.getLogger("root")
get_client_by_user = settings.ESB_GET_CLIENT_BY_USER
CACHE_PREFIX = __name__.replace(".", "_")
DEFAULT_CACHE_TIME_FOR_CC = settings.DEFAULT_CACHE_TIME_FOR_CC


# LOCAL-ONLY PATCH: business list is served from the local core_business table
# (mirror synced from CMDB) instead of calling the CC API, so SOPS works
# without a CMDB deployment. Keep the return shape identical to
# client.cc.search_business so downstream sync logic is untouched.
def _local_business_as_cc_format(business):
    return {
        "bk_biz_id": business.cc_id,
        "bk_biz_name": business.cc_name,
        "bk_supplier_account": business.cc_owner or "0",
        "bk_supplier_id": business.cc_company or "0",
        "time_zone": business.time_zone or "",
        "life_cycle": business.life_cycle or "",
        "bk_data_status": business.status or "enable",
    }


def get_all_business_list(use_cache=True):
    from gcloud.core.models import Business

    return [_local_business_as_cc_format(b) for b in Business.objects.all()]


def get_user_business_list(username, use_cache=True):
    """Get business list for a exact username, served from the local mirror table."""
    from gcloud.core.models import Business

    return [_local_business_as_cc_format(b) for b in Business.objects.all()]


def get_user_business_detail(username, bk_biz_id):
    """Get one business detail, served from the local mirror table."""
    from gcloud.core.models import Business

    try:
        business = Business.objects.get(cc_id=bk_biz_id)
    except Business.DoesNotExist:
        raise exceptions.APIError(system="cc", api="search_business", message="business not found")
    return _local_business_as_cc_format(business)


def _get_user_info(username, use_cache=True):
    """
    获取用户基本信息
    @param username:
    @param use_cache:
    @return:
    """
    cache_key = "%s_get_user_info_%s" % (CACHE_PREFIX, username)
    data = cache.get(cache_key)
    if not (use_cache and data):
        userinfo = get_user_info(username)
        userinfo.setdefault("code", -1)
        if userinfo["result"]:
            data = userinfo["data"]
            if data:
                cache.set(cache_key, data, DEFAULT_CACHE_TIME_FOR_CC)
        else:
            raise exceptions.APIError("bk_api", "get_user_info", userinfo.get("detail_message", userinfo["message"]))
    return data


def convert_readable_username(username):
    """将用户名转换成昵称"""
    return username


def convert_group_name(biz_cc_id, role):
    return "%s\x00%s" % (biz_cc_id, role)
