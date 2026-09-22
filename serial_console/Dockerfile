FROM alpine:3.23.6

# Keep the maintained Alpine branch for security revisions. Application version
# constraints prevent a silent major/minor upgrade; CI tests the resolved packages.
RUN apk add --no-cache \
      ca-certificates python3 tini socat \
      'ser2net~4.6.4' 'ttyd~1.7.7' \
    && mkdir -p /app /run/serial-console /run/lock

COPY run.sh /app/run.sh
COPY app.py /app/app.py
RUN chmod 0755 /app/run.sh

LABEL io.hass.name="Serial Console" \
      io.hass.description="ser2net serial console with authenticated ttyd" \
      io.hass.type="addon" \
      io.hass.version="1.0.0" \
      org.opencontainers.image.title="Serial Console" \
      org.opencontainers.image.licenses="MIT"

EXPOSE 7681 2000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python3", "/app/app.py", "--healthcheck"]
ENTRYPOINT ["/sbin/tini", "--", "/app/run.sh"]
