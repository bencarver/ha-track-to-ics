#!/usr/bin/with-contenv bashio

# Read configuration from Home Assistant
export TRACK_USERNAME=$(bashio::config 'track_username')
export TRACK_PASSWORD=$(bashio::config 'track_password')
export TRACK_BASE_URL=$(bashio::config 'track_base_url')
export EXPORT_PATH=$(bashio::config 'export_path')
export REFRESH_INTERVAL=$(bashio::config 'refresh_interval_minutes')
export CHECKIN_TIME=$(bashio::config 'checkin_time')
export CHECKOUT_TIME=$(bashio::config 'checkout_time')
export TIMEZONE=$(bashio::config 'timezone')
export INCLUDE_OWNER_STAYS=$(bashio::config 'include_owner_stays')
export INCLUDE_PAST_RESERVATIONS=$(bashio::config 'include_past_reservations')
export NOTIFY_ON_ERROR=$(bashio::config 'notify_on_error')
export NOTIFY_COOLDOWN_MINUTES=$(bashio::config 'notify_cooldown_minutes')

bashio::log.info "============================================="
bashio::log.info "Starting Track to ICS Calendar Add-on"
bashio::log.info "============================================="
bashio::log.info "Track URL: ${TRACK_BASE_URL}"
bashio::log.info "Refresh interval: ${REFRESH_INTERVAL} minutes"
bashio::log.info "Timezone: ${TIMEZONE}"
bashio::log.info "Check-in time: ${CHECKIN_TIME}"
bashio::log.info "Check-out time: ${CHECKOUT_TIME}"
bashio::log.info "Include owner stays: ${INCLUDE_OWNER_STAYS}"
bashio::log.info "Include past reservations: ${INCLUDE_PAST_RESERVATIONS}"

# Run the Python application
exec python3 /app/main.py
