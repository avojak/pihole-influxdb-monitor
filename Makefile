.PHONY: image
image:
	docker build . -t avojak/pihole-influxdb

all: image