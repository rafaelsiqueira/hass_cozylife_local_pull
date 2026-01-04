# -*- coding: utf-8 -*-
import json
import time
import logging
import aiohttp
from .const import (
    API_DOMAIN,
    LANG
)
_LOGGER = logging.getLogger(__name__)


def get_sn() -> str:
    """
    message sn
    :return: str
    """
    return str(int(round(time.time() * 1000)))


# cache get_pid_list result for many calls
_CACHE_PID = []


def get_pid_list_cached() -> list:
    """
    Get cached PID list (synchronous, for use in threads)
    :return: Cached list of device models, or empty list if not cached
    """
    global _CACHE_PID
    return _CACHE_PID


async def get_pid_list(session: aiohttp.ClientSession, lang='en') -> list:
    """
    Fetch device product models from API (async)
    http://doc.doit/project-12/doc-95/
    :param session: aiohttp ClientSession
    :param lang: Language code
    :return: List of device models
    """
    global _CACHE_PID
    if len(_CACHE_PID) != 0:
        return _CACHE_PID

    if lang not in ['zh', 'en', 'es', 'pt', 'ja', 'ru', 'pt', 'nl', 'ko', 'fr', 'de',]:
        _LOGGER.info(f'not support lang={lang}, will set lang={LANG}')
        lang = LANG

    try:
        async with session.get(
            f'http://{API_DOMAIN}/api/v2/device_product/model',
            params={'lang': lang},
            timeout=aiohttp.ClientTimeout(total=3)
        ) as response:
            if response.status != 200:
                _LOGGER.warning(f'get_pid_list failed with status {response.status}')
                return []

            try:
                pid_list = await response.json()
            except json.JSONDecodeError:
                _LOGGER.error('get_pid_list.result is not json')
                return []

    except aiohttp.ClientError as e:
        _LOGGER.error(f'HTTP error fetching pid list: {e}')
        return []
    except Exception as e:
        _LOGGER.error(f'Error fetching pid list: {e}')
        return []

    if pid_list.get('ret') is None:
        return []

    if '1' != pid_list['ret']:
        return []

    if pid_list.get('info') is None or type(pid_list.get('info')) is not dict:
        return []

    if pid_list['info'].get('list') is None or type(pid_list['info']['list']) is not list:
        return []

    _CACHE_PID = pid_list['info']['list']
    return _CACHE_PID
