# -*- coding: utf-8 -*-
import json
import socket
import time
from typing import Optional, Union, Any, Dict
import logging
from .utils import get_pid_list, get_sn
import threading
from enum import Enum
from dataclasses import dataclass
import random

CMD_INFO = 0
CMD_QUERY = 2
CMD_SET = 3
CMD_LIST = [CMD_INFO, CMD_QUERY, CMD_SET]
_LOGGER = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Connection state enum for tracking device connection status"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


class ErrorType(Enum):
    """Error type classification for structured error handling"""
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    PROTOCOL_ERROR = "protocol_error"
    DEVICE_ERROR = "device_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass
class QueryResult:
    """Structured result for query operations"""
    success: bool
    data: Dict[str, Any]
    error_type: Optional[ErrorType] = None
    error_message: Optional[str] = None
    should_retry: bool = False


# Timeout configuration
TIMEOUT_CONNECTION = 5  # seconds
TIMEOUT_QUERY = 3       # seconds
TIMEOUT_SEND = 3        # seconds

# Retry configuration
RETRY_MAX_ATTEMPTS = 3
RETRY_BASE_DELAY = 0.5  # seconds
RETRY_MAX_DELAY = 5.0   # seconds
RETRY_EXPONENTIAL_BASE = 2


class tcp_client(object):
    """
    Represents a device
    send:{"cmd":0,"pv":0,"sn":"1636463553873","msg":{}}
    receiver:{"cmd":0,"pv":0,"sn":"1636463553873","msg":{"did":"629168597cb94c4c1d8f","dtp":"02","pid":"e2s64v",
    "mac":"7cb94c4c1d8f","ip":"192.168.123.57","rssi":-33,"sv":"1.0.0","hv":"0.0.1"},"res":0}

    send:{"cmd":2,"pv":0,"sn":"1636463611798","msg":{"attr":[0]}}
    receiver:{"cmd":2,"pv":0,"sn":"1636463611798","msg":{"attr":[1,2,3,4,5,6],"data":{"1":0,"2":0,"3":1000,"4":1000,
    "5":65535,"6":65535}},"res":0}
    
    send:{"cmd":3,"pv":0,"sn":"1636463662455","msg":{"attr":[1],"data":{"1":0}}}
    receiver:{"cmd":3,"pv":0,"sn":"1636463662455","msg":{"attr":[1],"data":{"1":0}},"res":0}
    receiver:{"cmd":10,"pv":0,"sn":"1636463664000","res":0,"msg":{"attr":[1,2,3,4,5,6],"data":{"1":0,"2":0,"3":1000,
    "4":1000,"5":65535,"6":65535}}}
    """
    _ip = str
    _port = 5555
    _connect = socket
    
    _device_id = str
    # _device_key = str
    _pid = str
    _device_type_code = str
    _icon = str
    _device_model_name = str
    _dpid = []
    # last sn
    _sn = str
    
    def __init__(self, ip):
        self._ip = ip
        self._connect = None  # Initialize _connect as None
        self._connection_state = ConnectionState.DISCONNECTED
        self._connection_lock = threading.RLock()  # Reentrant lock for thread safety
        self._last_successful_query = None
        self._consecutive_failures = 0

        # Retry configuration (can be overridden)
        self._retry_max_attempts = RETRY_MAX_ATTEMPTS
        self._retry_base_delay = RETRY_BASE_DELAY

        self._close_connection()
        self._reconnect()
    
    def _close_connection(self):
        if self._connect:
            try:
                self._connect.close()
            except Exception as e:
                _LOGGER.error(f'Error while closing the connection: {e}')
            self._connect = None

    @property
    def is_connected(self) -> bool:
        """Thread-safe check if device is connected"""
        with self._connection_lock:
            return (self._connection_state == ConnectionState.CONNECTED
                    and self._connect is not None)

    @property
    def connection_state(self) -> ConnectionState:
        """Get current connection state"""
        with self._connection_lock:
            return self._connection_state

    def _set_connection_state(self, state: ConnectionState) -> None:
        """Thread-safe connection state setter"""
        with self._connection_lock:
            old_state = self._connection_state
            self._connection_state = state
            if old_state != state:
                _LOGGER.info(f'Device {self._ip} connection state: {old_state.value} -> {state.value}')

    def _reconnect(self):
        def reconnect_thread():
            while True:
                self._set_connection_state(ConnectionState.CONNECTING)
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(TIMEOUT_CONNECTION)
                    s.connect((self._ip, self._port))

                    with self._connection_lock:
                        self._connect = s

                    # Get device info to validate connection
                    self._device_info()

                    # Only mark as connected if device info succeeded
                    if self._device_id:
                        self._set_connection_state(ConnectionState.CONNECTED)
                        self._consecutive_failures = 0
                        _LOGGER.info(f'Successfully connected to {self._ip}')
                        return
                    else:
                        raise Exception("Device info retrieval failed")

                except socket.timeout as e:
                    _LOGGER.warning(f'Connection timeout for {self._ip}: {e}')
                    self._set_connection_state(ConnectionState.DISCONNECTED)
                except socket.error as e:
                    _LOGGER.warning(f'Socket error connecting to {self._ip}: {e}')
                    self._set_connection_state(ConnectionState.DISCONNECTED)
                except Exception as e:
                    _LOGGER.error(f'Reconnection failed for {self._ip}: {e}')
                    self._set_connection_state(ConnectionState.DISCONNECTED)

                time.sleep(60)  # Wait for 60 seconds before trying to reconnect

        thread = threading.Thread(target=reconnect_thread, name=f'reconnect_{self._ip}')
        thread.daemon = True  # This makes the thread exit when the main program exits
        thread.start()


    @property
    def check(self) -> bool:
        """
        Determine whether the device is filtered
        :return:
        """
        return True
    
    @property
    def dpid(self):
        return self._dpid
    
    @property
    def device_model_name(self):
        return self._device_model_name
    
    @property
    def icon(self):
        return self._icon
    
    @property
    def device_type_code(self) -> str:
        return self._device_type_code
    
    @property
    def device_id(self):
        return self._device_id
    
    def _device_info(self) -> None:
        """Get device model information"""
        if not self.is_connected:
            _LOGGER.warning(f'Cannot get device info - not connected to {self._ip}')
            return None

        try:
            self._only_send(CMD_INFO, {})
        except Exception as e:
            _LOGGER.error(f'Failed to send device info request to {self._ip}: {e}')
            return None

        try:
            with self._connection_lock:
                if self._connect is None:
                    _LOGGER.warning(f'Connection lost during device info for {self._ip}')
                    return None
                self._connect.settimeout(TIMEOUT_QUERY)
                resp = self._connect.recv(1024)

            resp_json = json.loads(resp.strip())
        except socket.timeout:
            _LOGGER.warning(f'Timeout receiving device info from {self._ip}')
            return None
        except json.JSONDecodeError as e:
            _LOGGER.error(f'Invalid JSON in device info response from {self._ip}: {e}')
            return None
        except Exception as e:
            _LOGGER.error(f'Error receiving device info from {self._ip}: {e}')
            return None

        # Validate response structure
        if not isinstance(resp_json.get('msg'), dict):
            _LOGGER.warning(f'Invalid device info response structure from {self._ip}')
            return None

        msg = resp_json['msg']

        # Extract device ID
        if msg.get('did') is None:
            _LOGGER.warning(f'No device ID in response from {self._ip}')
            return None
        self._device_id = msg['did']

        # Extract PID and look up device model
        if msg.get('pid') is None:
            _LOGGER.warning(f'No PID in response from {self._ip}')
            return None

        self._pid = msg['pid']
        pid_list = get_pid_list()

        # Match PID to device model
        for item in pid_list:
            match = False
            for item1 in item['m']:
                if item1['pid'] == self._pid:
                    match = True
                    self._icon = item1['i']
                    self._device_model_name = item1['n']
                    self._dpid = item1['dpid']
                    break

            if match:
                self._device_type_code = item['c']
                break

        _LOGGER.info(f'Device info: id={self._device_id}, type={self._device_type_code}, '
                     f'pid={self._pid}, model={self._device_model_name}')

    def _calculate_retry_delay(self, attempt: int) -> float:
        """Calculate exponential backoff delay with jitter"""
        delay = min(
            self._retry_base_delay * (RETRY_EXPONENTIAL_BASE ** attempt),
            RETRY_MAX_DELAY
        )
        # Add jitter (±25%)
        jitter = delay * 0.25 * (2 * random.random() - 1)
        return max(0, delay + jitter)

    def _should_retry_error(self, error_type: ErrorType) -> bool:
        """Determine if error type should trigger retry"""
        # Retry transient errors, not protocol or device errors
        return error_type in {
            ErrorType.NETWORK_ERROR,
            ErrorType.TIMEOUT_ERROR,
            ErrorType.UNKNOWN_ERROR
        }

    def _get_package(self, cmd: int, payload: dict) -> bytes:
        """
        package message
        :param cmd:int:
        :param payload:
        :return:
        """
        self._sn = get_sn()
        if CMD_SET == cmd:
            message = {
                'pv': 0,
                'cmd': cmd,
                'sn': self._sn,
                'msg': {
                    'attr': [int(item) for item in payload.keys()],
                    'data': payload,
                }
            }
        elif CMD_QUERY == cmd:
            message = {
                'pv': 0,
                'cmd': cmd,
                'sn': self._sn,
                'msg': {
                    'attr': [0],
                }
            }
        elif CMD_INFO == cmd:
            message = {
                'pv': 0,
                'cmd': cmd,
                'sn': self._sn,
                'msg': {}
            }
        else:
            raise Exception('CMD is not valid')
        
        payload_str = json.dumps(message, separators=(',', ':',))
        _LOGGER.info(f'_package={payload_str}')
        return bytes(payload_str + "\r\n", encoding='utf8')
    
    def _send_receiver(self, cmd: int, payload: dict) -> QueryResult:
        """
        Send command and receive response
        Returns QueryResult with structured error information
        """
        # Validate connection
        if not self.is_connected:
            return QueryResult(
                success=False,
                data={},
                error_type=ErrorType.NETWORK_ERROR,
                error_message=f'Not connected to {self._ip}',
                should_retry=True
            )

        # Send command
        try:
            package = self._get_package(cmd, payload)
            with self._connection_lock:
                if self._connect is None:
                    return QueryResult(
                        success=False,
                        data={},
                        error_type=ErrorType.NETWORK_ERROR,
                        error_message='Connection lost before send',
                        should_retry=True
                    )
                self._connect.settimeout(TIMEOUT_SEND)
                self._connect.send(package)
        except socket.timeout:
            _LOGGER.warning(f'Timeout sending to {self._ip}')
            return QueryResult(
                success=False,
                data={},
                error_type=ErrorType.TIMEOUT_ERROR,
                error_message='Send timeout',
                should_retry=True
            )
        except socket.error as e:
            _LOGGER.error(f'Socket error sending to {self._ip}: {e}')
            self._reconnect()
            return QueryResult(
                success=False,
                data={},
                error_type=ErrorType.NETWORK_ERROR,
                error_message=f'Socket error: {e}',
                should_retry=True
            )
        except Exception as e:
            _LOGGER.error(f'Unexpected error sending to {self._ip}: {e}')
            return QueryResult(
                success=False,
                data={},
                error_type=ErrorType.UNKNOWN_ERROR,
                error_message=f'Send error: {e}',
                should_retry=True
            )

        # Receive response
        try:
            i = 10
            while i > 0:
                with self._connection_lock:
                    if self._connect is None:
                        return QueryResult(
                            success=False,
                            data={},
                            error_type=ErrorType.NETWORK_ERROR,
                            error_message='Connection lost during recv',
                            should_retry=True
                        )
                    self._connect.settimeout(TIMEOUT_QUERY)
                    res = self._connect.recv(1024)

                i -= 1

                # Only process responses matching our sequence number
                if self._sn in str(res):
                    try:
                        payload_data = json.loads(res.strip())
                    except json.JSONDecodeError as e:
                        _LOGGER.error(f'Invalid JSON from {self._ip}: {e}')
                        return QueryResult(
                            success=False,
                            data={},
                            error_type=ErrorType.PROTOCOL_ERROR,
                            error_message='Invalid JSON response',
                            should_retry=False
                        )

                    # Validate response structure
                    if not isinstance(payload_data, dict) or not payload_data:
                        return QueryResult(
                            success=False,
                            data={},
                            error_type=ErrorType.PROTOCOL_ERROR,
                            error_message='Empty or invalid response',
                            should_retry=False
                        )

                    if not isinstance(payload_data.get('msg'), dict):
                        return QueryResult(
                            success=False,
                            data={},
                            error_type=ErrorType.PROTOCOL_ERROR,
                            error_message='Invalid message structure',
                            should_retry=False
                        )

                    if not isinstance(payload_data['msg'].get('data'), dict):
                        return QueryResult(
                            success=False,
                            data={},
                            error_type=ErrorType.PROTOCOL_ERROR,
                            error_message='Invalid data structure',
                            should_retry=False
                        )

                    # Success
                    self._last_successful_query = time.time()
                    self._consecutive_failures = 0
                    return QueryResult(
                        success=True,
                        data=payload_data['msg']['data'],
                        error_type=None,
                        error_message=None,
                        should_retry=False
                    )

            # No matching response received
            return QueryResult(
                success=False,
                data={},
                error_type=ErrorType.TIMEOUT_ERROR,
                error_message='No matching response received',
                should_retry=True
            )

        except socket.timeout:
            _LOGGER.warning(f'Timeout receiving from {self._ip}')
            return QueryResult(
                success=False,
                data={},
                error_type=ErrorType.TIMEOUT_ERROR,
                error_message='Receive timeout',
                should_retry=True
            )
        except socket.error as e:
            _LOGGER.error(f'Socket error receiving from {self._ip}: {e}')
            self._reconnect()
            return QueryResult(
                success=False,
                data={},
                error_type=ErrorType.NETWORK_ERROR,
                error_message=f'Socket error: {e}',
                should_retry=True
            )
        except Exception as e:
            _LOGGER.error(f'Unexpected error receiving from {self._ip}: {e}')
            return QueryResult(
                success=False,
                data={},
                error_type=ErrorType.UNKNOWN_ERROR,
                error_message=f'Receive error: {e}',
                should_retry=True
            )
    
    def _only_send(self, cmd: int, payload: dict) -> bool:
        """
        Send command without waiting for response
        Returns True on success, False on failure
        """
        if not self.is_connected:
            _LOGGER.warning(f'Cannot send - not connected to {self._ip}')
            return False

        try:
            package = self._get_package(cmd, payload)
            with self._connection_lock:
                if self._connect is None:
                    _LOGGER.warning(f'Connection lost before send to {self._ip}')
                    return False
                self._connect.settimeout(TIMEOUT_SEND)
                self._connect.send(package)
            return True
        except socket.timeout:
            _LOGGER.warning(f'Timeout sending to {self._ip}')
            return False
        except socket.error as e:
            _LOGGER.error(f'Socket error sending to {self._ip}: {e}')
            self._reconnect()
            return False
        except Exception as e:
            _LOGGER.error(f'Unexpected error sending to {self._ip}: {e}')
            return False
    
    def control(self, payload: dict) -> bool:
        """
        Control device using dpid
        Returns True on success, False on failure
        """
        success = self._only_send(CMD_SET, payload)
        if not success:
            _LOGGER.warning(f'Failed to send control command to {self._ip}')
            self._consecutive_failures += 1
        return success

    def query(self) -> QueryResult:
        """
        Query device state with retry logic
        Returns QueryResult with success/failure and data
        """
        last_result = None

        for attempt in range(self._retry_max_attempts):
            result = self._send_receiver(CMD_QUERY, {})
            last_result = result

            if result.success:
                return result

            # Don't retry if error type is not retryable
            if not result.should_retry or not self._should_retry_error(result.error_type):
                _LOGGER.warning(f'Non-retryable error querying {self._ip}: {result.error_message}')
                self._consecutive_failures += 1
                return result

            # Don't sleep after last attempt
            if attempt < self._retry_max_attempts - 1:
                delay = self._calculate_retry_delay(attempt)
                _LOGGER.info(f'Query failed (attempt {attempt + 1}/{self._retry_max_attempts}), '
                            f'retrying in {delay:.2f}s: {result.error_message}')
                time.sleep(delay)

        # All retries exhausted
        self._consecutive_failures += 1
        _LOGGER.error(f'Query failed after {self._retry_max_attempts} attempts for {self._ip}')
        return last_result