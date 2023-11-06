#!/usr/bin/env python3
"""Deployment script for CWV in GA4 solution.

 Deploys the SQL tables and scripts needed to collect CWVs according to the
 standard set in https://web.dev/vitals-ga4/ as well as a cloud run function
 for alerting.

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at
     https://www.apache.org/licenses/LICENSE-2.0
 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
"""

import argparse
import os
import subprocess
import sys
import time
from typing import List

import google.api_core.exceptions
import google.auth
from google.auth.credentials import Credentials
from google.cloud import bigquery
from google.cloud import bigquery_datatransfer
from google.cloud import eventarc
from google.cloud import service_usage_v1

from google.cloud.eventarc_v1.types.trigger import CloudRun
from google.cloud.eventarc_v1.types.trigger import Destination
from google.cloud.eventarc_v1.types.trigger import EventFilter
from googleapiclient import discovery


def enable_services(credentials: Credentials, project_id: str):
  """Enables the services required to use the solution.

  Args:
    credentials: the Google credentials to use to authenticate.
    project_id: the project the services will be enabled for.
  """
  crm = discovery.build('cloudresourcemanager', 'v3')
  project = crm.projects().get(name='projects/' + project_id).execute()
  client = service_usage_v1.ServiceUsageClient(credentials=credentials)
  request = service_usage_v1.BatchEnableServicesRequest()
  request.parent = project['name']
  request.service_ids = [
      'compute.googleapis.com',
      'bigquerydatatransfer.googleapis.com',
      'iam.googleapis.com',
  ]
  operation = client.batch_enable_services(request=request)
  try:
    operation.result()
  except google.api_core.GoogleAPICallError as ex:
    raise SystemExit('Unable to enable the required services. Please check the'
                     ' logs and resolve the issues found there.') from ex


def get_gcp_regions(credentials: Credentials, project_id: str) -> List[str]:
  """Fetches the list of available GCP regions and returns a list of str.

  Args:
    credentials: the Google credentials to use to authenticate.
    project_id: The project to use when making the query.

  Returns:
    A list of region names in str format.
  """
  regions = []
  service = discovery.build('compute', 'v1', credentials=credentials)
  request = service.regions().list(project=project_id)
  while request is not None:
    response = request.execute()
    for region in response['items']:
      if 'name' in region and region['name']:
        regions.append(region['name'])

    if 'nextPageToken' in response:
      request = service.regions().list(pageToken=response['nextPageToken'])
    else:
      request = None

  return regions


def delete_scheduled_query(display_name: str, project_id: str, region: str):
  """Deletes the BigQuery scheduled queries with the given display name.

  Please note that the display name of a BigQuery scheduled query is not
  unique. This means that multiple queries can be deleted.

  Args:
    display_name: the name of the config to delete.
    project_id: the project to delete the query from.
    region: the region the query is stored in.
  """
  transfer_client = bigquery_datatransfer.DataTransferServiceClient()
  parent = transfer_client.common_location_path(project=project_id,
                                                location=region)
  transfer_config_req = bigquery_datatransfer.ListTransferConfigsRequest(
      parent=parent, data_source_ids=['scheduled_query'])
  configs = transfer_client.list_transfer_configs(request=transfer_config_req)
  for config in configs:
    if config.display_name == display_name:
      transfer_client.delete_transfer_config(name=config.name)


def deploy_scheduled_materialize_query(project_id: str,
                                       credentials: Credentials, region: str,
                                       ga_property: str,
                                       service_account: str) -> None:
  """Deploys the query to create the materialized CWV summary table.

  The scheduled query is given the name "Update Web Vitals Summary" and any
  other scheduled query with this name will be deleted before the new one is
  deployed.

  Args:
    project_id: The project to deploy the query to.
    region: the region of the dataset used for the GA export.
    ga_property: The GA property used to collect the CWV data.
  """
  display_name = 'Update Web Vitals Summary'

  materialize_query = f"""
-- Copyright 2021 Google LLC
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at

--     https://www.apache.org/licenses/LICENSE-2.0

-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- Materialize Web Vitals metrics from GA4 event export data

CREATE OR REPLACE TABLE `{project_id}.analytics_{ga_property}.web_vitals_summary`
  PARTITION BY DATE(event_timestamp)
  CLUSTER BY metric_name
AS
SELECT
  ga_session_id,
  IF(
    EXISTS(
      SELECT 1
      FROM UNNEST(events) AS e
      WHERE e.event_name = 'first_visit'
    ),
    'New user',
    'Returning user') AS user_type,
  IF(
    (SELECT MAX(session_engaged) FROM UNNEST(events)) > 0, 'Engaged', 'Not engaged')
    AS session_engagement,
  evt.* EXCEPT (session_engaged, event_name),
  event_name AS metric_name,
  FORMAT_TIMESTAMP('%Y%m%d', event_timestamp) AS event_date
FROM
  (
    SELECT
      ga_session_id,
      ARRAY_AGG(custom_event) AS events
    FROM
      (
        SELECT
          ga_session_id,
          STRUCT(
            country,
            device_category,
            device_os,
            traffic_medium,
            traffic_name,
            traffic_source,
            page_path,
            debug_target,
            event_timestamp,
            event_name,
            metric_id,
            IF(event_name = 'LCP', metric_value / 1000, metric_value)
              AS metric_value,
            user_pseudo_id,
            session_engaged,
            session_revenue) AS custom_event
        FROM
          (
            SELECT
              (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id')
                AS ga_session_id,
              (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'metric_id')
                AS metric_id,
              ANY_VALUE(device.category) AS device_category,
              ANY_VALUE(device.operating_system) AS device_os,
              ANY_VALUE(traffic_source.medium) AS traffic_medium,
              ANY_VALUE(traffic_source.name) AS traffic_name,
              ANY_VALUE(traffic_source.source) AS traffic_source,
              ANY_VALUE(
                REGEXP_SUBSTR(
                  (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location'),
                  r'^[^?]+')) AS page_path,
              ANY_VALUE(
                (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'debug_target'))
                AS debug_target,
              ANY_VALUE(user_pseudo_id) AS user_pseudo_id,
              ANY_VALUE(geo.country) AS country,
              ANY_VALUE(event_name) AS event_name,
              SUM(ecommerce.purchase_revenue) AS session_revenue,
              MAX(
                (
                  SELECT
                    COALESCE(
                      value.double_value,
                      value.int_value,
                      CAST(value.string_value AS NUMERIC))
                  FROM UNNEST(event_params)
                  WHERE key = 'session_engaged'
                )) AS session_engaged,
              TIMESTAMP_MICROS(MAX(event_timestamp)) AS event_timestamp,
              MAX(
                (
                  SELECT COALESCE(value.double_value, value.int_value)
                  FROM UNNEST(event_params)
                  WHERE key = 'metric_value'
                )) AS metric_value,
            FROM
              `{project_id}.analytics_{ga_property}.events_*`
            WHERE
              event_name IN ('LCP', 'FID', 'CLS', 'INP', 'TTFB', 'first_visit', 'purchase')
            GROUP BY
              1, 2
          )
      )
    WHERE
      ga_session_id IS NOT NULL
    GROUP BY ga_session_id
  )
CROSS JOIN UNNEST(events) AS evt
WHERE evt.event_name NOT IN ('first_visit', 'purchase');
  """

  delete_scheduled_query(display_name=display_name,
                         project_id=project_id,
                         region=region)

  transfer_client = bigquery_datatransfer.DataTransferServiceClient(
      credentials=credentials)
  parent = transfer_client.common_location_path(project=project_id,
                                                location=region)
  transfer_config = bigquery_datatransfer.TransferConfig(
      display_name=display_name,
      data_source_id='scheduled_query',
      params={
          'query': materialize_query,
      },
      schedule='every 24 hours',
  )

  transfer_config = transfer_client.create_transfer_config(
      bigquery_datatransfer.CreateTransferConfigRequest(
          parent=parent,
          transfer_config=transfer_config,
          service_account_name=service_account))
  # wait 30 seconds for the query to complete. Otherwise anything depending on
  # the table being created will fail.
  time.sleep(30)


def get_default_service_account_email(project_id: str,
                                      credentials: Credentials) -> str:
  """Gets the email address for the default iam service account.

  Args:
    project_id: The GCP project to get the default account for.
    credentials: The credentials to use to authenticate.

  Returns:
    The email address of the default compute iam service account.
  """
  service = discovery.build('iam', 'v1', credentials=credentials)
  service_accounts = service.projects().serviceAccounts().list(
      name=f'projects/{project_id}').execute()
  for account in service_accounts['accounts']:
    display_name = account['displayName'].lower()
    if display_name.find('default') != -1:
      return account['email']

  return ''


def add_roles_to_service_account(service_account: str, project_id: str,
                                 credentials: Credentials) -> None:
  """Creates a new role with the permissions required to deploy the solution
  and it to the passed service account.

  The service account needs to have the correct permissions, and this is the
  most straightforward way of ensuring that. The permissions in the new role are
  - bigquery.tables.get
  - bigquery.tables.get
  - bigquery.tables.getData
  - bigquery.tables.list
  - bigquery.tables.create
  - bigquery.tables.update
  - bigquery.tables.updateData
  - bigquery.jobs.list
  - bigquery.jobs.create
  - bigquery.transfers.update
  - eventarc.events.receiveAuditLogWritten
  Args:
    service_account: The service account to add the role to.
    project_id: The project the new role will be created in.
    credentials: The credentials to authenticate the new role request with.
  """
  service = discovery.build('iam', 'v1', credentials=credentials)
  role_resp = service.projects().roles().list(
      parent=f'projects/{project_id}').execute()
  current_roles = role_resp.get('roles', [])
  role = None
  # if the role already exists, it's an error to try and create it again
  for r in current_roles:
    if r['name'].endswith('cwv_in_ga4_deployer'):
      role = r
      break
  if not role:
    role = service.projects().roles().create(
        parent=f'projects/{project_id}',
        body={
            'roleId': 'cwv_in_ga4_deployer',
            'role': {
                'title': 'CWV in GA4 Deployment role',
                'description': 'Used to deploy the CWV ni GA4 solution.',
                'includedPermissions': [
                    'bigquery.tables.get', 'bigquery.tables.getData',
                    'bigquery.tables.list', 'bigquery.tables.create',
                    'bigquery.tables.update', 'bigquery.tables.updateData',
                    'bigquery.jobs.list', 'bigquery.jobs.create',
                    'bigquery.transfers.update',
                    'eventarc.events.receiveAuditLogWritten'
                ],
                'stage': 'GA'
            }
        }).execute()
  if not role:
    raise SystemExit('There was an issue trying to create the role required for'
                     ' the BigQuery scheduled queries. Please check the cloud '
                     'logs, correct the issue, and try again.')

  service = discovery.build('cloudresourcemanager',
                            'v1',
                            credentials=credentials)
  policy = service.projects().getIamPolicy(resource=project_id,
                                           body={
                                               'options': {
                                                   'requestedPolicyVersion': 1
                                               }
                                           }).execute()
  policy['bindings'].append({
      'role': role['name'],
      'members': [f'serviceAccount:{service_account}']
  })
  service.projects().setIamPolicy(resource=project_id, body={
      "policy": policy
  }).execute()


def main():
  """The main entry point.

  Command line arguments are parsed and any missing information is gathered
  before running through the deployment steps.

  Raises:
    SystemExit: Raised when a non-GA4 property is entered.
  """
  arg_parser = argparse.ArgumentParser(
      description='Deploys the CWV in GA solution')
  arg_parser.add_argument('-g',
                          '--ga-property',
                          type=int,
                          help=('The GA property ID to use when looking for '
                                'exports in big query.'))
  arg_parser.add_argument('-r',
                          '--region',
                          help='The region GA data is being exported to.')
  arg_parser.add_argument('-i',
                          '--iam-service-account',
                          help=('The email of the IAM service account to use '
                                'when authenticating calls to the email '
                                'alerting function. Please note that this '
                                'account requires roles/eventarc.eventReceiver.'
                                ' If not provided, the default compute service '
                                'account is used.'))

  args = arg_parser.parse_args()

  credentials, project_id = google.auth.default()
  if not project_id:
    project_id = os.environ['GOOGLE_CLOUD_PROJECT']

  enable_services(credentials, project_id)

  if not args.region:
    args.region = input(
        'Which region should be deployed to (type list for a list)? ').strip()
    while args.region == 'list':
      region_list = get_gcp_regions(credentials, project_id)
      print('\n'.join(region_list))
      args.region = (input(
          'Which region is the GA export in (list for a list of regions)? ').
                     strip())

  if not args.ga_property:
    args.ga_property = (input(
        'Please enter the GA property ID you are collecting CWV data with: ').
                        strip())
    if not args.ga_property.isdigit():
      raise SystemExit('Only GA4 properties are supported at this time.')

  # the options are a service account email is provided with the default
  # credentials, the word default is provided in place of an email address, or
  # the service_account_email field isn't present at all on the credentials.
  if not args.iam_service_account:
    input_msg = 'Please enter the email of the service account to use: '
    if hasattr(credentials, 'service_account_email'):
      if credentials.service_account_email == 'default':
        args.iam_service_account = get_default_service_account_email(
            project_id, credentials)
      else:
        args.iam_service_account = credentials.service_account_email

      input_msg = (
          'Please note: using the default service account, '
          f'{args.iam_service_account}, will result in a new role being '
          'created to allow for the creation and execution of BigQuery '
          'scheduled queries.\n' + input_msg)

    else:
      input_msg = ('Please note: your default credentials do not provide a '
                   'service account. You must provide one here.\n' + input_msg)

    user_service_account = input(input_msg).strip()

    if user_service_account:
      args.iam_service_account = user_service_account

    if args.iam_service_account:
      add_roles_to_service_account(args.iam_service_account, project_id,
                                   credentials)
    else:
      raise SystemExit(
          'You must provide a service account for deploying and '
          'running the solution to continue. Please create a service account '
          'and try again.')

  deploy_scheduled_materialize_query(project_id, credentials, args.region,
                                     args.ga_property, args.iam_service_account)


if __name__ == '__main__':
  main()
