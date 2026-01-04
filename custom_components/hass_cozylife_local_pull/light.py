"""Platform for sensor integration."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.switch import SwitchEntity
from homeassistant.components.light import LightEntity
# from homeassistant.components.light import *
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_EFFECT,
    ATTR_FLASH,
    ATTR_HS_COLOR,
    ATTR_KELVIN,
    ATTR_RGB_COLOR,
    ATTR_TRANSITION,
    COLOR_MODE_BRIGHTNESS,
    COLOR_MODE_COLOR_TEMP,
    COLOR_MODE_HS,
    COLOR_MODE_ONOFF,
    COLOR_MODE_RGB,
    COLOR_MODE_UNKNOWN,
    FLASH_LONG,
    FLASH_SHORT,
    SUPPORT_EFFECT,
    SUPPORT_FLASH,
    SUPPORT_TRANSITION,
    LightEntity,
)
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
from .tcp_client import tcp_client
import logging
from homeassistant.components import zeroconf

_LOGGER = logging.getLogger(__name__)
_LOGGER.info(__name__)

def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    """Set up the sensor platform."""
    # We only want this platform to be set up via discovery.
    _LOGGER.info(
        f'setup_platform.hass={hass},config={config},add_entities={add_entities},discovery_info={discovery_info}')
    # zc = await zeroconf.async_get_instance(hass)
    # _LOGGER.info(f'zc={zc}')
    _LOGGER.info(f'hass.data={hass.data[DOMAIN]}')
    _LOGGER.info(f'discovery_info={discovery_info}')

    if discovery_info is None:
        return
    
    lights = []
    for item in hass.data[DOMAIN]['tcp_client']:
        if LIGHT_TYPE_CODE == item.device_type_code:
            lights.append(CozyLifeLight(item, hass))

    add_entities(lights)


class CozyLifeLight(LightEntity):
    # _attr_brightness: int | None = None
    # _attr_color_mode: str | None = None
    # _attr_color_temp: int | None = None
    # _attr_hs_color = None
    _tcp_client = None

    _attr_supported_color_modes = {COLOR_MODE_BRIGHTNESS, COLOR_MODE_ONOFF}
    _attr_color_mode = COLOR_MODE_BRIGHTNESS
    _attr_should_poll = True  # Enable polling for this entity

    # _unique_id = str
    # _attr_is_on = True
    # _name = str
    # _attr_brightness = int
    # _attr_color_temp = int
    # _attr_hs_color = (float, float)

    def __init__(self, tcp_client: tcp_client, hass) -> None:
        """Initialize the sensor."""
        _LOGGER.info('__init__')
        self._tcp_client = tcp_client
        self._hass = hass
        self._unique_id = tcp_client.device_id
        self._name = tcp_client.device_model_name + ' ' + tcp_client.device_id[-4:]
        self._attr_available = False  # Start as unavailable
        self._attr_is_on = False
        self._attr_brightness = None
        self._attr_color_temp = None
        self._attr_hs_color = None

        _LOGGER.info(f'before:{self._unique_id}._attr_color_mode={self._attr_color_mode}.'
                     f'_attr_supported_color_modes={self._attr_supported_color_modes}.dpid={tcp_client.dpid}')

        # Configure color modes based on device capabilities
        if 3 in tcp_client.dpid:
            self._attr_color_mode = COLOR_MODE_COLOR_TEMP
            self._attr_supported_color_modes.add(COLOR_MODE_COLOR_TEMP)

        if 5 in tcp_client.dpid or 6 in tcp_client.dpid:
            self._attr_color_mode = COLOR_MODE_HS
            self._attr_supported_color_modes.add(COLOR_MODE_HS)

        _LOGGER.info(f'after:{self._unique_id}._attr_color_mode={self._attr_color_mode}.'
                     f'_attr_supported_color_modes={self._attr_supported_color_modes}.dpid={tcp_client.dpid}')

        # Don't query immediately - wait for first update() call

    async def async_update(self):
        """Fetch new state data for this light (called by HA periodically)"""
        # Run blocking query() in executor to avoid blocking event loop
        result = await self._hass.async_add_executor_job(self._tcp_client.query)

        if result.success:
            self._attr_available = True
            data = result.data

            _LOGGER.debug(f'Light {self._name} state data={data}')

            # Safe access to all state values
            self._attr_is_on = data.get('1', 0) > 0

            if '4' in data:
                self._attr_brightness = int(data['4'] / 4)

            if '5' in data and '6' in data:
                self._attr_hs_color = (int(data['5']), int(data['6'] / 10))

            if '3' in data:
                self._attr_color_temp = 500 - int(data['3'] / 2)

            _LOGGER.debug(f'Light {self._name} refreshed: is_on={self._attr_is_on}, '
                         f'brightness={self._attr_brightness}, color_temp={self._attr_color_temp}')
        else:
            # Mark as unavailable on error
            self._attr_available = False
            _LOGGER.warning(f'Light {self._name} unavailable: {result.error_message}')
            # Keep last known state values
    
    @property
    def name(self) -> str:
        return self._name
    
    @property
    def available(self) -> bool:
        """Return if the device is available."""
        return self._attr_available

    @property
    def is_on(self) -> bool:
        """Return True if entity is on (cached value from async_update)."""
        return self._attr_is_on
    
    @property
    def color_temp(self) -> int | None:
        """Return the CT color value in mireds."""
        return self._attr_color_temp
    
    @property
    def unique_id(self) -> str | None:
        """Return a unique ID."""
        return self._unique_id

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the entity on."""
        if not self._attr_available:
            _LOGGER.warning(f'Cannot turn on {self._name} - device unavailable')
            return

        brightness = kwargs.get(ATTR_BRIGHTNESS)
        colortemp = kwargs.get(ATTR_COLOR_TEMP)
        hs_color = kwargs.get(ATTR_HS_COLOR)
        rgb = kwargs.get(ATTR_RGB_COLOR)
        flash = kwargs.get(ATTR_FLASH)
        effect = kwargs.get(ATTR_EFFECT)

        _LOGGER.info(f'turn_on.kwargs={kwargs}')

        payload = {'1': 255, '2': 0}

        if brightness is not None:
            payload['4'] = brightness * 4
            self._attr_brightness = brightness

        if hs_color is not None:
            payload['5'] = int(hs_color[0])
            payload['6'] = int(hs_color[1] * 10)
            self._attr_hs_color = hs_color

        if colortemp is not None:
            payload['3'] = 1000 - colortemp * 2

        # Run blocking control() in executor to avoid blocking event loop
        success = await self._hass.async_add_executor_job(
            self._tcp_client.control, payload
        )
        if success:
            self._attr_is_on = True
            # State will be verified on next async_update() call
        else:
            _LOGGER.error(f'Failed to turn on {self._name}')
            self._attr_available = False

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the entity off."""
        if not self._attr_available:
            _LOGGER.warning(f'Cannot turn off {self._name} - device unavailable')
            return

        _LOGGER.info(f'turn_off.kwargs={kwargs}')

        # Run blocking control() in executor to avoid blocking event loop
        success = await self._hass.async_add_executor_job(
            self._tcp_client.control, {'1': 0}
        )
        if success:
            self._attr_is_on = False
            # State will be verified on next async_update() call
        else:
            _LOGGER.error(f'Failed to turn off {self._name}')
            self._attr_available = False
    
    @property
    def hs_color(self) -> tuple[float, float] | None:
        """Return the hue and saturation color value [float, float] (cached value)."""
        return self._attr_hs_color

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255 (cached value)."""
        return self._attr_brightness
    
    @property
    def color_mode(self) -> str | None:
        """Return the color mode of the light."""
        _LOGGER.info('color_mode')
        return self._attr_color_mode
    
    # def set_brightness(self, b):
    #     _LOGGER.info('set_brightness')
    #
    #     self._attr_brightness = b
    #
    # def set_hs(self, hs_color, duration) -> None:
    #     """Set bulb's color."""
    #     _LOGGER.info('set_hs')
    #     self._attr_hs_color = (hs_color[0], hs_color[1])
