# Track to ICS Calendar

Downloads reservations from Track Property Management and serves them as an ICS calendar compatible with the [Rental Control HACS integration](https://github.com/tykeal/homeassistant-rental-control).

## Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `track_username` | Your Track login email | (required) |
| `track_password` | Your Track login password | (required) |
| `track_base_url` | Base URL for Track | `https://fivestarproperty.trackhs.com` |
| `export_path` | Path to the CSV export endpoint | `/owner/reservations/generate-csv/` |
| `refresh_interval_minutes` | How often to refresh the calendar | `30` |
| `checkin_time` | Default check-in time (24hr format) | `16:00` |
| `checkout_time` | Default check-out time (24hr format) | `11:00` |
| `timezone` | Timezone for events | `America/Denver` |
| `include_owner_stays` | Include "Owner Stay" events | `false` |
| `include_past_reservations` | Include past reservations | `false` |

## Usage

Once the add-on is running, use this URL in Rental Control:

```
http://localhost:8099/calendar.ics
```

Or access the web UI at `http://localhost:8099` to check status.

## How It Works

1. Logs into Track Owner Portal with your credentials
2. Downloads the reservations CSV export
3. Filters based on your settings (removes past, owner stays, etc.)
4. Converts to ICS format with Rental Control-compatible event details
5. Serves the calendar via HTTP on port 8099
6. Refreshes automatically at the configured interval

## Support

For issues or feature requests, please open an issue on GitHub.
