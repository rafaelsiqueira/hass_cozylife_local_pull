"""Platform for sensor integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from typing import Any, Final, Literal, TypedDict, final
from .const import (
    DOMAIN,
    SWITCH_TYPE_CODE,
    LIGHT_TYPE_CODE,
    LIGHT_DPID,
    SWITCH,
    WORK_MODE,
    TEMP,
    BRIGHT,
    HUE,
    SAT,
)
import logging

_LOGGER = logging.getLogger(__name__)
_LOGGER.info('switch')


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the sensor platform."""
    # We only want this platform to be set up via discovery.
    # logging.info('setup_platform', hass, config, add_entities, discovery_info)
    _LOGGER.info('setup_platform')
    _LOGGER.info(f'ip={hass.data[DOMAIN]}')
    
    if discovery_info is None:
        return


    switchs = []
    for item in hass.data[DOMAIN]['tcp_client']:
        if SWITCH_TYPE_CODE == item.device_type_code:
            switchs.append(CozyLifeSwitch(item))
    
    add_entities(switchs)


class CozyLifeSwitch(SwitchEntity):
    _tcp_client = None
    _attr_available = False
    _attr_is_on = False

    def __init__(self, tcp_client) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self._tcp_client = tcp_client
        self._unique_id = tcp_client.device_id
        self._name = tcp_client.device_model_name + ' ' + tcp_client.device_id[-4:]
        self._attr_available = False  # Start as unavailable
        self._attr_is_on = False
        self._refresh_state()

    def _refresh_state(self):
        """Refresh device state from query"""
        result = self._tcp_client.query()

        if result.success:
            self._attr_available = True
            # Safe access with default value
            self._attr_is_on = result.data.get('1', 0) != 0
            _LOGGER.debug(f'Switch {self._name} state refreshed: is_on={self._attr_is_on}')
        else:
            # Mark as unavailable on error
            self._attr_available = False
            _LOGGER.warning(f'Switch {self._name} unavailable: {result.error_message}')
            # Keep last known state for is_on
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def available(self) -> bool:
        """Return if the device is available."""
        return self._attr_available

    @property
    def is_on(self) -> bool:
        """Return True if entity is on."""
        if self._attr_available:
            self._refresh_state()
        return self._attr_is_on
    
    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id
    
    def turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        _LOGGER.info(f'turn_on:{kwargs}')

        if not self._attr_available:
            _LOGGER.warning(f'Cannot turn on {self._name} - device unavailable')
            return

        success = self._tcp_client.control({'1': 255})
        if success:
            self._attr_is_on = True
            self._refresh_state()  # Verify state change
        else:
            _LOGGER.error(f'Failed to turn on {self._name}')
            self._attr_available = False

    def turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        _LOGGER.info('turn_off')

        if not self._attr_available:
            _LOGGER.warning(f'Cannot turn off {self._name} - device unavailable')
            return

        success = self._tcp_client.control({'1': 0})
        if success:
            self._attr_is_on = False
            self._refresh_state()  # Verify state change
        else:
            _LOGGER.error(f'Failed to turn off {self._name}')
            self._attr_available = False
