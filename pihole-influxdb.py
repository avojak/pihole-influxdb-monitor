# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: 2025 Andrew Vojak <andrew.vojak@gmail.com>

#!/usr/bin/env python3

"""
Pi-hole InfluxDB Monitor

Export Pi-hole statistics to InfluxDB 2.x
"""

import argparse
import logging
import os
import signal
import time
from datetime import datetime
from itertools import zip_longest
from urllib.parse import urlparse

import requests
import schedule
from influxdb_client import InfluxDBClient, Point, BucketRetentionRules
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.domain.write_precision import WritePrecision


DEFAULT_INTERVAL_SECONDS = 60

DEFAULT_PIHOLE_ALIAS = 'pihole'
DEFAULT_PIHOLE_ADDRESS = 'http://pi.hole:80'
DEFAULT_PIHOLE_PASSWORD = None

DEFAULT_PIHOLE_NUM_TOP_ITEMS = 10
DEFAULT_PIHOLE_NUM_TOP_CLIENTS = 10

DEFAULT_INFLUXDB_ADDRESS = 'http://influxdb:8086'
DEFAULT_INFLUXDB_ORG = 'my-org'
DEFAULT_INFLUXDB_TOKEN = None
DEFAULT_INFLUXDB_BUCKET = 'pihole'
DEFAULT_INFLUXDB_CREATE_BUCKET = False
DEFAULT_INFLUXDB_VERIFY_SSL = True

DEBUG = False

class Pihole():
    """
    Class to contain the configuration, and provide the ability to interface with, a Pi-hole instance.
    """

    def __init__(self, alias, address, request_timeout, password=None, sid=None):
        self.alias = alias
        self.address = address
        self.request_timeout = request_timeout
        self.password = password
        self.sid = sid

    def print_config(self):
        """
        Return the Pi-hole configuration as a string.
        """
        return f'{self.alias} {self.address} ' + ('(Authenticated)' if self.sid else '(Not authenticated)')

    def _get_api_url(self, endpoint, query=None):
        """
        Get the URL for the Pi-hole API with an optional query element.
        """
        url = f'{self.address}/api{endpoint}'
        query_data = []
        if query:
            query_data.append(query)
        if len(query_data) > 0:
            url = f'{url}?{"&".join(query_data)}'
        return url

    def _api_call(self, endpoint, method='GET', query=None, json_data=None):
        """
        Execute an API request against the Pi-hole.
        """
        url = self._get_api_url(endpoint, query)
        try:
            headers = {}
            if self.sid is not None:
                headers = {
                    'X-FTL-SID': self.sid
                }
            timeout = self.request_timeout
            response = requests.request(method, url, json=json_data, timeout=timeout, headers=headers)
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            logging.error(f'[{self.alias}] [HTTP {response.status_code}] Error executing request to {url}: {e}')
            if response.status_code >= 400 and response.status_code < 500:
                error_response = response.json()
                if 'error' in error_response:
                    error = error_response['error']
                    hint = "(Hint: " + error["hint"] + ")" if "hint" in error else "none"
                    logging.error(f'[{self.alias}] [{error["key"]}] {error["message"]} {hint}')
        except requests.exceptions.ConnectionError as e:
            logging.error(f'[{self.alias}] Error connecting to {self.address}: {e}')
        except requests.exceptions.Timeout as e:
            logging.error(f'[{self.alias}] Timeout connecting to {self.address}: {e}')
        except requests.exceptions.RequestException as e:
            logging.error(f'[{self.alias}] Unexpected error while sending request to {url}: {e}')
        return None

    def _api_get(self, endpoint: str, requires_auth=True):
        if requires_auth and not self.sid:
            return None
        response = self._api_call(endpoint)
        if response:
            logging.debug(response.json())
            return response.json()
        return None

    def authenticate(self):
        """
        Authenticates with the Pi-hole API to retrieve the session ID (SID).
        https://ftl.pi-hole.net/development-v6/docs/#post-/auth
        """
        # TODO: The new API contains an endpoint to check if authentication is required on the server, however
        # I don't see a documented way to disable authentication. Maybe this check should be added in the future?
        # https://ftl.pi-hole.net/development-v6/docs/#get-/auth
        session_data = self._api_call('/auth', method='POST', json_data={"password": self.password}).json()["session"]
        if not session_data["valid"]:
            logging.error('Pi-hole auth session is not valid')
            return False
        self.sid = session_data["sid"]
        self.password = ""
        return True

    def get_summary(self):
        """
        Get overview of Pi-hole activity.
        https://ftl.pi-hole.net/development-v6/docs/#get-/stats/summary
        """
        return self._api_get('/stats/summary')

    def get_top_clients(self, count):
        """
        Get top clients.
        https://ftl.pi-hole.net/development-v6/docs/#get-/stats/top_clients
        """
        return self._api_get(f'/stats/top_clients?count={count}')

    def get_top_domains(self, count: int, blocked: bool):
        """
        Get top domains.
        https://ftl.pi-hole.net/development-v6/docs/#get-/stats/top_domains
        """
        return self._api_get(f'/stats/top_domains?count={count}&blocked={blocked}')

    def get_upstreams(self):
        """
        Get metrics about Pi-hole's upstream destinations.
        https://ftl.pi-hole.net/development-v6/docs/#get-/stats/upstreams
        """
        return self._api_get('/stats/upstreams')

    def get_history(self):
        """
        Get activity graph data.
        https://ftl.pi-hole.net/development-v6/docs/#get-/history
        """
        return self._api_get('/history')

    def get_blocking(self):
        """
        Get current blocking status.
        https://ftl.pi-hole.net/development-v6/docs/#get-/dns/blocking
        """
        return self._api_get('/dns/blocking')

class Config():
    """
    Class to contain the application configuration.
    """

    def __init__(self, args):
        # Set configuration by first checking for command-line arguments. If not present, check for the corresponding
        # environment variable. If not present, use the default.
        self.interval_seconds = int(args.interval or os.getenv("INTERVAL_SECONDS", DEFAULT_INTERVAL_SECONDS))
        # Set the request timeout to be either 50% of the polling interval, or 30 seconds, whichever is smaller.
        request_timeout = min(0.5 * self.interval_seconds, 30)
        pihole_aliases = (args.pihole_alias or os.getenv("PIHOLE_ALIAS", DEFAULT_PIHOLE_ALIAS)).split(',')
        pihole_addresses = (args.pihole_address or os.getenv("PIHOLE_ADDRESS", DEFAULT_PIHOLE_ADDRESS)).split(',')
        if len(pihole_addresses) == 0:
            logging.error("No Pi-hole instances provided")
            exit(1)
        if len(pihole_aliases) != len(pihole_addresses):
            logging.error('The number of Pi-hole aliases provided does not match the number of Pi-hole addresses')
            exit(1)
        pihole_passwords = (args.pihole_password or os.getenv("PIHOLE_PASSWORD", DEFAULT_PIHOLE_PASSWORD))
        pihole_passwords = pihole_passwords.split(',') if pihole_passwords else []
        self.piholes = {}
        for alias,address,password in zip_longest(pihole_aliases, pihole_addresses, pihole_passwords):
            if address in self.piholes:
                logging.warning(f'Duplicate Pi-hole address provided ({address}), skipping...')
                continue
            if not password:
                logging.warning(f'No password provided for {alias}, some data will not be available')
            pihole = Pihole(alias, address, request_timeout, password)
            if password:
                pihole.authenticate()
            self.piholes[address] = pihole
        self.num_top_items = int(args.pihole_num_top_items or os.getenv("PIHOLE_NUM_TOP_ITEMS",
                                                                        DEFAULT_PIHOLE_NUM_TOP_ITEMS))
        self.num_top_clients = int(args.pihole_num_top_clients or os.getenv("PIHOLE_NUM_TOP_CLIENTS",
                                                                            DEFAULT_PIHOLE_NUM_TOP_CLIENTS))
        self.influxdb_address = args.influxdb_address or os.getenv("INFLUXDB_ADDRESS", DEFAULT_INFLUXDB_ADDRESS)
        self.influxdb_org = args.influxdb_org or os.getenv("INFLUXDB_ORG", DEFAULT_INFLUXDB_ORG)
        self.influxdb_token = args.influxdb_token or os.getenv("INFLUXDB_TOKEN", DEFAULT_INFLUXDB_TOKEN)
        if not self.influxdb_token:
            logging.error('No InfluxDB auth token provided')
            exit(1)
        self.influxdb_bucket = args.influxdb_bucket or os.getenv("INFLUXDB_BUCKET", DEFAULT_INFLUXDB_BUCKET)
        self.influxdb_create_bucket = args.influxdb_create_bucket or os.getenv("INFLUXDB_CREATE_BUCKET",
                                                                               DEFAULT_INFLUXDB_CREATE_BUCKET)
        self.influxdb_verify_ssl = bool(args.influxdb_skip_verify_ssl if args.influxdb_skip_verify_ssl is not None
                                        else os.getenv("INFLUXDB_VERIFY_SSL", DEFAULT_INFLUXDB_VERIFY_SSL))

    def dump(self):
        """
        Dump the configuration to the log.
        """
        logging.info('================== Configuration ==================')
        first_pihole = list(self.piholes.values())[0]
        logging.info(f'Pi-holes:            {first_pihole.print_config()}')
        for pihole in list(self.piholes.values())[1:]:
            logging.info(f'                     {pihole.print_config}')
        logging.info(f'Poll interval:       {self.interval_seconds} seconds')
        logging.info(f'InfluxDB address:    {self.influxdb_address}')
        logging.info(f'InfluxDB org:        {self.influxdb_org}')
        logging.info(f'InfluxDB token:      {"******" if self.influxdb_token else "(None)"}')
        logging.info(f'InfluxDB bucket:     {self.influxdb_bucket}')
        logging.info(f'InfluxDB verify SSL: {self.influxdb_verify_ssl}')
        logging.info('===================================================')
        return

class PiholeInfluxDB():

    def __init__(self, config):
        self.config = config

    def _verify_bucket(self):
        """
        Ensure that the target InfluxDB bucket exists, creating it if necessary.
        """
        influxdb_client = InfluxDBClient(url=self.config.influxdb_address,
                                         token=self.config.influxdb_token,
                                         org=self.config.influxdb_org,
                                         verify_ssl=self.config.influxdb_verify_ssl)
        try:
            buckets_api = influxdb_client.buckets_api()
            if buckets_api.find_bucket_by_name(self.config.influxdb_bucket) is None:
                if self.config.influxdb_create_bucket:
                    logging.info('InfluxDB bucket does not yet exist - creating...')
                    retention_rules = BucketRetentionRules(type="expire", every_seconds=604800) # 7-day retention
                    buckets_api.create_bucket(bucket_name=self.config.influxdb_bucket,
                                              org=self.config.influxdb_org,
                                              retention_rules=retention_rules)
                else:
                    logging.error('InfluxDB bucket does not exist')
                    return False
        except Exception as e:
            logging.error(f'Error creating InfluxDB bucket: {str(e)}')
            return False
        return True

    def _create_point(self, measurement: str, tags: dict, fields: dict, time: int, field_types: dict):
        return Point.from_dict(
            {
                "measurement": measurement,
                "tags": tags,
                "fields": fields,
                "time": time
            },
            WritePrecision.S,
            field_types = field_types
        )

    def _write_to_influxdb(self, pihole: Pihole, summary: dict, top_clients: dict, top_permitted_domains: dict,
                           top_blocked_domains: dict, upstreams: dict, history: dict, blocking):
        """
        Write all data gathered to InfluxDB.

        Note: Some measurements (top clients, upstreams, etc.) are written to InfluxDB as an encoded string rather than
              leveraging separate fields for the different clients, upstreams, etc. This is to facilitate querying the
              data. If separate fields were used, it would be different to get an accurate read on what the Pi-hole is
              reporting as the latest data because a "stale" client, upstream etc. would likely still be returned in a
              query.
        """
        now_seconds = int(time.time())
        hostname = urlparse(pihole.address).hostname
        tags = {
            "alias": pihole.alias,
            "hostname": hostname
        }
        points=[]

        if summary:
            # Gravity
            gravity = summary.pop("gravity")
            points.append(self._create_point("gravity", tags, gravity, now_seconds, {x: "uint" for x in gravity}))

            # Clients
            clients = summary.pop("clients")
            points.append(self._create_point("clients", tags, clients, now_seconds, {x: "uint" for x in clients}))

            # Queries
            queries = summary.pop("queries")

            # Number of individual replies to queries
            query_replies = queries.pop("replies")
            points.append(self._create_point("query_replies", tags, query_replies, now_seconds,
                                             {x: "uint" for x in query_replies}))

            # Number of individual queries by status
            query_statuses = queries.pop("status")
            points.append(self._create_point("query_statuses", tags, query_statuses, now_seconds,
                                             {x: "uint" for x in query_statuses}))

            # Number of individual queries by type
            query_types = queries.pop("types")
            points.append(self._create_point("query_types", tags, query_types, now_seconds,
                                             {x: "uint" for x in query_types}))

            # Remaining query data
            # XXX: "frequency" is not a documented field
            points.append(self._create_point("queries", tags, queries, now_seconds,
                                             {x: "float" if x in ["percent_blocked", "frequency"]
                                              else "uint" for x in queries}))

        if top_clients:
            clients = top_clients.pop("clients")
            data = {"top_clients": ','.join([f'{x["ip"]}|{x["name"]}|{x["count"]}' for x in clients])}
            points.append(self._create_point("top_clients", tags, data, now_seconds, {x: "str" for x in data}))

        if top_permitted_domains:
            permitted_domains = top_permitted_domains.pop("domains")
            data = {"top_permitted_domains": ','.join([f'{x["domain"]}|{x["count"]}' for x in permitted_domains])}
            points.append(self._create_point("top_permitted_domains", tags, data, now_seconds,
                                             {x: "str" for x in data}))

        if top_blocked_domains:
            blocked_domains = top_blocked_domains.pop("domains")
            data = {"top_blocked_domains": ','.join([f'{x["domain"]}|{x["count"]}' for x in blocked_domains])}
            points.append(self._create_point("top_blocked_domains", tags, data, now_seconds, {x: "str" for x in data}))

        if upstreams:
            upstream_data = upstreams.pop("upstreams")
            data = {"upstreams": ','.join([f'{x["ip"]}|{x["name"]}|{x["port"]}|{x["count"]}|{x["statistics"]["response"]}|{x["statistics"]["variance"]}' for x in upstream_data])}
            points.append(self._create_point("upstreams", tags, data, now_seconds, {x: "str" for x in data}))

        if history:
            query_history = history.pop("history")
            for datapoint in query_history:
                timestamp = int(datapoint.pop("timestamp"))
                points.append(self._create_point("history", tags, datapoint, timestamp, {x: "uint" for x in datapoint}))

        if blocking:
            blocking_status = {
                "blocking": blocking["blocking"],
                "timer": blocking["timer"] if blocking["timer"] is not None else -1
            }
            points.append(self._create_point("blocking", tags, blocking_status, now_seconds, {"blocking": "str", "timer": "int"}))

        # Batch write of points
        influxdb_client = InfluxDBClient(url=self.config.influxdb_address,
                                         token=self.config.influxdb_token,
                                         org=self.config.influxdb_org,
                                         verify_ssl=self.config.influxdb_verify_ssl)
        try:
            with influxdb_client.write_api(write_options=SYNCHRONOUS) as write_api:
                write_api.write(self.config.influxdb_bucket, self.config.influxdb_org, record=points)
        except Exception as e:
            logging.error(f'Error writing data to InfluxDB: {str(e)}')
            return False
        return True

    def _run_job(self, pihole):
        """
        Runs the scheduled polling job for a single Pi-hole.
        """
        query_start = datetime.now()
        summary = pihole.get_summary()
        top_clients = pihole.get_top_clients(self.config.num_top_clients)
        top_permitted_domains = pihole.get_top_domains(self.config.num_top_items, False)
        top_blocked_domains = pihole.get_top_domains(self.config.num_top_items, True)
        upstreams = pihole.get_upstreams()
        history = pihole.get_history()
        blocking = pihole.get_blocking()
        query_duration = int((datetime.now() - query_start).total_seconds() * 1000)
        logging.info(f'[{pihole.alias}] Queried successfully in {query_duration}ms')
        write_start = datetime.now()
        if self._write_to_influxdb(pihole, summary, top_clients, top_permitted_domains, top_blocked_domains, upstreams,
                                   history, blocking):
            write_duration = int((datetime.now() - write_start).total_seconds() * 1000)
            logging.info(f'[{pihole.alias}] Wrote to InfluxDB successfully in {write_duration}ms')
        return

    def start(self):
        """
        Starts the scheduled polling jobs for each Pi-hole instance.
        """
        logging.info('Starting...')
        # Ensure the target bucket exists
        if not self._verify_bucket():
            exit(1)
        # Schedule one job per Pi-hole instance to monitor
        for pihole in self.config.piholes.values():
            job = schedule.every(self.config.interval_seconds).seconds.do(self._run_job, pihole=pihole)
            job.run() # Run immediately without initial delay
        # Run until stopped
        while True:
            schedule.run_pending()
            time.sleep(1)

def signal_handler(signum, frame):
    """
    Handler for SIGTERM and SIGINT signals.
    """
    if signum in [signal.SIGTERM, signal.SIGINT]:
        logging.info('Stopping...')
        exit(0)
    exit(1)

def main():
    # Parse any command-line arguments, which take a higher precedence than environment variables
    parser = argparse.ArgumentParser(description='Query Pi-hole instances for statistics and store them in InfluxDB')
    parser.add_argument('-i', '--interval',
        type=int,
        help=f'interval (in seconds) between queries to the Pi-hole instance(s) (Default: {DEFAULT_INTERVAL_SECONDS})')
    parser.add_argument('--pihole-alias',
        type=str,
        help=f'comma-separated list of aliases for Pi-hole instances (Default: {DEFAULT_PIHOLE_ALIAS})')
    parser.add_argument('--pihole-address',
        type=str,
        help=f'comma-separated list of addresses for Pi-hole instances (Default: {DEFAULT_PIHOLE_ADDRESS})')
    parser.add_argument('--pihole-password',
        type=str,
        help=f'comma-separated list of Pi-hole passwords (Default: {DEFAULT_PIHOLE_PASSWORD})')
    parser.add_argument('--pihole-num-top-items',
        type=int,
        help=f'number of top domains queried and ad domains (Default: {DEFAULT_PIHOLE_NUM_TOP_ITEMS})')
    parser.add_argument('--pihole-num-top-clients',
        type=int,
        help=f'number of top clients (Default: {DEFAULT_PIHOLE_NUM_TOP_CLIENTS})')
    parser.add_argument('--influxdb-address',
        type=str,
        help=f'address of the InfluxDB server (Default: {DEFAULT_INFLUXDB_ADDRESS})')
    parser.add_argument('--influxdb-org',
        type=str,
        help=f'InfluxDB organization to use (Default: {DEFAULT_INFLUXDB_ORG})')
    parser.add_argument('--influxdb-bucket',
        type=str,
        help=f'InfluxDB bucket to store data (Default: {DEFAULT_INFLUXDB_BUCKET})')
    parser.add_argument('--influxdb-create-bucket',
        action='store_true',
        help='Create the InfluxDB bucket if it does not already exist')
    parser.add_argument('--influxdb-token',
        type=str,
        help=f'InfluxDB auth token (Default: {DEFAULT_INFLUXDB_TOKEN})')
    parser.add_argument('--influxdb-skip-verify-ssl',
        action='store_false',
        help='Skip verification of the SSL certificate for InfluxDB')
    parser.add_argument('-d', '--debug',
        action='store_true',
        help=f'Enable debug logging (Default: {DEBUG})')
    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.debug or os.getenv("DEBUG") else logging.INFO
    logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=log_level, datefmt="%H:%M:%S")

    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    config = Config(args)
    config.dump()
    PiholeInfluxDB(config).start()

if __name__ == "__main__":
    main()
