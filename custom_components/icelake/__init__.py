"""Icelake integration — ship Home Assistant metrics to Icelake."""

import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

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

_LOGGER = logging.getLogger(__name__)

type IcelakeConfigEntry = ConfigEntry


async def async_setup_entry(hass: HomeAssistant, entry: IcelakeConfigEntry) -> bool:
    sender = IcelakeSender(
        endpoint=entry.data[CONF_ENDPOINT],
        client_id=entry.data[CONF_CLIENT_ID],
        api_key=entry.data[CONF_API_KEY],
        source_id=entry.data.get(CONF_SOURCE_ID, DEFAULT_SOURCE_ID),
        send_interval=entry.data.get(CONF_SEND_INTERVAL, DEFAULT_SEND_INTERVAL),
    )
    await sender.start()

    include_domains = set(entry.options.get(CONF_INCLUDE_DOMAINS, []))
    exclude_domains = set(entry.options.get(CONF_EXCLUDE_DOMAINS, []))
    include_entities = set(entry.options.get(CONF_INCLUDE_ENTITIES, []))
    exclude_entities = set(entry.options.get(CONF_EXCLUDE_ENTITIES, []))

    def _entity_allowed(entity_id: str) -> bool:
        domain = entity_id.split(".", 1)[0]

        if include_entities and entity_id not in include_entities:
            return False
        if entity_id in exclude_entities:
            return False
        if include_domains and domain not in include_domains:
            return False
        if domain in exclude_domains:
            return False

        return True

    @callback
    def _handle_state_change(event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        entity_id = new_state.entity_id
        if not _entity_allowed(entity_id):
            return

        state_value = new_state.state
        if state_value in ("unknown", "unavailable"):
            return

        numeric_value = _to_numeric(state_value)
        if numeric_value is None:
            return

        domain = entity_id.split(".", 1)[0]
        object_id = entity_id.split(".", 1)[1]
        timestamp_ms = int(time.time() * 1000)

        labels = [
            ("__name__", f"ha_{domain}_{object_id}"),
            ("entity_id", entity_id),
            ("domain", domain),
            ("friendly_name", new_state.attributes.get("friendly_name", "")),
        ]

        unit = new_state.attributes.get("unit_of_measurement")
        if unit:
            labels.append(("unit", unit))

        device_class = new_state.attributes.get("device_class")
        if device_class:
            labels.append(("device_class", device_class))

        sender.add_sample(labels, numeric_value, timestamp_ms)

    unsub = hass.bus.async_listen("state_changed", _handle_state_change)

    async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
        nonlocal include_domains, exclude_domains, include_entities, exclude_entities
        include_domains = set(entry.options.get(CONF_INCLUDE_DOMAINS, []))
        exclude_domains = set(entry.options.get(CONF_EXCLUDE_DOMAINS, []))
        include_entities = set(entry.options.get(CONF_INCLUDE_ENTITIES, []))
        exclude_entities = set(entry.options.get(CONF_EXCLUDE_ENTITIES, []))
        _LOGGER.info("Icelake entity filter updated")

    entry.async_on_unload(entry.add_update_listener(_options_updated))

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "sender": sender,
        "unsub": unsub,
    }

    _LOGGER.info("Icelake integration started, sending to %s", entry.data[CONF_ENDPOINT])
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IcelakeConfigEntry) -> bool:
    data = hass.data[DOMAIN].pop(entry.entry_id)
    data["unsub"]()
    await data["sender"].stop()
    _LOGGER.info("Icelake integration stopped")
    return True


def _to_numeric(state: str) -> float | None:
    """Convert state string to a numeric value, or None if not numeric."""
    if state in ("on", "open", "home", "active", "playing", "locked"):
        return 1.0
    if state in ("off", "closed", "not_home", "idle", "standby", "paused", "unlocked"):
        return 0.0
    try:
        return float(state)
    except (ValueError, TypeError):
        return None
