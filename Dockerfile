FROM python:3-alpine AS builder
COPY requirements.txt /
RUN python3 -m pip install --user -r requirements.txt

FROM python:3-alpine
COPY --from=builder /root/.local /root/.local
COPY pihole-influxdb.py /
ENTRYPOINT [ "python", "/pihole-influxdb.py" ]