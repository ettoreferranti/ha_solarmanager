"""Constants for the Solar Manager v3 integration."""
from __future__ import annotations

DOMAIN = "solarmanager_v3"

# API
API_BASE = "https://cloud.solar-manager.ch"
ENDPOINT_LOGIN = "/v1/oauth/login"
ENDPOINT_REFRESH = "/v1/oauth/refresh"
ENDPOINT_STREAM = "/v3/users/{sm_id}/data/stream"
ENDPOINT_INFO_SENSORS = "/v1/info/sensors/{sm_id}"

# Polling
DEFAULT_SCAN_INTERVAL_SECONDS = 30
REQUEST_TIMEOUT_SECONDS = 15
TOKEN_REFRESH_LEEWAY_SECONDS = 60  # refresh that many seconds before expiry

# Config keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_SM_ID = "sm_id"

# Gateway-level fields from /v3/users/{smId}/data/stream
# (key, unit, device_class, name, icon)
GATEWAY_SENSORS: tuple[tuple[str, str, str | None, str, str | None], ...] = (
    ("pW",  "W",  "power",   "PV Production Power",      "mdi:solar-power"),
    ("cW",  "W",  "power",   "Household Consumption Power", "mdi:home-lightning-bolt"),
    ("iW",  "W",  "power",   "Grid Import Power",        "mdi:transmission-tower-import"),
    ("eW",  "W",  "power",   "Grid Export Power",        "mdi:transmission-tower-export"),
    ("bcW", "W",  "power",   "Battery Charge Power",     "mdi:battery-charging"),
    ("bdW", "W",  "power",   "Battery Discharge Power",  "mdi:battery-arrow-down"),
    ("soc", "%",  "battery", "Battery State of Charge",  "mdi:battery"),
)

# Per-device fields from devices[] in the same stream response.
# Each registered device gets these sensors when the field is present.
DEVICE_SENSORS: tuple[tuple[str, str, str | None, str, str | None], ...] = (
    ("power",       "W",  "power",       "Power",            "mdi:flash"),
    ("soc",         "%",  "battery",     "State of Charge",  "mdi:battery"),
    ("temperature", "°C", "temperature", "Temperature",      "mdi:thermometer"),
    ("activeDevice","",   None,          "Active",           "mdi:power"),
    ("signal",      "",   None,          "Signal",           "mdi:wifi"),
)
