FROM python:3-alpine AS builder
COPY requirements.txt /
RUN python3 -m pip install --no-cache-dir --user -r requirements.txt

FROM python:3-alpine
LABEL org.opencontainers.image.authors="Andrew Vojak"
LABEL org.opencontainers.image.licenses="MIT"
LABEL org.opencontainers.image.source="https://github.com/avojak/pihole-influxdb"
LABEL org.opencontainers.image.title="pihole-influxdb"
LABEL org.opencontainers.image.description="Export Pi-hole statistics to InfluxDB 2.x"
COPY --from=builder /root/.local /root/.local
COPY pihole_influxdb.py /
ENTRYPOINT [ "python", "/pihole_influxdb.py" ]