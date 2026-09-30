# Energy Tracker Integration for Home Assistant

[![GitHub Release](https://img.shields.io/github/release/energy-tracker/home-assistant-energy-tracker.svg)](https://github.com/energy-tracker/home-assistant-energy-tracker/releases)
[![HACS](https://img.shields.io/badge/HACS-Default-41BDF5.svg)](https://github.com/hacs/integration)
[![License](https://img.shields.io/github/license/energy-tracker/home-assistant-energy-tracker.svg)](LICENSE)

Send meter readings from Home Assistant sensors to your [Energy Tracker](https://www.energy-tracker.best-ios-apps.de) account using an action or automation.

## Features

- Configure multiple accounts through the Home Assistant UI.
- Send readings to standard measuring devices on demand or through automations.
- Optionally round readings to the meter's configured precision.
- Receive translated error messages when an action fails.

The integration does not create entities or retrieve readings from Energy Tracker.

## Installation

> **Note**: This integration is currently available via HACS only. Home Assistant Core integration is planned for the future.

Requires **Home Assistant 2026.3.1 or newer** (Python 3.14.2+).

### Upgrading from 1.0.0

Update Home Assistant to 2026.3.1 or newer before installing this release. Existing accounts are migrated automatically; their account references and automation action fields stay the same. You do not need to remove and recreate the integration.

Meter readings must be finite, non-negative, and below `10000000000`. Values are sent with up to six fractional digits; additional digits are truncated. Review automations that send values outside these limits. The **Allow rounding** setting continues to control rounding to the meter's precision in Energy Tracker.

### Step 1: Install the Integration

#### Option A: Via HACS (Recommended)

1. Open [HACS](https://hacs.xyz/) in Home Assistant.
2. Search for **Energy Tracker** and download the integration.
3. Restart Home Assistant.

#### Option B: Manual Installation

1. Download the latest release from [GitHub Releases](https://github.com/energy-tracker/home-assistant-energy-tracker/releases)
2. Copy the `custom_components/energy_tracker/` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

### Step 2: Configure the Integration

Before configuring, you need an API token from your [Energy Tracker account](https://www.energy-tracker.best-ios-apps.de):

1. Log in at [www.energy-tracker.best-ios-apps.de](https://www.energy-tracker.best-ios-apps.de)
2. Navigate to **API** > **Access Tokens**.
3. Select **Generate token** and grant **Create or update meter readings** (`write:meter-reading`). An existing token with the broader `meter-reading` permission also works.
4. Copy the token. It is only shown once. Paste the token itself into Home Assistant, without a `Bearer` prefix.

Then in Home Assistant:

1. Go to **Settings** > **Devices & services**.
2. Select **Add integration** and search for **Energy Tracker**.
3. Enter an **Account name** and your **Personal access token**.
4. Select **Submit**.

Repeat these steps to configure another token. Each token can only be configured once.

### Step 3: Get Your Standard Measuring Device ID

You need the device ID to send meter readings. There are two ways to get it:

#### Option A: Via Energy Tracker Web Interface

1. Log into your Energy Tracker account
2. Open the standard device's settings and select **Overview**.
3. Copy the **Device Identifier**.
4. Remove the `std-` prefix. The ID should be in UUID format, like `deadbeef-dead-beef-dead-beefdeadbeef`.

#### Option B: Via API

1. Log into your Energy Tracker account
2. Navigate to **API** → **Documentation**
3. Use the API endpoint to retrieve your devices
4. The IDs returned are already in the correct format (without `std-` prefix)

Listing devices through the API requires `read:measuring-device` or `measuring-device` permission. That permission is not needed to send readings when you already know the device ID.

## Usage

This integration provides a service only — no entities are created. Create an automation to send meter readings.

### Step 4: Create an Automation

1. Go to **Settings** > **Automations & scenes** and create an automation.
2. Add a time trigger, for example daily at 23:55.
3. Add the **Energy Tracker: Send meter reading** action.
4. Select the **Account**, enter the **Standard measuring device ID**, and select the **Sensor** providing the reading.
5. Choose whether to **Allow rounding**, then save the automation.

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

For the automation editor's **Edit in YAML** view, use the following example. Replace `YOUR_CONFIG_ENTRY_ID` with the account's `entry_id` shown when you select the account in the visual action editor and switch to YAML. Replace the device and sensor IDs with your own.

```yaml
alias: "Send daily electricity reading"
triggers:
  - trigger: time
    at: "23:55:00"
actions:
  - action: energy_tracker.send_meter_reading
    data:
      entry_id: "YOUR_CONFIG_ENTRY_ID"
      device_id: "deadbeef-dead-beef-dead-beefdeadbeef"
      source_entity_id: sensor.electricity_meter
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

Action failures produce translated error messages. Requests are not automatically retried.

The reading uses the source entity's `last_updated` timestamp. Sending an unchanged source again can produce a conflict when a reading already exists for that timestamp.

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
A: Authentication is checked when a reading is sent. Verify that the token is valid and has `write:meter-reading` or `meter-reading` permission. Go to **Settings** > **Devices & services** > **Energy Tracker**, open the account's **⋮** menu, and select **Reconfigure** to replace the token.

**Q: How do I update my token?**  
A: Click the **⋮** menu on your Energy Tracker integration and select **Reconfigure**. Enter your personal access token. Leading and trailing whitespace is removed. Empty input is rejected and leaves the existing configuration unchanged. Cancel the dialog if you do not want to change the token.

## Removing an account or the integration

1. Disable or update automations and scripts that send readings through the account you want to remove.
2. Go to **Settings** > **Devices & services** > **Energy Tracker**.
3. Open the account's **⋮** menu and select **Delete**.

Removing an account stops sending readings through that account. It does not delete readings stored in Energy Tracker or revoke its access token. Revoke the token in Energy Tracker if it is no longer needed.

To uninstall the integration completely, remove all its accounts first, then remove it through HACS and restart Home Assistant. For a manual installation, remove `config/custom_components/energy_tracker/` instead and restart Home Assistant.

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
