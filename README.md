# Energy Tracker Integration for Home Assistant

[![GitHub Release](https://img.shields.io/github/release/energy-tracker/home-assistant-energy-tracker.svg)](https://github.com/energy-tracker/home-assistant-energy-tracker/releases)
[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/energy-tracker/home-assistant-energy-tracker.svg)](LICENSE)

Send meter readings from Home Assistant sensors automatically to your [Energy Tracker](https://www.energy-tracker.best-ios-apps.de) account.

## Features

- ✅ **Config Flow Setup**: Easy configuration through the Home Assistant UI
- ✅ **Multi-Account Support**: Connect multiple Energy Tracker accounts
- ✅ **Automated Meter Readings**: Send sensor values automatically via automations
- ✅ **Optional Value Rounding**: Automatic rounding to match your meter's precision
- ✅ **Full Localization**: 26 languages supported
- ✅ **Comprehensive Error Handling**: Clear error messages and repair flows
- ✅ **Cloud Integration**: Direct API connection to Energy Tracker service

## Installation

> **Note**: This integration is currently available via HACS only. Home Assistant Core integration is planned for the future.

Requires **Home Assistant 2026.3.1 or newer** (Python 3.14.2+).

### Step 1: Install the Integration

#### Option A: Via HACS (Recommended)

1. Open [HACS](https://hacs.xyz/) in Home Assistant
2. Go to **Integrations**
3. Click **+ Explore & Download Repositories**
4. Search for "Energy Tracker"
5. Click **Download**
6. Restart Home Assistant

#### Option B: Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/energy-tracker/home-assistant-energy-tracker/releases)
2. Copy the `custom_components/energy_tracker/` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

### Step 2: Configure the Integration

Before configuring, you need an API token from your [Energy Tracker account](https://www.energy-tracker.best-ios-apps.de):

1. Log in at [www.energy-tracker.best-ios-apps.de](https://www.energy-tracker.best-ios-apps.de)
2. Navigate to **API** → **Access Tokens**
3. Create a new **Personal Access Token**
4. Copy the token

Then in Home Assistant:

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Energy Tracker"
4. Enter a name for this account (e.g., "My Energy Tracker")
5. Paste your personal access token
6. Click **Submit**

### Step 3: Get Your Standard Measuring Device ID

You need the device ID to send meter readings. There are two ways to get it:

#### Option A: Via Energy Tracker Web Interface

1. Log into your Energy Tracker account
2. Go to your device details
3. Copy the **Standard Measuring Device ID** 
4. **Important**: Remove the `std-` prefix! The ID should be in UUID format like `deadbeef-dead-beef-dead-beefdeadbeef`

#### Option B: Via API (Recommended)

1. Log into your Energy Tracker account
2. Navigate to **API** → **Documentation**
3. Use the API endpoint to retrieve your devices
4. The IDs returned are already in the correct format (without `std-` prefix)

## Usage

This integration provides a service only — no entities are created. Create an automation to send meter readings.

### Step 4: Create an Automation

1. Go to **Settings** → **Automations & Scenes**
2. Click **+ Create Automation**
3. Add a **Trigger** (e.g., time-based: daily at 23:55)
4. Click **Add action** and search for **Energy Tracker: Send meter reading**
5. Fill in the required fields
6. Save the automation

## Reference

### Action `energy_tracker.send_meter_reading`

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entry_id` | Yes | config_entry | Your Energy Tracker account (select from dropdown) |
| `device_id` | Yes | string | Standard measuring device ID from Energy Tracker (UUID format) |
| `source_entity_id` | Yes | entity_id | Home Assistant sensor providing the meter reading |
| `allow_rounding` | No | boolean | Round value to meter precision (default: `true`) |

Sensor values are sent as decimal strings through API v3. Values must be finite,
non-negative and below `10000000000`. Fractional digits beyond six places are
truncated before sending. `allow_rounding` separately controls server-side rounding
to the meter’s configured precision.

### Example Automation (YAML)

```yaml
- alias: "Send daily electricity reading"
  triggers:
    - trigger: time
      at: "23:55:00"
  actions:
    - action: energy_tracker.send_meter_reading
      data:
        entry_id: <select from dropdown>
        device_id: "deadbeef-dead-beef-dead-beefdeadbeef"
        source_entity_id: <select from dropdown>
        allow_rounding: true
```

### Supported Entity Types

The integration accepts meter readings from:

- **Sensors** (`sensor.*`) - e.g., `sensor.electricity_meter`, `sensor.gas_meter`
- **Input Numbers** (`input_number.*`) - Manual input helpers
- **Number Entities** (`number.*`) - Numeric device values

### Requirements

- Entity state must be numeric
- Entity must have a valid timestamp (`last_updated`)
- Entity state must not be `unavailable` or `unknown`

## Error Handling

The integration provides comprehensive error handling with localized error messages.

## Troubleshooting

### Enable Debug Logging

Add to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.energy_tracker: debug
```

Then check **Settings** → **System** → **Logs** for detailed information.

### Common Issues

**Q: "Standard measuring device not found" error**  
A: Verify the device ID is correct. It should be a UUID format like `deadbeef-dead-beef-dead-beefdeadbeef`. Find it in your Energy Tracker account under device details.

**Q: "Entity unavailable" error in automation**  
A: Add a condition to check entity state before sending:

```yaml
conditions:
  - "{{ states('sensor.electricity_meter') not in ['unavailable', 'unknown'] }}"
```

**Q: Integration shows authentication error after setup**  
A: Your token may be invalid. Go to **Settings** → **Devices & Services** → **Energy Tracker** → **Reconfigure** to update your token.

**Q: How do I update my token?**  
A: Click the **⋮** menu on your Energy Tracker integration and select **Reconfigure**. Enter your personal access token. Leading and trailing whitespace is removed. Empty input is rejected and leaves the existing configuration unchanged. Cancel the dialog if you do not want to change the token.

## Support

- **Energy Tracker Support**: [Contact Energy Tracker](https://www.energy-tracker.best-ios-apps.de/contact)
- **Home Assistant Community**: [Community Forum](https://community.home-assistant.io/)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Copyright (c) 2015-2025 energy-tracker support@best-ios-apps.de

## Related Links

- [Energy Tracker Website](https://www.energy-tracker.best-ios-apps.de)
- [Home Assistant Documentation](https://www.home-assistant.io/)
- [Home Assistant Developer Docs](https://developers.home-assistant.io/)
