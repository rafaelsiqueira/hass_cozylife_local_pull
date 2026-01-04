"""Example Load Platform integration."""
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType
import logging
import asyncio
from .const import (
    DOMAIN,
    LANG
)
from .utils import get_pid_list
from .udp_discover import get_ip
from .tcp_client import tcp_client


_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Async setup with proper device initialization"""

    # Discovery
    ip = await get_ip()
    ip_from_config = config[DOMAIN].get('ip') if config[DOMAIN].get('ip') is not None else []
    ip += ip_from_config
    ip_list = []
    [ip_list.append(i) for i in ip if i not in ip_list]

    if len(ip_list) == 0:
        _LOGGER.info('No devices discovered')
        return True

    _LOGGER.info(f'Discovered devices at: {ip_list}')

    # Get language setting
    lang_from_config = config[DOMAIN].get('lang') if config[DOMAIN].get('lang') is not None else LANG
    get_pid_list(lang_from_config)

    # Create TCP clients for all devices
    tcp_clients = [tcp_client(ip_addr) for ip_addr in ip_list]

    # Wait for connections with timeout
    max_wait_time = 10  # seconds
    poll_interval = 0.5  # seconds
    elapsed = 0

    _LOGGER.info('Waiting for devices to connect...')

    while elapsed < max_wait_time:
        connected_count = sum(1 for client in tcp_clients if client.is_connected)

        if connected_count == len(tcp_clients):
            _LOGGER.info(f'All {len(tcp_clients)} devices connected')
            break

        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        if elapsed % 2 == 0:  # Log every 2 seconds
            _LOGGER.info(f'Connected {connected_count}/{len(tcp_clients)} devices...')

    # Identify working and failed devices
    working_clients = []
    failed_ips = []

    for client in tcp_clients:
        if client.is_connected and client.device_id:
            working_clients.append(client)
            _LOGGER.info(f'Device ready: {client._ip} ({client.device_model_name})')
        else:
            failed_ips.append(client._ip)
            _LOGGER.warning(f'Device failed to initialize: {client._ip}')

    # Report results
    if len(failed_ips) > 0:
        _LOGGER.warning(f'Failed to connect to {len(failed_ips)} device(s): {failed_ips}')

    if len(working_clients) == 0:
        _LOGGER.error('No devices successfully connected')
        return True  # Return True to allow retry later

    _LOGGER.info(f'Successfully connected to {len(working_clients)}/{len(tcp_clients)} devices')

    # Store working clients
    hass.data[DOMAIN] = {
        'temperature': 24,
        'ip': [client._ip for client in working_clients],
        'tcp_client': working_clients,
        'failed_ips': failed_ips,
    }

    # Load platforms with working devices
    await async_load_platform(hass, 'light', DOMAIN, {}, config)
    await async_load_platform(hass, 'switch', DOMAIN, {}, config)

    return True


def setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Synchronous setup wrapper"""
    return hass.loop.run_until_complete(async_setup(hass, config))
