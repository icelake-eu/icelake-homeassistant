"""Config flow for Icelake integration."""

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_API_KEY,
    CONF_CLIENT_ID,
    CONF_ENDPOINT,
    CONF_EXCLUDE_DOMAINS,
    CONF_EXCLUDE_ENTITIES,
    CONF_INCLUDE_DOMAINS,
    CONF_INCLUDE_ENTITIES,
    CONF_SEND_INTERVAL,
    CONF_SOURCE_ID,
    DEFAULT_SEND_INTERVAL,
    DEFAULT_SOURCE_ID,
    DOMAIN,
)
from .sender import IcelakeSender

ALL_DOMAINS = [
    "air_quality", "alarm_control_panel", "automation", "binary_sensor",
    "button", "calendar", "camera", "climate", "cover", "device_tracker",
    "fan", "humidifier", "input_boolean", "input_number", "input_select",
    "light", "lock", "media_player", "number", "person", "plant",
    "remote", "scene", "script", "select", "sensor", "siren",
    "sun", "switch", "timer", "update", "vacuum", "water_heater",
    "weather", "zone",
]


class IcelakeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Icelake."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            sender = IcelakeSender(
                endpoint=user_input[CONF_ENDPOINT],
                client_id=user_input[CONF_CLIENT_ID],
                api_key=user_input[CONF_API_KEY],
                source_id=user_input.get(CONF_SOURCE_ID, DEFAULT_SOURCE_ID),
                send_interval=user_input.get(CONF_SEND_INTERVAL, DEFAULT_SEND_INTERVAL),
            )
            success, error_key = await sender.test_connection()
            if success:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Icelake",
                    data=user_input,
                )
            errors["base"] = error_key

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ENDPOINT, default="https://api.icelake.eu"
                    ): str,
                    vol.Required(CONF_CLIENT_ID): str,
                    vol.Required(CONF_API_KEY): str,
                    vol.Optional(
                        CONF_SOURCE_ID, default=DEFAULT_SOURCE_ID
                    ): str,
                    vol.Optional(
                        CONF_SEND_INTERVAL, default=DEFAULT_SEND_INTERVAL
                    ): vol.All(int, vol.Range(min=5, max=300)),
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IcelakeOptionsFlow(config_entry)


class IcelakeOptionsFlow(OptionsFlow):
    """Handle options for Icelake."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._config_entry.options
        domain_selector = SelectSelector(
            SelectSelectorConfig(
                options=ALL_DOMAINS,
                multiple=True,
                mode=SelectSelectorMode.DROPDOWN,
            )
        )
        entity_selector = EntitySelector(EntitySelectorConfig(multiple=True))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_INCLUDE_DOMAINS,
                        default=options.get(CONF_INCLUDE_DOMAINS, []),
                    ): domain_selector,
                    vol.Optional(
                        CONF_EXCLUDE_DOMAINS,
                        default=options.get(CONF_EXCLUDE_DOMAINS, []),
                    ): domain_selector,
                    vol.Optional(
                        CONF_INCLUDE_ENTITIES,
                        default=options.get(CONF_INCLUDE_ENTITIES, []),
                    ): entity_selector,
                    vol.Optional(
                        CONF_EXCLUDE_ENTITIES,
                        default=options.get(CONF_EXCLUDE_ENTITIES, []),
                    ): entity_selector,
                }
            ),
        )
