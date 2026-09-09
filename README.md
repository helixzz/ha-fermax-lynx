# FERMAX LYNX Gateway for Home Assistant

Local doorbell events, visitor images and explicit controls for [FERMAX LYNX Gateway](https://github.com/helixzz/fermax-lynx-gateway). Connect Home Assistant directly to your gateway: no MQTT broker, cloud account or additional HA OS app is required.

**Requirements:** Home Assistant 2026.9 or newer; gateway 0.7.0 or newer with integration API schema 1. This is a custom integration, not a Home Assistant core integration. HACS default-store inclusion has not been requested or approved.

[中文说明](docs/README.zh-Hans.md)

## Install on HA OS

### HACS custom repository

1. Install [HACS](https://www.hacs.xyz/docs/use/download/download/) if desired.
2. In HACS, open **⋮ → Custom repositories**; add `https://github.com/helixzz/ha-fermax-lynx` with type **Integration**.
3. Download **FERMAX LYNX Gateway**, then restart Home Assistant.
4. Continue with pairing below. Installing through a custom repository does not mean the project is listed in the HACS default store.

### Manual installation

Copy `custom_components/fermax_lynx` from a release into `/config/custom_components/fermax_lynx` using your normal HA OS file management method, then restart Home Assistant. Do not put the files in an extra nested repository directory.

## Pair your gateway

1. Open the gateway administrator interface and create a short-lived integration pairing code. Choose the permitted entry panels and permissions. State and events are required; camera, preview, end-call and opening are optional.
2. In HA, open **Settings → Devices & services → Add integration → FERMAX LYNX Gateway**.
3. Enter the gateway URL (for example `http://gateway.local:8765`) and pairing code.
4. HA creates a gateway device and a device for each permitted panel. The code is single-use and is not saved in HA. HA stores an independent bearer credential; revoke it from the gateway whenever needed.

Use a trusted local network for HTTP, or a gateway HTTPS origin with a trusted certificate. Credentials must not be placed in the URL. Redirects are refused; use the gateway's final origin directly. This integration does not configure TLS or expose your gateway to the Internet.

Only one HA entry is allowed per gateway. A code exchanged against an already-configured or incorrect gateway may create an unused credential; revoke that authorization in the gateway. Reauthentication and **Reconfigure** accept a new pairing code for the same gateway and update its address. Revoke the superseded credential afterwards.

## Devices and entities

| Device | Entity | Meaning |
| --- | --- | --- |
| Gateway | Calls today; opening confirmations today | Gateway local-day counters; unavailable when statistics cannot be read |
| Gateway | Building network; current call | Connection and current call state |
| Gateway | Automatic opening | Read-only policy state; does not change the policy |
| Entry panel | Doorbell; activity event | Fresh live incoming calls and permitted activity |
| Entry panel | Current visitor camera | Fresh JPEG from an active call/preview only; polling never starts a preview |
| Entry panel | Preview; end call | Explicit actions, if granted |
| Entry panel | Request opening | Only created with opening permission, and disabled by default in HA |

Enable **Request opening** explicitly in its entity settings if you need it. A gateway protocol confirmation does **not** prove a physical door opened or closed. There is intentionally no lock entity or physical door-position sensor. Controls are tied to the current panel/call, expire quickly and are never automatically retried. A network timeout can leave the outcome unknown; inspect the current visit instead of repeatedly pressing opening.

The camera provides periodic still images, not two-way audio or a streaming video transport. When no fresh permitted frame exists it returns no image; dashboard clients may still retain their last rendered image, so check entity availability before acting.

## Automations and reconnect behavior

The panel's **Doorbell** event entity displays the latest incoming event. For notifications, use the `fermax_lynx_doorbell` bus event below: it fires only for a fresh live doorbell, including the first one, and does not fire when HA restores an entity after startup. The **Activity** entity supports `incoming`, `outgoing`, `call_ended`, `open_manual`, `open_auto`, `open_unknown`, `open_denied`, and `control_failed`.

```yaml
triggers:
  - trigger: event
    event_type: fermax_lynx_doorbell
    event_data:
      entity_id: event.example_entry_doorbell
actions:
  - action: persistent_notification.create
    data:
      title: Doorbell
      message: A visitor is calling.
```

Replace the synthetic entity ID with your panel's Doorbell entity ID. If you instead build a state-trigger automation, guard against entity restoration and unknown/unavailable transitions.

A single SSE connection pushes states and events. Disconnects mark entities unavailable and reconnect with bounded backoff. Gateway history is consumed only to move the cursor; **missed doorbells are never replayed as notifications after reconnect or HA restart**. Live events older than 30 seconds (using the gateway clock), duplicate journal IDs and repeated incoming events for the same call are suppressed. Gateway or HA unavailability does not stop the gateway's own ringing or opening policy.

## Troubleshooting

- **Pairing failed:** generate a fresh code; confirm the code's gateway and permissions.
- **Authentication required:** an authorization was revoked or gateway password reset. Generate a new code and use HA's reauthentication prompt.
- **Unavailable:** check gateway/network connectivity and granted panels; no opening requests are retried during recovery.
- **No camera/button:** grant that permission and reconfigure with a new code. Opening also needs explicit HA entity enablement.
- Diagnostics include only version, availability, permission names and panel count, never URLs, tokens, names, images or call IDs.

## Development

Use Python 3.14; `pip install -r requirements_test.txt`, then `pytest` and `ruff check .`. Tests use real Home Assistant fixtures and synthetic gateway responses only. Never test a physical opening as part of CI.

Release numbers follow SemVer: integration releases are independent of gateway versions. API schema 1 is the compatibility boundary. HACS submission and ecosystem branding can follow after installation feedback; see [HACS publishing requirements](https://www.hacs.xyz/docs/publish/integration/).

An optional cross-repository contract test launches only the gateway's synthetic loopback fixture: `FERMAX_GATEWAY_SOURCE=/path/to/fermax-lynx-gateway pytest tests/test_gateway_e2e.py`. It covers actual pairing, state, SSE incoming events, current JPEG, denied opening, end-call and revocation without constructing a live controller. CI runs the standalone suite against HA 2026.9.0 and 2026.9.1.

The original door-and-signal icon ships locally under `custom_components/fermax_lynx/brand` ([HA local branding](https://developers.home-assistant.io/blog/2026/02/24/brands-proxy-api/)); it does not imply manufacturer endorsement.
