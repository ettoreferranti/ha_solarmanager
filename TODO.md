# TODO

Concrete next steps, prioritised. Pick one and start a Claude Code session asking "implement TODO #N".

## Shipped

- ✅ v0.1.x — initial read-only cloud transport, gateway + per-device sensors.
- ✅ v0.2.0 — per-device cumulative kWh sensors (`iWhTotal` / `eWhTotal`) feeding the Energy dashboard.
- ✅ v0.3.x — local API transport (`/v2/point` over HTTPS with `X-API-Key`), config-flow menu for Cloud/Local choice, options flow to switch later, grid Import/Export Power synthesized from the grid meter in local mode.

## Next up

### 1. Configurable polling interval

Currently hardcoded to 30 s in `const.py`. The options flow already exists (for transport choice) — add a polling-interval field there. Coordinator reads from `entry.options` on reload.

Files: `config_flow.py` (extend both cloud and local option steps), `coordinator.py` (read from `entry.options`).

Acceptance: Configure → polling interval (10 / 30 / 60 / 300 s). Change applies on reload.

### 2. Dynamic device discovery

Per-device sensors are payload-driven from the first poll. If a user adds a device to Solar Manager mid-life, an HA restart is required to surface it. Detect new devices on every poll and register them dynamically via `async_add_entities` from the coordinator listener.

Files: `sensor.py` (entity registration), `__init__.py` (wire up the listener).

Acceptance: add a new plug in Solar Manager → it appears in HA within one polling cycle.

### 3. Local-only device types (deferred from the v0.3 PR)

The local payload exposes per-device fields we don't currently model:
- `switchState` (0/1) — natural fit for `binary_sensor` for switchable loads.
- `heatingAdjustment` (integer) and `operationState` (integer) — heating/heat-pump devices.

Files: `const.py` (new field maps), `sensor.py` / new `binary_sensor.py` platform.

Acceptance: switchable loads expose a `binary_sensor` reflecting their state. Heating devices expose adjustment / operation state sensors.

## Quality

### 4. Unit tests

Zero coverage today. Bring it up to at least:

- Transport: `CloudTransport` token refresh + 401 retry, `LocalTransport` grid meter identification with edge cases (no devices, all zero, ambiguous match, no eWh keys).
- Config flow: both Cloud and Local paths, invalid creds, network error, duplicate gateway.
- Sensor entity value extraction with edge cases (None, missing field, wrong type).

Tooling: `pytest` + `pytest-homeassistant-custom-component` + `aioresponses`.

### 5. Brand assets

Submit logo + icon to <https://github.com/home-assistant/brands> so the integration shows the Solar Manager logo in HA's UI instead of the generic placeholder.

### 6. Translations

Currently EN and DE only. Italian and French would be appreciated by Swiss users.

### 7. Local-mode device names

The local API has no `/info/sensors` equivalent, so devices show as `Device <id-suffix>` in pure local installs. Options:

- Cache the cloud `/info/sensors` response once at setup (require a one-off cloud login even for local-mode users).
- Add a "name your devices" step to the local config flow with the discovered `_id` list.
- Document that users migrating from cloud should keep `smId` so existing names persist.

## v1.0 — write capability (deliberately deferred)

Only after the v0.x line is stable and well-tested. See `CONTRIBUTING.md` "Read-only guarantee" section for the rules.

Candidate writeable services, highest to lowest priority by likely user value:

- `solarmanager_v3.set_battery_eco_limit` — daily reserve % the battery should keep
- `solarmanager_v3.set_battery_charge_target` — force-charge to N% by time T
- `solarmanager_v3.set_device_priority` — reorder load priority for the dispatcher

All require careful UX. Each must have:

- Confirmation dialog in the service call
- Bounded input validation (no -1% battery, no 200% targets)
- Clear logging of every write

## Maintenance hygiene

- Tag a release after every functionally meaningful merge to `main`.
- Watch <https://github.com/home-assistant/core> deprecation announcements for HA framework changes affecting custom integrations (e.g. the `OptionsFlow.__init__` removal in HA 2025.12 / 2026 that broke v0.3.0).
- The Solar Manager API has versioned itself once (v1 → v3). If a v4 appears, evaluate whether to migrate or maintain both.

## Long-term, "if interested" ideas

- Expose a service that returns the raw stream/point payload as an attribute — useful for users wanting to template novel calculations.
- Add Forecast.Solar integration: combine your latitude/longitude/panel-orientation with HA's built-in forecast to show "expected vs actual" PV bars.
- Energy-cost integration: pull EKZ tariff schedule from a Swiss tariff API (if one exists) and overlay cost on the energy dashboard.
- Companion Lovelace card: a polished single-card view showing live distribution + daily totals + top consumers, designed for the living-room screen kiosk.
