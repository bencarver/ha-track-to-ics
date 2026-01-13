#!/usr/bin/env python3
"""
Track to ICS Calendar Add-on for Home Assistant

Downloads reservations from Track Property Management and serves them as an ICS calendar
compatible with the Rental Control HACS integration.
"""

import os
import csv
import logging
from datetime import datetime, timedelta
from io import StringIO
from threading import Thread
from uuid import uuid4

import pytz
import requests
from flask import Flask, Response, render_template_string
from icalendar import Calendar, Event
from apscheduler.schedulers.background import BackgroundScheduler
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask application
app = Flask(__name__)

# Global calendar storage
current_calendar_ics = None
last_update = None
last_error = None
reservation_count = 0

# Configuration from environment
CONFIG = {
    'track_username': os.environ.get('TRACK_USERNAME', ''),
    'track_password': os.environ.get('TRACK_PASSWORD', ''),
    'track_base_url': os.environ.get('TRACK_BASE_URL', 'https://fivestarproperty.trackhs.com'),
    'export_path': os.environ.get('EXPORT_PATH', '/owner/reservations/generate-csv/'),
    'refresh_interval': int(os.environ.get('REFRESH_INTERVAL', 30)),
    'checkin_time': os.environ.get('CHECKIN_TIME', '16:00'),
    'checkout_time': os.environ.get('CHECKOUT_TIME', '11:00'),
    'timezone': os.environ.get('TIMEZONE', 'America/Denver'),
    'include_owner_stays': os.environ.get('INCLUDE_OWNER_STAYS', 'false').lower() == 'true',
    'include_past_reservations': os.environ.get('INCLUDE_PAST_RESERVATIONS', 'false').lower() == 'true',
}


class TrackClient:
    """Client for interacting with Track Property Management system."""
    
    def __init__(self, base_url: str, username: str, password: str, export_path: str = '/owner/reservations/generate-csv/'):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.export_path = export_path.strip() if export_path else '/owner/reservations/generate-csv/'
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        })
        self._logged_in = False
    
    def login(self) -> bool:
        """Authenticate with Track Owner Portal."""
        try:
            # Track's owner portal login page
            login_page_url = f"{self.base_url}/owner/"
            logger.info(f"Fetching login page: {login_page_url}")
            
            response = self.session.get(login_page_url)
            response.raise_for_status()
            
            # Parse for the security token
            soup = BeautifulSoup(response.text, 'lxml')
            
            # Build login payload - Track uses 'username', 'password', and 'security' fields
            login_data = {
                'username': self.username,
                'password': self.password,
            }
            
            # Look for the security token (Track's CSRF protection)
            security_input = soup.find('input', {'name': 'security'})
            if security_input:
                login_data['security'] = security_input.get('value', '')
                logger.info("Found security token")
            else:
                logger.warning("Security token not found on login page")
            
            # Submit login to the same URL
            logger.info("Submitting login credentials...")
            login_response = self.session.post(
                login_page_url,
                data=login_data,
                allow_redirects=True
            )
            
            # Check if login was successful
            # Successful login redirects to /owner/dashboard/ or similar
            # Failed login stays on /owner/ with the login form
            final_url = login_response.url.lower()
            
            # Check for successful redirect (dashboard, reservations, etc.)
            if 'dashboard' in final_url or 'reservations' in final_url or 'availability' in final_url:
                self._logged_in = True
                logger.info(f"Login successful! Redirected to: {login_response.url}")
                return True
            
            # Check if we're still on the login page (look for the login form)
            if 'Owner Connect Login' in login_response.text or 'name="security"' in login_response.text:
                logger.error("Login failed - still on login page. Check credentials.")
                return False
            
            # If we're somewhere else in /owner/, assume success
            if '/owner/' in final_url and final_url != login_page_url.lower():
                self._logged_in = True
                logger.info(f"Login appears successful. Current page: {login_response.url}")
                return True
                
            logger.error(f"Login status unclear. Final URL: {login_response.url}")
            return False
                
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False
    
    def download_reservations_csv(self) -> str:
        """Download the reservations CSV export via POST request."""
        if not self._logged_in:
            if not self.login():
                raise Exception("Failed to authenticate with Track")
        
        # Track uses POST to /owner/reservations/generate-csv/
        export_url = f"{self.base_url}{self.export_path if self.export_path.startswith('/') else '/' + self.export_path}"
        
        logger.info(f"Downloading CSV from: {export_url}")
        
        # POST request with empty form data to get all reservations
        # Optional parameters: startDate, endDate, unit
        try:
            response = self.session.post(
                export_url,
                data={},  # Empty = all reservations
                allow_redirects=True
            )
            
            # Check if we got a CSV response
            content_type = response.headers.get('Content-Type', '')
            content_disp = response.headers.get('Content-Disposition', '')
            
            # Log response details for debugging
            logger.debug(f"Response status: {response.status_code}")
            logger.debug(f"Content-Type: {content_type}")
            logger.debug(f"Content-Disposition: {content_disp}")
            
            # Check various indicators of CSV content
            is_csv = (
                'csv' in content_type.lower() or
                'csv' in content_disp.lower() or
                response.text.strip().startswith('"Reservation Id"') or
                'Reservation Id' in response.text.split('\n')[0] if response.text else False
            )
            
            if is_csv and len(response.text) > 50:
                logger.info(f"Successfully downloaded CSV")
                logger.info(f"CSV size: {len(response.text)} bytes")
                # Log first line to verify format
                first_line = response.text.split('\n')[0] if response.text else ''
                logger.debug(f"CSV header: {first_line[:100]}...")
                return response.text
            
            # If not CSV, we might have been redirected to login
            if 'Owner Connect Login' in response.text or 'name="security"' in response.text:
                logger.error("Session expired - redirected to login page")
                self._logged_in = False
                raise Exception("Session expired. Please try again.")
            
            # Log what we got for debugging
            logger.error(f"Did not receive CSV data. Content-Type: {content_type}")
            logger.debug(f"Response preview: {response.text[:500] if response.text else 'Empty'}...")
            raise Exception(f"Export did not return CSV data. Got Content-Type: {content_type}")
                
        except requests.RequestException as e:
            logger.error(f"HTTP error during CSV download: {e}")
            raise Exception(f"Failed to download CSV: {e}")


def parse_track_csv(csv_content: str) -> list:
    """
    Parse the Track CSV export into a list of reservation dictionaries.
    
    Expected columns:
    "Reservation Id",Status,Type,Unit,Guest,"Booked Date",Check-In,Checkout,Nights,Income,Currency
    """
    reservations = []
    
    reader = csv.DictReader(StringIO(csv_content))
    
    if reader.fieldnames:
        logger.info(f"CSV Headers: {reader.fieldnames}")
    
    today = datetime.now().date()
    
    for row in reader:
        try:
            # Extract fields with exact column names from Track
            reservation = {
                'reservation_id': row.get('Reservation Id', '').strip(),
                'status': row.get('Status', '').strip(),
                'type': row.get('Type', '').strip(),
                'unit': row.get('Unit', '').strip(),
                'guest_name': row.get('Guest', '').strip(),
                'booked_date': row.get('Booked Date', '').strip(),
                'checkin_date': row.get('Check-In', '').strip(),
                'checkout_date': row.get('Checkout', '').strip(),
                'nights': row.get('Nights', '').strip(),
                'income': row.get('Income', '').strip(),
                'currency': row.get('Currency', 'USD').strip(),
            }
            
            # Skip if no dates
            if not reservation['checkin_date'] or not reservation['checkout_date']:
                logger.warning(f"Skipping reservation {reservation['reservation_id']}: missing dates")
                continue
            
            # Parse checkout date to check if past
            try:
                checkout_date = datetime.strptime(reservation['checkout_date'], '%Y-%m-%d').date()
            except ValueError:
                logger.warning(f"Skipping reservation {reservation['reservation_id']}: invalid date format")
                continue
            
            # Filter out past reservations unless configured to include them
            if not CONFIG['include_past_reservations']:
                if checkout_date < today:
                    logger.debug(f"Skipping past reservation: {reservation['guest_name']} (checkout: {checkout_date})")
                    continue
            
            # Filter out "Checked Out" status
            if reservation['status'] == 'Checked Out':
                logger.debug(f"Skipping checked out reservation: {reservation['guest_name']}")
                continue
            
            # Filter owner stays unless configured to include them
            if not CONFIG['include_owner_stays']:
                res_type = reservation['type'].lower()
                if 'owner stay' in res_type or 'guest of owner' in res_type:
                    logger.debug(f"Skipping owner stay: {reservation['guest_name']}")
                    continue
            
            reservations.append(reservation)
            logger.debug(f"Added reservation: {reservation['guest_name']} ({reservation['checkin_date']} - {reservation['checkout_date']})")
            
        except Exception as e:
            logger.warning(f"Error parsing row: {e}")
            continue
    
    # Sort by check-in date
    reservations.sort(key=lambda x: x['checkin_date'])
    
    logger.info(f"Parsed {len(reservations)} active reservations from CSV")
    return reservations


def create_ics_calendar(reservations: list, checkin_time: str, checkout_time: str, timezone_str: str) -> str:
    """
    Create an ICS calendar from reservations.
    
    The format is designed to be compatible with the Rental Control HACS integration.
    """
    cal = Calendar()
    cal.add('prodid', '-//Track to ICS Calendar//Home Assistant Add-on//EN')
    cal.add('version', '2.0')
    cal.add('calscale', 'GREGORIAN')
    cal.add('method', 'PUBLISH')
    cal.add('x-wr-calname', 'Track Reservations')
    cal.add('x-wr-timezone', timezone_str)
    
    tz = pytz.timezone(timezone_str)
    
    # Parse checkin/checkout times
    checkin_hour, checkin_minute = map(int, checkin_time.split(':'))
    checkout_hour, checkout_minute = map(int, checkout_time.split(':'))
    
    for res in reservations:
        try:
            event = Event()
            
            # Parse dates (Track uses YYYY-MM-DD format)
            checkin_date = datetime.strptime(res['checkin_date'], '%Y-%m-%d')
            checkout_date = datetime.strptime(res['checkout_date'], '%Y-%m-%d')
            
            # Create datetime with times
            checkin_dt = tz.localize(checkin_date.replace(hour=checkin_hour, minute=checkin_minute))
            checkout_dt = tz.localize(checkout_date.replace(hour=checkout_hour, minute=checkout_minute))
            
            # Event summary (guest name)
            # Clean up guest name - Track uses "F. Lastname" format
            guest_name = res['guest_name'].strip() or 'Reserved'
            event.add('summary', guest_name)
            
            # Start and end times
            event.add('dtstart', checkin_dt)
            event.add('dtend', checkout_dt)
            
            # Build description with Rental Control compatible format
            description_parts = []
            
            # Add reservation type/source
            if res.get('type'):
                description_parts.append(f"Source: {res['type']}")
            
            # Add property/unit info
            if res.get('unit'):
                description_parts.append(f"Property: {res['unit']}")
            
            # Add number of nights as guests info (since we don't have actual guest count)
            if res.get('nights'):
                description_parts.append(f"Nights: {res['nights']}")
            
            # Add confirmation/reservation ID
            if res.get('reservation_id'):
                conf = res['reservation_id']
                description_parts.append(f"Confirmation: {conf}")
                # Add URL for Rental Control to pick up
                description_parts.append(f"{CONFIG['track_base_url']}/owner/reservations/{conf}")
            
            # Add income if available and non-zero
            if res.get('income') and float(res.get('income', 0)) > 0:
                description_parts.append(f"Income: ${res['income']} {res.get('currency', 'USD')}")
            
            event.add('description', '\n'.join(description_parts))
            
            # Generate a unique ID for the event
            uid = f"track-{res.get('reservation_id', uuid4())}-{checkin_date.strftime('%Y%m%d')}@track-to-ics"
            event.add('uid', uid)
            
            # Add timestamp
            event.add('dtstamp', datetime.now(tz))
            
            # Add location (property)
            if res.get('unit'):
                event.add('location', res['unit'])
            
            cal.add_component(event)
            logger.debug(f"Added event: {guest_name} ({checkin_date.date()} - {checkout_date.date()})")
            
        except Exception as e:
            logger.error(f"Error creating event for {res.get('guest_name', 'Unknown')}: {e}")
            continue
    
    return cal.to_ical().decode('utf-8')


def refresh_calendar():
    """Refresh the calendar data from Track."""
    global current_calendar_ics, last_update, last_error, reservation_count
    
    logger.info("Refreshing calendar from Track...")
    
    try:
        # Create client and download CSV
        client = TrackClient(
            CONFIG['track_base_url'],
            CONFIG['track_username'],
            CONFIG['track_password'],
            CONFIG['export_path']
        )
        
        csv_content = client.download_reservations_csv()
        
        # Parse CSV
        reservations = parse_track_csv(csv_content)
        reservation_count = len(reservations)
        
        # Create ICS
        current_calendar_ics = create_ics_calendar(
            reservations,
            CONFIG['checkin_time'],
            CONFIG['checkout_time'],
            CONFIG['timezone']
        )
        
        last_update = datetime.now()
        last_error = None
        
        logger.info(f"Calendar refreshed successfully with {reservation_count} reservations")
        
    except Exception as e:
        last_error = str(e)
        logger.error(f"Error refreshing calendar: {e}")


# Flask routes
@app.route('/')
def index():
    """Status page."""
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Track to ICS Calendar</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { box-sizing: border-box; }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
                max-width: 900px;
                margin: 0 auto;
                padding: 20px;
                background: #1a1a2e;
                color: #eee;
            }
            .card {
                background: #16213e;
                border-radius: 12px;
                padding: 24px;
                margin-bottom: 20px;
                box-shadow: 0 4px 6px rgba(0,0,0,0.3);
            }
            h1 { 
                color: #4cc9f0; 
                margin-top: 0;
                display: flex;
                align-items: center;
                gap: 12px;
            }
            h1::before {
                content: "📅";
                font-size: 1.2em;
            }
            h2 { 
                color: #7b2cbf; 
                border-bottom: 2px solid #7b2cbf;
                padding-bottom: 8px;
            }
            .status { 
                padding: 16px; 
                border-radius: 8px; 
                margin: 10px 0;
                display: flex;
                align-items: center;
                gap: 12px;
            }
            .status.ok { background: #1b4332; color: #95d5b2; }
            .status.error { background: #4a1515; color: #f8a5a5; }
            .status.pending { background: #3d3d00; color: #ffeb99; }
            .url-box {
                background: #0f3460;
                padding: 16px;
                border-radius: 8px;
                font-family: 'Monaco', 'Menlo', monospace;
                word-break: break-all;
                font-size: 14px;
                border: 1px solid #4cc9f0;
            }
            code { 
                background: #0f3460; 
                padding: 3px 8px; 
                border-radius: 4px;
                font-size: 13px;
            }
            .btn {
                display: inline-block;
                padding: 12px 24px;
                background: #7b2cbf;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                margin: 8px 8px 8px 0;
                transition: background 0.2s;
            }
            .btn:hover { background: #9d4edd; }
            .btn.secondary { background: #4361ee; }
            .btn.secondary:hover { background: #4895ef; }
            .stats {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 16px;
                margin-top: 16px;
            }
            .stat {
                background: #0f3460;
                padding: 16px;
                border-radius: 8px;
                text-align: center;
            }
            .stat-value {
                font-size: 2em;
                font-weight: bold;
                color: #4cc9f0;
            }
            .stat-label {
                font-size: 0.85em;
                color: #aaa;
                margin-top: 4px;
            }
            .config-table {
                width: 100%;
                border-collapse: collapse;
            }
            .config-table td {
                padding: 8px;
                border-bottom: 1px solid #333;
            }
            .config-table td:first-child {
                color: #aaa;
                width: 40%;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Track to ICS Calendar</h1>
            <p>This add-on downloads reservations from Track Property Management and serves them as an ICS calendar for the Rental Control integration.</p>
        </div>
        
        <div class="card">
            <h2>Status</h2>
            {% if last_error %}
            <div class="status error">
                <span style="font-size: 1.5em">❌</span>
                <div>
                    <strong>Error</strong><br>
                    {{ last_error }}
                </div>
            </div>
            {% elif last_update %}
            <div class="status ok">
                <span style="font-size: 1.5em">✅</span>
                <div>
                    <strong>Healthy</strong><br>
                    Last updated: {{ last_update }}
                </div>
            </div>
            {% else %}
            <div class="status pending">
                <span style="font-size: 1.5em">⏳</span>
                <div>
                    <strong>Pending</strong><br>
                    Calendar not yet loaded
                </div>
            </div>
            {% endif %}
            
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{{ reservation_count }}</div>
                    <div class="stat-label">Active Reservations</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{{ refresh_interval }}m</div>
                    <div class="stat-label">Refresh Interval</div>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>Calendar URL for Rental Control</h2>
            <p><strong>Use this URL in the Rental Control integration:</strong></p>
            <div class="url-box" id="local-url" onclick="copyLocalUrl()" style="cursor: pointer;" title="Click to copy">
                https://local-track-to-ics:8443/calendar.ics
            </div>
            <p style="margin-top: 12px;">
                <button onclick="copyLocalUrl()" class="btn" style="padding: 8px 16px; font-size: 14px;">📋 Copy URL for Rental Control</button>
                <span id="copy-local-status" style="margin-left: 10px; color: #95d5b2; display: none;">✓ Copied!</span>
            </p>
            <p style="margin-top: 8px; color: #aaa; font-size: 13px;">
                ℹ️ HTTPS on port 8443 with self-signed certificate. Alternative hostnames:<br>
                <code style="font-size: 11px;">local-track-to-ics</code> · 
                <code style="font-size: 11px;">track_to_ics</code> · 
                <code style="font-size: 11px;">homeassistant.local</code>
            </p>
            
            <h3 style="margin-top: 24px; color: #7b2cbf; font-size: 16px;">Remote Browser Access</h3>
            <p style="font-size: 14px;">For viewing this page remotely (your current URL):</p>
            <div class="url-box" id="calendar-url" onclick="copyUrl()" style="cursor: pointer; font-size: 12px;" title="Click to copy">
                Loading...
            </div>
            <p style="margin-top: 8px;">
                <button onclick="copyUrl()" class="btn secondary" style="padding: 6px 12px; font-size: 12px;">📋 Copy Browser URL</button>
                <span id="copy-status" style="margin-left: 10px; color: #95d5b2; display: none;">✓ Copied!</span>
            </p>
            <script>
                function getCalendarUrl() {
                    return window.location.href.replace(/\/$/, '').replace(/\/+$/, '') + '/calendar.ics';
                }
                document.getElementById('calendar-url').textContent = getCalendarUrl();
                
                function copyUrl() {
                    const url = getCalendarUrl();
                    navigator.clipboard.writeText(url).then(function() {
                        const status = document.getElementById('copy-status');
                        status.style.display = 'inline';
                        setTimeout(function() { status.style.display = 'none'; }, 2000);
                    });
                }
                
                function copyLocalUrl() {
                    const url = 'https://local-track-to-ics:8443/calendar.ics';
                    navigator.clipboard.writeText(url).then(function() {
                        const status = document.getElementById('copy-local-status');
                        status.style.display = 'inline';
                        setTimeout(function() { status.style.display = 'none'; }, 2000);
                    });
                }
            </script>
        </div>
        
        <div class="card">
            <h2>Actions</h2>
            <a href="calendar.ics" class="btn">📥 Download Calendar</a>
            <a href="refresh" class="btn secondary">🔄 Force Refresh</a>
        </div>
        
        <div class="card">
            <h2>Configuration</h2>
            <table class="config-table">
                <tr><td>Track URL</td><td>{{ track_url }}</td></tr>
                <tr><td>Timezone</td><td>{{ timezone }}</td></tr>
                <tr><td>Check-in Time</td><td>{{ checkin_time }}</td></tr>
                <tr><td>Check-out Time</td><td>{{ checkout_time }}</td></tr>
                <tr><td>Include Owner Stays</td><td>{{ include_owner_stays }}</td></tr>
                <tr><td>Include Past Reservations</td><td>{{ include_past }}</td></tr>
            </table>
        </div>
    </body>
    </html>
    """
    return render_template_string(
        html, 
        last_update=last_update.strftime('%Y-%m-%d %H:%M:%S') if last_update else None,
        last_error=last_error,
        reservation_count=reservation_count,
        refresh_interval=CONFIG['refresh_interval'],
        track_url=CONFIG['track_base_url'],
        timezone=CONFIG['timezone'],
        checkin_time=CONFIG['checkin_time'],
        checkout_time=CONFIG['checkout_time'],
        include_owner_stays='Yes' if CONFIG['include_owner_stays'] else 'No',
        include_past='Yes' if CONFIG['include_past_reservations'] else 'No',
    )


@app.route('/calendar.ics')
def get_calendar():
    """Serve the ICS calendar file."""
    if current_calendar_ics:
        return Response(
            current_calendar_ics,
            mimetype='text/calendar',
            headers={
                'Content-Disposition': 'attachment; filename=calendar.ics',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache',
                'Expires': '0',
            }
        )
    else:
        return Response(
            "Calendar not yet loaded. Please wait for the first refresh or check the logs.",
            status=503
        )


@app.route('/refresh')
def force_refresh():
    """Force a calendar refresh."""
    refresh_calendar()
    if last_error:
        return f"""
        <html>
        <head><meta http-equiv="refresh" content="3;url=."></head>
        <body style="font-family: sans-serif; padding: 20px; background: #4a1515; color: #f8a5a5;">
        <h2>❌ Refresh Failed</h2>
        <p>{last_error}</p>
        <p>Redirecting in 3 seconds... <a href="." style="color: white;">Go back now</a></p>
        </body></html>
        """
    return f"""
    <html>
    <head><meta http-equiv="refresh" content="2;url=."></head>
    <body style="font-family: sans-serif; padding: 20px; background: #1b4332; color: #95d5b2;">
    <h2>✅ Calendar Refreshed</h2>
    <p>Found {reservation_count} active reservations.</p>
    <p>Redirecting in 2 seconds... <a href="." style="color: white;">Go back now</a></p>
    </body></html>
    """


@app.route('/health')
def health():
    """Health check endpoint."""
    return {
        'status': 'ok' if not last_error else 'error',
        'last_update': str(last_update) if last_update else None,
        'reservation_count': reservation_count,
        'error': last_error,
    }


def main():
    """Main entry point."""
    logger.info("=" * 60)
    logger.info("Starting Track to ICS Calendar Add-on")
    logger.info("=" * 60)
    logger.info(f"Track URL: {CONFIG['track_base_url']}")
    logger.info(f"Timezone: {CONFIG['timezone']}")
    logger.info(f"Check-in time: {CONFIG['checkin_time']}")
    logger.info(f"Check-out time: {CONFIG['checkout_time']}")
    logger.info(f"Refresh interval: {CONFIG['refresh_interval']} minutes")
    logger.info(f"Include owner stays: {CONFIG['include_owner_stays']}")
    logger.info(f"Include past reservations: {CONFIG['include_past_reservations']}")
    
    # Validate configuration
    if not CONFIG['track_username'] or not CONFIG['track_password']:
        logger.warning("⚠️  Track credentials not configured. Please configure the add-on.")
    else:
        # Initial refresh
        refresh_calendar()
    
    # Set up scheduled refresh
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        refresh_calendar,
        'interval',
        minutes=CONFIG['refresh_interval'],
        id='refresh_calendar'
    )
    scheduler.start()
    logger.info(f"Scheduled refresh every {CONFIG['refresh_interval']} minutes")
    
    # Generate SSL certificate if needed
    cert_dir = '/ssl'
    cert_file = f'{cert_dir}/cert.pem'
    key_file = f'{cert_dir}/key.pem'
    
    import os
    import subprocess
    from threading import Thread
    
    if not os.path.exists(cert_dir):
        os.makedirs(cert_dir)
    
    if not os.path.exists(cert_file) or not os.path.exists(key_file):
        logger.info("Generating self-signed SSL certificate...")
        try:
            subprocess.run([
                'openssl', 'req', '-x509', '-newkey', 'rsa:2048',
                '-keyout', key_file, '-out', cert_file,
                '-days', '365', '-nodes',
                '-subj', '/CN=track-to-ics/O=HomeAssistant/C=US'
            ], check=True, capture_output=True)
            logger.info("SSL certificate generated successfully")
        except Exception as e:
            logger.error(f"Failed to generate SSL certificate: {e}")
            cert_file = None
            key_file = None
    
    # Start HTTPS server on port 8443 in a separate thread
    if cert_file and key_file and os.path.exists(cert_file):
        def run_https():
            logger.info("Starting HTTPS server on port 8443...")
            app.run(host='0.0.0.0', port=8443, debug=False, threaded=True,
                    ssl_context=(cert_file, key_file), use_reloader=False)
        
        https_thread = Thread(target=run_https, daemon=True)
        https_thread.start()
        logger.info("HTTPS server started on port 8443 (for Rental Control)")
    
    # Start HTTP server on port 8099 (for ingress)
    logger.info("Starting HTTP server on port 8099 (for ingress)...")
    app.run(host='0.0.0.0', port=8099, debug=False, threaded=True)


if __name__ == '__main__':
    main()
