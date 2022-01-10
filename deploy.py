#!/usr/bin/env python3
import argparse
import os
from typing import List
import google.auth
from google.auth.credentials import Credentials
import google.api_core.exceptions
from googleapiclient import discovery
from google.cloud import bigquery_datatransfer

# Copyright 2021 Google LLC
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Deploys the SQL tables and scripts needed to collect CWVs according to the
# standard set in https://web.dev/vitals-ga4/ as well as a cloud run function
# for alerting.


def get_gcp_regions(credentials: Credentials, project_id: str) -> List[str]:
  """Fetches the list of available GCP regions and returns a list of str.

  Args:
    project: The project to use when making the query.

  Returns:
    A list of region names in str format.
  """
  regions = []
  service = discovery.build('compute', 'v1', credentials=credentials)
  request = service.regions().list(project=project_id)
  while request is not None:
    response = request.execute()
    for region in response['items']:
      regions.append(region['name'])

    request = service.regions().list(previous_request=request,
                                     previous_response=response)

  return regions


def delete_scheduled_query(config_name: str, project_id: str):
  """Deletes the BigQuery scheduled query (data transfer) with the given name.

  Args:
    config_name: the name of the config to delete.
  """
  transfer_client = bigquery_datatransfer.DataTransferServiceClient()
  parent = transfer_client.common_project_path(project_id)
  configs = transfer_client.list_transfer_configs(parent=parent)
  for config in configs:
    if config.display_name == config_name:
      transfer_client.delete_transfer_config(name=config.name)


def deploy_scheduled_materialize_query():
  pass


def deploy_p75_procedure():
  pass


def deploy_cloudrun_alerter():
  pass


def create_cloudrun_trigger():
  pass


def main():
  """The main entry point.

  Command line arguments are parsed and any missing information is gathered
  before running through the deployment steps.
  """
  arg_parser = argparse.ArgumentParser(
    description='Deploys the CWV in GA solution')
  arg_parser.add_argument('-r', '--region',
                          help='The region the solution is deployed to.')
  arg_parser.add_argument('-g', '--ga-property',
                          help=('The GA property ID to use when looking for '
                                'exports in big query.'))
  arg_parser.add_argument('-l', '--lcp-threshold', default=2500,
                          help=('The value to use as the threshold for a good '
                                'LCP score in ms (default %(default)d).'))
  arg_parser.add_argument('-f' '--fid-threshold', default=100,
                          help=('The value to use as a threshold for a good FID'
                                ' score in ms (default %(default)d)'))
  arg_parser.add_argument('-c', '--cls-threshold', default=0.1,
                          help=('The value to use as a threshold for a good CLS'
                                ' score (unit-less)(default %(default)1.1f)'))
  arg_parser.add_argument('-s', '--email-server',
                          help=('The address of the email server to use to send'
                                ' alerts.'))
  arg_parser.add_argument('-u', '--email-user',
                          help=('The username to use to authenticate with the '
                                'email server.'))
  arg_parser.add_argument('-p', '--email-password',
                          help=('The password to use to authenticate with the '
                                'email server'))
  arg_parser.add_argument('-a', '--alert-recipients',
                          help=('A comma-separated list of email addresses to '
                                'send the alerts to.'))

  args = arg_parser.parse_args()

  credentials, project_id = google.auth.default()
  if project_id is None:
    project_id = os.environ['GOOGLE_CLOUD_PROJECT']

  if not args.region:
    args.region = input(
      'Which region should be deployed to (type list for a list)? ').strip()
    while args.region == 'list':
      region_list = get_gcp_regions(credentials, project_id)
      print('\n'.join(region_list))
      args.region = input(
        'Which region should be deployed to (type list for a list)? ').strip()
  if not args.ga_property:
    args.ga_property = (input(
      'Please enter the GA property ID you are collecting CWV data with: ')
      .strip())
  if not args.ga_property.isdigit():
    raise SystemExit('Only GA4 properties are supported at this time.')

  if not args.email_server:
    args.email_server = (input(
      'Please enter the address of the email server to use to send alerts: ')
      .strip())
  if not args.email_user:
    args.email_user = (input(
      'Please enter the username for authenticating with the email server: ')
      .strip())
  if not args.email_password:
    args.email_password = (input(
      'Please enter the password for authenticating with the email server: ')
      .strip())
  if not args.alert_recipients:
    args.alert_recipients = (input(
      'Please enter a comma-separated list of email addresses to send the '
      'alerts to: ')).strip()

  deploy_scheduled_materialize_query()
  deploy_p75_procedure()
  deploy_cloudrun_alerter()
  create_cloudrun_trigger()


if __name__ == '__main__':
  main()
