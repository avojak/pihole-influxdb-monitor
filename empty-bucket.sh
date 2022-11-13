#!/bin/sh

#
# Utility script for testing to empty the content of the Pi-hole bucket
#

source test.env

curl -X POST "$INFLUXDB_ADDRESS/api/v2/delete?org=$INFLUXDB_ORG&bucket=$INFLUXDB_BUCKET" \
  --header "Authorization: Token $INFLUXDB_TOKEN" \
  --header 'Content-Type: application/json' \
  --data '{
    "start": "1970-01-01T00:00:00Z",
    "stop": "2262-04-11T23:47:16Z"
  }'