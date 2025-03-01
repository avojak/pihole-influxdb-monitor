.PHONY: image
image:
	docker build . -t avojak/pihole-influxdb

.PHONY: lint
lint:
	pylint pihole-influxdb.py

all: image