<p align="center">
  <img src="assets/logo-light.svg" alt="Icelake" width="280" />
</p>

<h3 align="center">Home Assistant Integration</h3>

<p align="center">
  Ship all your Home Assistant entity metrics to <a href="https://icelake.io">Icelake</a> for long-term storage, analytics, and visualization.
</p>

<p align="center">
  <a href="#installation"><strong>Install</strong></a> &middot;
  <a href="#configuration"><strong>Configure</strong></a> &middot;
  <a href="#how-it-works"><strong>How it works</strong></a> &middot;
  <a href="#entity-filtering"><strong>Filtering</strong></a>
</p>

---

## Features

- **Plug-and-play** &mdash; install, paste your API key, done
- **All entities by default** &mdash; every numeric sensor, switch, and binary sensor is sent automatically
- **Configurable filtering** &mdash; include or exclude by domain or entity ID
- **Efficient batching** &mdash; samples are buffered and sent in compressed batches on a configurable interval
- **Resilient delivery** &mdash; if Icelake is temporarily unreachable, samples are kept in memory (up to 100k) and retried with exponential backoff
- **Prometheus remote write** &mdash; uses the standard protocol, no translation layer needed
- **Lightweight** &mdash; no extra containers, no sidecars, runs inside Home Assistant

## Installation

### HACS (recommended)

1. Open HACS in your Home Assistant instance
2. Go to **Integrations** > **Custom repositories**
3. Add this repository URL and select **Integration** as the category
4. Search for **Icelake** and install it
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/icelake` directory into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant

## Configuration

1. In the Icelake admin UI, create an API key for your Home Assistant instance. Copy the **Client ID** and **API Key**.

2. In Home Assistant, go to **Settings** > **Devices & Services** > **Add Integration** and search for **Icelake**.

3. Enter your connection details:

   | Field | Description |
   |---|---|
   | **Icelake URL** | Base URL of your Icelake server (default: `https://api.icelake.eu`) |
   | **Client ID** | Client ID from the Icelake admin UI |
   | **API Key** | API key from the Icelake admin UI |
   | **Source identifier** | Name for this HA instance in Icelake (default: `homeassistant`) |
   | **Send interval** | Batch send interval in seconds (default: `30`, range: 5-300) |

   The integration will test the connection before saving.

## Entity filtering

By default, all entities with numeric or boolean states are sent. To customize this, go to the integration's **Options** after setup:

- **Include domains** &mdash; only send entities from these domains (e.g. `sensor`, `climate`)
- **Exclude domains** &mdash; never send entities from these domains
- **Include entities** &mdash; only send these specific entities
- **Exclude entities** &mdash; never send these specific entities

Filter logic: include lists take priority. If an include list is set, only matching items are sent. Exclude lists then remove from that set.

## How it works

```
Home Assistant               Icelake

  state_changed  ──>  buffer ──>  snappy + protobuf  ──>  POST /prometheus/v1/write
  event bus           (batch)     (Prometheus remote       (Basic auth)
                                   write format)
```

1. The integration listens to `state_changed` events on the Home Assistant event bus
2. Numeric states are sent as-is. Boolean states (`on`/`off`, `open`/`closed`, `home`/`not_home`, etc.) are mapped to `1.0`/`0.0`. Non-numeric states are skipped.
3. Samples accumulate in a buffer. Every N seconds, the buffer is encoded as Prometheus protobuf, snappy-compressed, and sent to Icelake
4. Each metric includes labels: `entity_id`, `domain`, `friendly_name`, `unit` (if available), and `device_class` (if available)

### Metric naming

Metrics are named `ha_{domain}_{object_id}` (the `__name__` label in Prometheus convention). For example:

| Entity | Metric name |
|---|---|
| `sensor.living_room_temperature` | `ha_sensor_living_room_temperature` |
| `binary_sensor.front_door` | `ha_binary_sensor_front_door` |
| `climate.bedroom` | `ha_climate_bedroom` |

## Requirements

- Home Assistant 2024.1 or later
- An Icelake server with an API key

## License

Apache License 2.0 &mdash; see [LICENSE](LICENSE).
