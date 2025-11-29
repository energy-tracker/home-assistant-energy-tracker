# Energy Tracker Integration for Home Assistant

[![GitHub Release](https://img.shields.io/github/release/energy-tracker/home-assistant-energy-tracker.svg)](https://github.com/energy-tracker/home-assistant-energy-tracker/releases)
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

## Configuration

### Prerequisites

Before configuring the integration, you need an [Energy Tracker account](https://www.energy-tracker.best-ios-apps.de):

1. Create an account at [www.energy-tracker.best-ios-apps.de](https://www.energy-tracker.best-ios-apps.de)
2. Log in to your Energy Tracker account
3. Navigate to **API** → **Access Tokens**
4. Create a new **Personal Access Token**
5. Copy the token - you'll need it for the integration setup

### Step 1: Add Integration in Home Assistant

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "Energy Tracker"
4. Enter a name for this account (e.g., "My Energy Tracker")
5. Paste your personal access token
6. Click **Submit**

### Step 2: Get Your Standard Measuring Device ID

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

### Action `energy_tracker.send_meter_reading`

Send a meter reading from a Home Assistant sensor to Energy Tracker.

#### Action Parameters

| Parameter | Required | Type | Description |
|-----------|----------|------|-------------|
| `entry_id` | Yes | config_entry | Your Energy Tracker account (select from dropdown) |
| `device_id` | Yes | string | Standard measuring device ID from Energy Tracker (UUID format) |
| `source_entity_id` | Yes | entity_id | Home Assistant sensor providing the meter reading |
| `allow_rounding` | No | boolean | Round value to meter precision (default: `true`) |

### Example Automation

Send your electricity meter reading daily at 23:55:

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

Use the visual automation editor to automatically select your account and sensor from dropdowns.

## Supported Entity Types

The integration accepts meter readings from:

- **Sensors** (`sensor.*`) - e.g., `sensor.electricity_meter`, `sensor.gas_meter`
- **Input Numbers** (`input_number.*`) - Manual input helpers
- **Number Entities** (`number.*`) - Numeric device values

### Requirements

- Entity state must be numeric
- Entity must have a valid timestamp (`last_updated`)
- Entity state must not be `unavailable` or `unknown`

## Error Handling

The integration provides comprehensive error handling with detailed logs and Home Assistant issue notifications for authentication errors and other problems.

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
A: Click the **⋮** menu on your Energy Tracker integration and select **Reconfigure**. Leave the token field empty to keep the existing token, or enter a new one.

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
