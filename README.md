![CI](https://github.com/avojak/pihole-influxdb/workflows/CI/badge.svg)
![GitHub](https://img.shields.io/github/license/avojak/pihole-influxdb)
![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/avojak/pihole-influxdb?sort=semver)
![Docker Pulls](https://img.shields.io/docker/pulls/avojak/pihole-influxdb)
![Image Size](https://img.shields.io/docker/image-size/avojak/pihole-influxdb/latest)

# Pi-hole InfluxDB Monitor

Export Pi-hole statistics to InfluxDB 2.x.

## Environment Variables

| Name | Description | Default |
| ---- | ----------- | ------- |
| `INTERVAL_SECONDS` | Interval (in seconds) between polling | `60` |
| `PIHOLE_ALIAS` | Comma-separated list of aliases for the Pi-hole instances | `pihole` |
| `PIHOLE_ADDRESS` | Comma-separated list of Pi-hole adddresses to poll | `http://pi.hole:80` |
| `PIHOLE_TOKEN` | Comma-separated list of Pi-hole API tokens* |  |
| `PIHOLE_NUM_TOP_ITEMS` | Number of top domains and ads to return | `10` |
| `PIHOLE_NUM_TOP_CLIENTS` | Number of top clients to return | `10` |
| `INFLUXDB_ADDRESS` | Address of the InfluxDB instance | `http://influxdb:8086` |
| `INFLUXDB_ORG` | InfluxDB organization | `my-org` |
| `INFLUXDB_TOKEN` | InfluxDB auth token |  |
| `INFLUXDB_BUCKET` | InfluxDB bucket for storing the data | `pihole` |
| `INFLUXDB_CREATE_BUCKET` | Whether or not to create the InfluxDB bucket if it does not already exist | `False` |
| `INFLUXDB_VERIFY_SSL` | Whether or not to verify the InfluxDB SSL certificate (only applicable when using an HTTPS address) | `True` |

\* *Note: only required to retrieve data on top DNS queries, clients, etc.*

## Docker

```bash
docker run -d \
    -e PIHOLE_ALIAS="pihole" \
    -e PIHOLE_ADDRESS="http://pi.hole" \
    -e PIHOLE_TOKEN="pihole_api_token" \
    -e PIHOLE_NUM_TOP_ITEMS=25 \
    -e PIHOLE_NUM_TOP_CLIENTS=25 \
    -e INFLUXDB_ADDRESS="http://influxdb:8086" \
    -e INFLUXDB_ORG="my-org" \
    -e INFLUXDB_TOKEN="super_secret_token" \
    -e INFLUXDB_BUCKET="pihole" \
    avojak/pihole-influxdb:latest
```

## Docker Compose

```yaml
version: "3.9"
services:
  pihole-influxdb:
    image: avojak/pihole-influxdb:latest
    container_name: pihole-influxdb
    restart: unless-stopped
    environment:
      - "PIHOLE_ALIAS=pihole"
      - "PIHOLE_ADDRESS=http://pi.hole"
      - "PIHOLE_TOKEN=pihole_api_token"
      - "PIHOLE_NUM_TOP_ITEMS=25"
      - "PIHOLE_NUM_TOP_CLIENTS=25"
      - "INFLUXDB_ADDRESS=http://influxdb:8086"
      - "INFLUXDB_ORG=my-org"
      - "INFLUXDB_TOKEN=super_secret_token"
      - "INFLUXDB_BUCKET=pihole"
```

## Command Line

```bash
python3 pihole-influxdb.py \
    --pihole-alias "pihole" \
    --pihole-address "http://pi.hole" \
    --pihole-token "pihole_api_token" \
    --pihole-num-top-items 25 \
    --pihole-num-top-clients 25 \
    --influxdb-address "http://influxdb:8096" \
    --influxdb-org "my-org" \
    --influxdb-token "super_secret_token" \
    --influxdb-bucket "pihole"
```

## Screenshots

Simple dashboard in Grafana (See: [grafana/Pi-hole.json](grafana/Pi-hole.json)):

![Dashboard](screenshots/dashboard.png)

## References

Rough API documentation for the Pi-hole API is available here: https://discourse.pi-hole.net/t/pi-hole-api/1863