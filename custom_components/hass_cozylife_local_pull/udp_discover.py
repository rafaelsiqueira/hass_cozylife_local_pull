import socket
import time
from .utils import get_sn
import logging


_LOGGER = logging.getLogger(__name__)

"""
discover device
"""

# Discovery configuration
DISCOVERY_TIMEOUT = 0.1  # seconds
DISCOVERY_BROADCAST_REPEATS = 3
DISCOVERY_MAX_RETRIES = 5
DISCOVERY_MAX_RESPONSES = 255


def get_ip() -> list:
    """
    Discover devices via UDP broadcast
    Returns list of device IP addresses
    """
    server = None
    try:
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        server.settimeout(DISCOVERY_TIMEOUT)
        socket.setdefaulttimeout(DISCOVERY_TIMEOUT)

        message = '{"cmd":0,"pv":0,"sn":"' + get_sn() + '","msg":{}}'

        # Send broadcast messages
        i = 0
        while i < DISCOVERY_BROADCAST_REPEATS:
            try:
                server.sendto(bytes(message, encoding='utf-8'), ('255.255.255.255', 6095))
            except socket.error as e:
                _LOGGER.error(f'Failed to send UDP broadcast: {e}')
                return []
            time.sleep(0.03)
            i += 1

        # Wait for first response
        max_retries = DISCOVERY_MAX_RETRIES
        i = 0
        first_response = False

        while i < max_retries:
            i += 1
            try:
                data, addr = server.recvfrom(1024, socket.MSG_PEEK)
                _LOGGER.info(f'First UDP response from: {addr[0]}')
                first_response = True
                break
            except socket.timeout:
                _LOGGER.debug(f'{i}/{max_retries} discovery attempt, no response yet')
            except socket.error as e:
                _LOGGER.error(f'Socket error during discovery: {e}')
                break

        if not first_response:
            _LOGGER.warning('No devices responded to UDP discovery')
            return []

        # Collect all responses
        ip = []
        i = DISCOVERY_MAX_RESPONSES

        while i > 0:
            try:
                data, addr = server.recvfrom(1024)
                _LOGGER.info(f'UDP discovery response from: {addr[0]}')
                if addr[0] not in ip:
                    ip.append(addr[0])
                i -= 1
            except socket.timeout:
                _LOGGER.debug('UDP discovery timeout - no more responses')
                break
            except socket.error as e:
                _LOGGER.error(f'Socket error receiving UDP response: {e}')
                break
            except Exception as e:
                _LOGGER.error(f'Unexpected error during UDP discovery: {e}')
                break

        _LOGGER.info(f'Discovered {len(ip)} device(s): {ip}')
        return ip

    except Exception as e:
        _LOGGER.error(f'Error during device discovery: {e}')
        return []
    finally:
        if server:
            try:
                server.close()
            except Exception as e:
                _LOGGER.error(f'Error closing discovery socket: {e}')
