To spin up the test environment:

```shell
docker compose up -d
docker compose logs -f pihole-influxdb-monitor
docker compose down
```

If you make a code change and want to ensure that your changes are reflected, you can force a rebuild of the container image:

```shell
docker compose up --build --force-recreate -d
```

The following services are created:

| Service  | URL | Username | Password | API Token |
| -------- | --- | -------- | -------- | --------- |
| Pi-hole  | http://localhost:8080/admin | | `password123` | `25aa34070a75ce79dcf2496484ad2301de3daa2b80581c9b265eaadb79685303` |
| InfluxDB | http://localhost:8086 | admin | `password123` | `admintoken123` |
| Grafana  | http://localhost:3000/d/zLZsJ9v4k/pi-hole?from=now-3h&to=now&var-alias=pihole | admin | `password123` | |
| Pi-hole InfluxDB Monitor | | | | |
| Traffic Generator | | | | |