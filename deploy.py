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
      'compute.googleapis.com', 'bigquerydatatransfer.googleapis.com'
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
              # Replace source table name
              `{project_id}.analytics_{ga_property}.events_*`
            WHERE
              event_name IN ('LCP', 'FID', 'CLS', 'first_visit', 'purchase')
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


def deploy_p75_procedure(project_id: str, ga_property: str):
  """Deploys the p75 stored procedure to BigQuery.

  The p75 procedure is used by the email alerting function to find if the CWV
  values have crossed the threshold set by the user.

  Args:
    project_id: The GCP project ID the procedure is being deployed to.
    ga_property: The GA property used to collect the CWV data.
  """

  p75_procedure = f"""CREATE OR REPLACE
  PROCEDURE analytics_{ga_property}.get_cwv_p75_for_date(start_date date, num_days INT64) BEGIN
SELECT
  metric_name, APPROX_QUANTILES(metric_value, 100)[OFFSET(75)] AS p75, COUNT(1) AS count
FROM `{project_id}.analytics_{ga_property}.web_vitals_summary`
WHERE
  PARSE_DATE('%Y%m%d', event_date)
  BETWEEN DATE_SUB(start_date, INTERVAL num_days DAY)
  AND DATE_SUB(start_date, INTERVAL 1 DAY)
GROUP BY 1;

END
  """

  bq_client = bigquery.Client()
  query_job = bq_client.query(p75_procedure)

  def query_done_callback(job):
    if job.error_result:
      print('There was an error deploying the p75 procedure: ', file=sys.stderr)
      for error_key in job.error_result.keys():
        for error in job.error_result[error_key]:
          print(error, file=sys.stderr)
      raise SystemExit('Please check the GCP logs and try again.')

  query_job.add_done_callback(query_done_callback)
  query_job.result()


def deploy_cloudrun_alerter(ga_property: str, region: str, lcp_threshold: int,
                            cls_threshold: float, fid_threshold: int,
                            email_server: str, email_user: str,
                            email_password: str, email_from: str,
                            alert_recipients: str):
  """Deploys the Cloud Run function that sends the alert email.

  The GCP API doesn't provide a function to deploy functions from source, so
  we shell out to the gcloud command. That command sets the environment
  variables for the function to use and deploys it from the source in the
  notifications directory.

  Note: this won't work if the script is moved, so we fail if the
  notifications directory is not found.

  Args:
    ga_property: The GA property used to collect the CWV data.
    region: The region to deploy the function to. This must be the same region
      the CWV data is stored in in BQ.
    lcp_threshold: The threshold LCP value to send the email for.
    cls_threshold: The threshold CLS value to send the email for.
    fid_threshold: The threshold FID value to send the email for.
    email_server: The SMTP server to use to send the email.
    email_user: The user name to use when authenticating with the server.
    email_password: The password to use when authenticating with the server.
    email_from: The email address to use in the alert's From field.
    alert_recipients: A comma-separated list of emails to send the alert to.

  Raises:
    SystemExit: Raised when the deployment fails.
  """
  # : used as a separator to allow a comma-separated list of alert recipients.
  env_vars = (f'^:^ANALYTICS_ID={ga_property}:'
              f'GOOD_LCP={lcp_threshold}:'
              f'GOOD_CLS={cls_threshold}:'
              f'GOOD_FID={fid_threshold}:'
              f'EMAIL_SERVER={email_server}:'
              f'EMAIL_USER={email_user}:'
              f'EMAIL_PASS={email_password}:'
              f'EMAIL_FROM={email_from}:'
              f'ALERT_RECEIVERS={alert_recipients}')

  source_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)),
                            'notifications')
  if not os.path.isdir(source_dir):
    print('Source directory for the email notification function not found.',
          file=sys.stderr)
    raise SystemExit('Please ensure the deploy script is in the distribution '
                     'directory as delivered.')

  try:
    subprocess.run([
        'gcloud', 'run', 'deploy', 'cwv-alerting-service', f'--region={region}',
        f'--set-env-vars={env_vars}', '--source', source_dir
    ],
                   check=True)
  except subprocess.CalledProcessError as cpe:
    raise SystemExit('Deploying the email alerting function failed. Please '
                     'check the messages above and correct any issues before '
                     'trying again.') from cpe


def create_cloudrun_trigger(project_id: str, region: str, service_account: str):
  """Creates the trigger to check if an alert email should be sent.

  This creates a trigger named cwv-alert-email-trigger that fires when a
  BigQuery insert job completes. It deletes the trigger with the same name if
  it exists first.

  Args:
    project_id: The GCP project ID the trigger is being deployed to.
    region: The region to create the trigger in.
    service_account: The service account to assign the trigger.
  """
  trigger_name = (f'projects/{project_id}/locations/{region}/triggers/'
                  'cwv-alert-email-trigger')
  eventarc_client = eventarc.EventarcClient()

  eventarc_client.delete_trigger(name=trigger_name, allow_missing=True)

  destination = Destination(
      cloud_run=CloudRun(service='cwv-alerting-service', region=region))
  event_filters = [
      EventFilter(attribute='type', value='google.cloud.audit.log.v1.written'),
      EventFilter(attribute='serviceName', value='bigquery.googleapis.com'),
      EventFilter(attribute='methodName',
                  value='google.cloud.bigquery.v2.JobService.InsertJob')
  ]

  new_trigger = eventarc.Trigger(name=trigger_name,
                                 destination=destination,
                                 service_account=service_account,
                                 event_filters=event_filters)
  parent = eventarc_client.common_location_path(project=project_id,
                                                location=region)
  try:
    eventarc_client.create_trigger(parent=parent,
                                   trigger=new_trigger,
                                   trigger_id='cwv-alert-email-trigger')
  except Exception as ex:
    print(ex, file=sys.stderr)
    raise SystemExit(
        'The event trigger was not created. Please check the '
        'errors above and ensure the service account you are using'
        ' has the correct roles (e.g. oles/eventarc.eventReceiver') from ex


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


def add_roles_to_service_account(
    service_account: str, project_id: str, credentials: Credentials) -> None:
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
  arg_parser.add_argument('-l',
                          '--lcp-threshold',
                          default=2500,
                          help=('The value to use as the threshold for a good '
                                'LCP score in ms (default %(default)d).'))
  arg_parser.add_argument('-f',
                          '--fid-threshold',
                          default=100,
                          help=('The value to use as a threshold for a good FID'
                                ' score in ms (default %(default)d)'))
  arg_parser.add_argument('-c',
                          '--cls-threshold',
                          default=0.1,
                          help=('The value to use as a threshold for a good CLS'
                                ' score (unit-less)(default %(default)1.1f)'))
  arg_parser.add_argument('-s',
                          '--email-server',
                          help=('The address of the email server to use to send'
                                ' alerts.'))
  arg_parser.add_argument('-u',
                          '--email-user',
                          help=('The username to use to authenticate with the '
                                'email server.'))
  arg_parser.add_argument('-p',
                          '--email-password',
                          help=('The password to use to authenticate with the '
                                'email server'))
  arg_parser.add_argument('-e',
                          '--email-from',
                          help=('The email address used in the from field of '
                                'the alert'))
  arg_parser.add_argument('-a',
                          '--alert-recipients',
                          help=('A comma-separated list of email addresses to '
                                'send the alerts to.'))
  arg_parser.add_argument('-i',
                          '--iam-service-account',
                          help=('The email of the IAM service account to use '
                                'when authenticating calls to the email '
                                'alerting function. Please note that this '
                                'account requires roles/eventarc.eventReceiver.'
                                ' If not provided, the default compute service '
                                'account is used.'))
  arg_parser.add_argument('--email-alert',
                          help='Flag for deploying the email alerting service',
                          action='store_true',
                          dest='email_alert')
  arg_parser.add_argument('--no-email-alert',
                          help='Flag to not deploy the email alerting service',
                          action='store_false',
                          dest='email_alert')
  arg_parser.set_defaults(email_alert=True)

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

  if not args.iam_service_account:
    input_msg = 'Please enter the email of the service account to use: '
    if hasattr(credentials, 'service_account_email'):
      if credentials.service_account_email == 'default':
        args.iam_service_account = get_default_service_account_email(
           project_id, credentials)
      else:
        args.iam_service_account = credentials.service_account_email

      input_msg = ('Please note: using the default service account, '
        f'{args.iam_service_account}, will result in a new role being created '
        'to allow for the creation and execution of BigQuery scheduled queries.'
        '\n' + input_msg)

    else:
      input_msg = ('Please note: your default credentials do not provide a '
      'service account. You must provide one here.\n' + input_msg)

    user_service_account = input(input_msg).strip()

    if not user_service_account:
      add_roles_to_service_account(args.iam_service_account,
                                                  project_id, credentials)
    else:
      raise SystemExit('You must provide a service account for deploying and '
        'running the solution to continue. Please create a service account and'
        ' try again.')

  deploy_scheduled_materialize_query(project_id, credentials, args.region,
                                     args.ga_property, args.iam_service_account)

  if args.email_alert:
    if not args.email_server:
      args.email_server = input(
          'Please enter the address of the email server to use to send alerts '
          '(leave empty to not deploy the email alerting function): ').strip()
    if args.email_server:
      if not args.email_user:
        args.email_user = input(
            'Please enter the username for authenticating with the email '
            'server: ').strip()
      if not args.email_password:
        args.email_password = input(
            'Please enter the password for authenticating with the email '
            'server: ').strip()
      if not args.email_from:
        args.email_from = input(
            'Please enter the email address to use in the FROM field: ').strip(
            )
      if not args.alert_recipients:
        args.alert_recipients = input(
            'Please enter a comma-separated list of email addresses to send '
            'the alerts to: ').strip()

      # only ask for CWV thresholds if no args were used, defaults will
      # otherwise be used
      if len(sys.argv) == 1:
        args.lcp_threshold = input(
            'Please enter the alert threshold for LCP in ms (default 2500): '
        ).strip()
      if not args.lcp_threshold:
        args.lcp_threshold = 2055
      args.fid_threshold = input(
          'Please enter the alert threshold for FID in ms (default 100): '
      ).strip()
      if not args.fid_threshold:
        args.fid_threshold = 100
      args.cls_threshold = input(
          'Please enter the threshold for CLS (default 0.1): ').strip()
      if not args.cls_threshold:
        args.cls_threshold = 0.1

    deploy_p75_procedure(project_id, args.ga_property)
    if args.email_server:
      deploy_cloudrun_alerter(args.ga_property, args.region, args.lcp_threshold,
                              args.cls_threshold, args.fid_threshold,
                              args.email_server, args.email_user,
                              args.email_password, args.email_from,
                              args.alert_recipients)
      create_cloudrun_trigger(project_id, args.region, args.iam_service_account)


if __name__ == '__main__':
  main()
