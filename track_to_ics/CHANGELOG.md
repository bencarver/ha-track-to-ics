# Changelog

All notable changes to this project will be documented in this file.

## [1.0.8] - 2026-02-28

### Fixed
- "Include past reservations" option now works correctly
- "Checked Out" status filter no longer overrides the include_past_reservations setting

## [1.0.6] - 2026-01-13

### Changed
- Web UI now auto-detects container hostname for Rental Control URL
- Displays correct `{addon-id}-track-to-ics:8443` format automatically

## [1.0.5] - 2026-01-13

### Added
- Dual server setup: HTTP (8099) for ingress, HTTPS (8443) for Rental Control
- Self-signed SSL certificate generation on startup

### Fixed
- Ingress "Bad Gateway" error by separating HTTP and HTTPS servers

## [1.0.4] - 2026-01-13

### Added
- HTTPS support with self-signed SSL certificate
- OpenSSL dependency for certificate generation

## [1.0.3] - 2026-01-13

### Added
- Auto-detect calendar URL based on current page location
- Copy URL button with visual feedback
- Separate sections for Rental Control URL and browser access URL

## [1.0.2] - 2026-01-13

### Fixed
- Use relative URLs for ingress compatibility
- Links now work correctly when accessed via Home Assistant ingress

## [1.0.1] - 2026-01-13

### Fixed
- GitHub username in repository URLs

## [1.0.0] - 2026-01-13

### Added
- Initial release
- Downloads reservations from Track Property Management
- Converts CSV export to ICS calendar format
- Serves calendar via HTTP on port 8099
- Compatible with Rental Control HACS integration
- Configurable check-in/check-out times
- Configurable timezone support
- Automatic refresh at configurable intervals
- Option to include/exclude owner stays
- Option to include/exclude past reservations
- Web interface for status and manual refresh
- Filter support for reservation status (Confirmed, Checked In)
- Filter support for reservation types (Airbnb, VRBO, Owner Stay, etc.)
