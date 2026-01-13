ARG BUILD_FROM
FROM $BUILD_FROM

# Install Python and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    tzdata

# Set working directory
WORKDIR /app

# Copy Python application
COPY app/ /app/

# Install Python dependencies
RUN pip3 install --no-cache-dir --break-system-packages \
    flask \
    icalendar \
    pytz \
    requests \
    beautifulsoup4 \
    lxml \
    apscheduler

# Copy run script
COPY run.sh /run.sh

# Make scripts executable
RUN chmod a+x /run.sh

# Expose port
EXPOSE 8099

CMD [ "/run.sh" ]
