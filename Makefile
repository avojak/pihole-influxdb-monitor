.PHONY: image
image:
	docker build . -t avojak/pihole-influxdb

.PHONY: lint
lint:
	pylint pihole_influxdb.py
	hadolint Dockerfile

all: image