# Home Assistant Add-ons: Track to ICS Calendar

[![Open your Home Assistant instance and show the add add-on repository dialog with this repository pre-filled.](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fbencarver%2Fha-track-to-ics)

## Add-ons

This repository contains the following add-ons:

### [Track to ICS Calendar](./track_to_ics)

![Supports aarch64 Architecture][aarch64-shield]
![Supports amd64 Architecture][amd64-shield]
![Supports armhf Architecture][armhf-shield]
![Supports armv7 Architecture][armv7-shield]
![Supports i386 Architecture][i386-shield]

Downloads reservations from Track Property Management and serves them as an ICS calendar for the Rental Control HACS integration.

## Installation

1. Click the button above, or manually add this repository URL to your Home Assistant add-on store:
   ```
   https://github.com/bencarver/ha-track-to-ics
   ```

2. Find "Track to ICS Calendar" in the add-on store and install it

3. Configure with your Track credentials

4. Start the add-on

5. Use `http://localhost:8099/calendar.ics` as the calendar URL in Rental Control

## Features

- Authenticates with Track Property Management (trackhs.com)
- Downloads reservations and converts to ICS format
- Serves calendar via HTTP for Rental Control integration
- Automatic refresh at configurable intervals
- Filters out past reservations and owner stays (configurable)
- Modern web UI for status monitoring
- Optional Home Assistant event on fetch errors so you can automate notifications (mobile, email, etc.)

[aarch64-shield]: https://img.shields.io/badge/aarch64-yes-green.svg
[amd64-shield]: https://img.shields.io/badge/amd64-yes-green.svg
[armhf-shield]: https://img.shields.io/badge/armhf-yes-green.svg
[armv7-shield]: https://img.shields.io/badge/armv7-yes-green.svg
[i386-shield]: https://img.shields.io/badge/i386-yes-green.svg
