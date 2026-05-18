# Contributing

Contributions welcome. This file documents the conventions to follow.

## Setup

```bash
git clone https://github.com/ettoreferranti/ha_solarmanager.git
cd ha_solarmanager
```

For local development against a running Home Assistant instance, the simplest workflow:

1. Develop on your machine in this repo.
2. Push to a feature branch on GitHub.
3. In HA: HACS → Solar Manager (v3) → ⋮ → Redownload → restart HA.

For tighter loops, symlink the dev copy from inside HA's filesystem (via the SSH or Studio Code Server add-on):

```bash
# In HA's terminal
cd /root
git clone https://github.com/<you>/ha_solarmanager.git
rm -rf /config/custom_components/solarmanager_v3
ln -s /root/ha_solarmanager/custom_components/solarmanager_v3 \
      /config/custom_components/solarmanager_v3
```

Then `git pull` in `/root/ha_solarmanager` and restart HA between iterations.

## Code style

- Python 3.12+ (matches HA's minimum).
- Type hints on all new code. Use `from __future__ import annotations` at the top of every module.
- Async everywhere. No `requests`, no `time.sleep` — use `aiohttp` and `asyncio.sleep`.
- Logger: `_LOGGER = logging.getLogger(__name__)` at module top. Use it; never `print`.
- No new runtime dependencies without a strong reason. The integration currently has zero `requirements:` entries — keep it that way unless adding one is genuinely cheaper than reimplementing.

## Read-only guarantee (current invariant)

**Until the v0.x line ends, no `PUT`, `POST`, `DELETE`, or `PATCH` HTTP methods are used against Solar Manager endpoints, except `POST /v1/oauth/login` and `POST /v1/oauth/refresh` for authentication.**

If you add a feature that would require a write call, the change must:
1. Be opt-in via the options flow (default off).
2. Be implemented as an HA `service` registered via `async_register_admin_service`, not as an entity property setter.
3. Bump the integration to v1.0.0 (semantic versioning: read-only-only is a stable contract; breaking it is a major version bump).

This applies to both transports. The Solar Manager local API also has write endpoints (battery control, switch toggles); those are off-limits under the same rule.

## Where to add what

| Change | File |
|---|---|
| New cloud API endpoint | `transport.py` (add a method on `CloudTransport`) and `const.py` (add the URL constant) |
| New local API endpoint | `transport.py` (add a method on `LocalTransport`) and `const.py` (add the URL constant) |
| New gateway-level sensor | `const.py` (extend `GATEWAY_SENSORS` tuple) — sensor entity is auto-created if the field is present in the snapshot |
| New per-device sensor field | `const.py` (extend `DEVICE_SENSORS` tuple) — same |
| New device class for an existing field | `sensor.py` (`_device_class_from_str` helper) |
| New transport | `transport.py` (implement `SolarManagerTransport` protocol — `async_test`, `async_get_snapshot`, `async_get_devices_meta`) + `config_flow.py` (menu option + form + options-flow step) |
| Configurable polling interval | `config_flow.py` (extend existing options flow) and `coordinator.py` (read from entry options) |
| New translation language | Copy `translations/en.json` to `translations/<code>.json` |

## Adding new sensors

The pattern is:

1. Identify the source field. Cloud: Solar Manager v3 swagger (<https://cloud.solar-manager.ch/solarManager/swagger.json>). Local: capture a `/v2/point` response from your gateway and inspect.
2. Confirm the field is in the snapshot by adding debug logging (`logger: custom_components.solarmanager_v3: debug` in `configuration.yaml`) and watching `home-assistant.log`.
3. Add a tuple entry in `const.py`'s `GATEWAY_SENSORS` or `DEVICE_SENSORS`.
4. Tuple format: `(api_field_name, unit, device_class_string, friendly_name, mdi_icon)`.
5. For non-trivial cases (e.g. fields needing transformation), edit `sensor.py`'s `native_value` property.

`sensor.py` already filters by key presence in the first snapshot, so a sensor declared in `GATEWAY_SENSORS` is only instantiated when the active transport's payload actually contains the field. That keeps cloud-only and local-only fields out of the wrong mode automatically.

For transport-specific field reshaping (e.g. the synthesis of `iW`/`eW` in local mode), do it in the transport's normalization step, not in `sensor.py`.

## Versioning

Semantic versioning. v0.x = unstable API; treat as alpha. Breaking changes allowed in patches *during* v0.x, must be documented in release notes.

When tagging a release:
```bash
git tag -a vX.Y.Z -m "Brief release summary"
git push --tags
```

Then create a GitHub Release from the tag with a fuller changelog. HACS reads release notes for users.

## Commits

Conventional Commits style is encouraged but not required:

```
feat: add per-device iWhTotal sensors
fix: handle stream payload missing devices array
docs: clarify Riemann helper recipe in README
refactor: extract _device_class_from_str into helper module
```

One change per commit. Avoid mixing functional and stylistic changes.

## Pull requests

For external contributors:

1. Fork the repo, make your changes on a feature branch.
2. Test against a running HA instance — at minimum verify the integration loads and entities populate.
3. Open a PR with a description of what changed and why.
4. Note any new external dependencies or breaking changes prominently.

For the maintainer (Ettore): direct commits to `main` are fine for now, but use feature branches for any changes that take more than one commit to land.

## Issues

Use GitHub Issues for bugs and feature requests. Useful information to include in bug reports:

- HA version (Settings → About).
- Integration version (visible in HACS or in `manifest.json`).
- Solar Manager hardware: which inverters, which battery (if any), and the gateway model.
- Excerpts from `home-assistant.log` filtered to `solarmanager_v3`.

To enable debug logging:

```yaml
logger:
  default: warning
  logs:
    custom_components.solarmanager_v3: debug
```
