#!/usr/bin/env python3
"""Deploment script for the gPS Core Web Vitals GTM template.

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

import google.auth
from google.cloud import service_usage_v1
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient import discovery
from googleapiclient import errors


cwv_template_data = (
    "___TERMS_OF_SERVICE___\n\nBy creating or modifying this file you agree to"
    "Google Tag Manager's Community\nTemplate Gallery Developer Terms of"
    " Service"
    "available at\nhttps://developers.google.com/tag-manager/gallery-tos (or"
    " such"
    "other URL as\nGoogle may provide), as modified from time to"
    'time.\n\n\n___INFO___\n\n{\n "type": "TAG",\n "id":'
    '"cvt_temp_public_id",\n "version": 1,\n "securityGroups": [],\n'
    '"displayName": "gPS CWV Template",\n "brand": {\n "id":'
    '"brand_dummy",\n "displayName": ""\n },\n "description": "Simple'
    'template for collecting Core Web Vitals",\n "containerContexts": [\n'
    '"WEB"\n ]\n}\n\n\n___TEMPLATE_PARAMETERS___\n\n[\n {\n "type":'
    '"CHECKBOX",\n "name": "debugMode",\n "checkboxText": "Add the'
    'web-vitals attribution object to events.",\n "simpleValueType": true,\n'
    '"displayName": "Enable Debug Mode"\n'
    "}\n]\n\n\n___SANDBOXED_JS_FOR_WEB_TEMPLATE___\n\nconst createQueue ="
    "require('createQueue');\nconst copyFromWindow ="
    "require('copyFromWindow');\nconst injectScript ="
    "require('injectScript');\nconst logToConsole ="
    "require('logToConsole');\n\nconst dataLayerPush ="
    "createQueue('dataLayer');\n\n/** Extracts the CWV data from the object"
    " passed"
    "by web-vitals.\n *\n * @param event The event object passed by wb-vitals"
    " when"
    "this is used as a callback.\n *\n * @returns A new object with the CWV"
    " data.\n"
    "*/\nfunction extractCWVData(metric) {\n const cwvData = {\n metric_name:"
    "metric.name,\n metric_id: metric.id,\n metric_value: metric.value,\n"
    " value:"
    "metric.delta,\n };\n switch (metric.name) {\n case 'CLS':\n"
    " cwvData.target ="
    "metric.attribution.largestShiftTarget;\n break;\n case 'FID':\n"
    " cwvData.target"
    "= metric.attribution.eventTarget;\n break;\n case 'LCP':\n"
    " cwvData.target ="
    "metric.attribution.element;\n break;\n case 'INP':\n cwvData.target ="
    "metric.attribution.eventTarget;\n break;\n case 'TTFB':\n cwvData.target ="
    "metric.attribution.waitingTime;\n break;\n }\n if (data.debugMode) {\n"
    "cwvData.debug = metric.attribution;\n }\n return cwvData;\n}\n\n/**"
    " Pushes a"
    "CWV measurement object to the GTM data layer.\n *\n * @param event An"
    " object"
    "returned from extractCWVData.\n */\nfunction pushToDataLayer(metric) {\n"
    "dataLayerPush({\n event: 'core-web-vitals',\n data:"
    " extractCWVData(metric)\n"
    "});\n}\n\nfunction setupWebVitals() {\n const webVitals ="
    "copyFromWindow('webVitals');\n webVitals.onCLS(pushToDataLayer);\n"
    "webVitals.onFID(pushToDataLayer);\n webVitals.onLCP(pushToDataLayer);\n"
    "webVitals.onINP(pushToDataLayer);\n webVitals.onTTFB(pushToDataLayer);\n"
    "data.gtmOnSuccess();\n}\n\nfunction failedToLoadWebVitals() {\n"
    "logToConsole('web-vitals libray failed to load');\n"
    "data.gtmOnFailure();\n}\n\ninjectScript('https://unpkg.com/web-vitals@3/dist/web-vitals.attribution.iife.js',\n"
    "setupWebVitals,\n failedToLoadWebVitals,\n"
    "'web-vitals-tag'\n);\n\n\n___WEB_PERMISSIONS___\n\n[\n {\n"
    ' "instance": {\n'
    '"key": {\n "publicId": "access_globals",\n "versionId": "1"\n },\n'
    '"param": [\n {\n "key": "keys",\n "value": {\n "type": 2,\n'
    '"listItem": [\n {\n "type": 3,\n "mapKey": [\n {\n "type": 1,\n'
    '"string": "key"\n },\n {\n "type": 1,\n "string": "read"\n },\n {\n'
    '"type": 1,\n "string": "write"\n },\n {\n "type": 1,\n "string":'
    '"execute"\n }\n ],\n "mapValue": [\n {\n "type": 1,\n "string":'
    '"dataLayer"\n },\n {\n "type": 8,\n "boolean": true\n },\n {\n "type":'
    '8,\n "boolean": true\n },\n {\n "type": 8,\n "boolean": false\n }\n ]\n'
    '}\n ]\n }\n }\n ]\n },\n "clientAnnotations": {\n "isEditedByUser": true\n'
    '},\n "isRequired": true\n },\n {\n "instance": {\n "key": {\n'
    '"publicId": "logging",\n "versionId": "1"\n },\n "param": [\n {\n'
    '"key": "environments",\n "value": {\n "type": 1,\n "string":'
    '"debug"\n }\n }\n ]\n },\n "isRequired": true\n },\n {\n "instance": {\n'
    '"key": {\n "publicId": "inject_script",\n "versionId": "1"\n },\n'
    '"param": [\n {\n "key": "urls",\n "value": {\n "type": 2,\n'
    '"listItem": [\n {\n "type": 1,\n "string":'
    '"https://unpkg.com/web-vitals@3/dist/web-vitals.attribution.iife.js"\n }\n'
    ']\n }\n }\n ]\n },\n "clientAnnotations": {\n "isEditedByUser": true\n'
    '},\n "isRequired": true\n }\n]\n\n\n___TESTS___\n\nscenarios:\n- name:'
    "Extracts Data\n code: |-\n const mockData = {\n // Mocked field values\n"
    "};\n\n // Call runCode to run the template's code.\n"
    " runCode(mockData);\n\n //"
    "Verify that the tag finished successfully.\n"
    "assertApi('gtmOnSuccess').wasCalled();\n\n\n___NOTES___\n\n\n\n\n"
)


def enable_tagmanager_api(project_id: str, credentials: Credentials):
  """Turns on the Tag Manager API for the given GCP project.

  Args:
    project_id: The GCP project to enable the API on.
    credentials: The credentials used to authenticate with GCP.
  """
  crm = discovery.build("cloudresourcemanager", "v3")
  service_client = service_usage_v1.ServiceUsageClient(credentials=credentials)
  req = service_usage_v1.EnableServiceRequest()
  req.name = f"projects/{project_id}/services/tagmanager.googleapis.com"
  operation = service_client.enable_service(req)
  try:
    operation.result()
  except google.api_core.GoogleAPICallError as ex:
    raise SystemExit(
        "Unable to enable the Tag Manager API."
        " Please check the logs and try again."
    ) from ex


def get_oauth_creds(client_id: str, client_secret: str) -> Credentials:
  client_config = {
      "installed": {
          "client_id": client_id,
          "client_secret": client_secret,
          "redirect_uris": ["http://localhost", "urn:ietf:wg:oauth:2.0:oob"],
          "auth_uri": "https://accounts.google.com/o/oauth2/auth",
          "token_uri": "https://accounts.google.com/o/oauth2/token",
      }
  }
  scopes = ["https://www.googleapis.com/auth/tagmanager.edit.containers"]
  flow = InstalledAppFlow.from_client_config(client_config, scopes)
  auth_url, _ = flow.authorization_url()
  print("Please visit this URL to authorise the tool: {}".format(auth_url))
  auth_code = input("Please enter the authorization code: ")
  flow.fetch_token(code=auth_code)
  return flow.credentials


def deploy_cwv_template(gtm_service: discovery.Resource, gtm_parent: str):
  """Deploys the gPS Core Web Vitals Tag.

  Args:
    gtm_service: The Google API Service to deploy the tag with.
  """
  gtm_tag = {
      "name": "gPS Core Web Vitals Template",
      "templateData": cwv_template_data,
  }
  try:
    gtm_service.accounts().containers().workspaces().templates().create(
        parent=gtm_parent, body=gtm_tag
    ).execute()
  except errors.HttpError as err:
    raise SystemExit("Unable to deploy CWV Template.") from err


def main():
  arg_parser = argparse.ArgumentParser(description="Deploys the gPS GTM Tag.")
  arg_parser.add_argument(
      "-a", "--account", type=int, required=True, help="The account ID to use."
  )
  arg_parser.add_argument(
      "-c",
      "--container",
      type=int,
      required=True,
      help="The container ID to use.",
  )
  arg_parser.add_argument(
      "-w",
      "--workspace",
      type=int,
      required=True,
      help="The workspace ID to use.",
  )
  arg_parser.add_argument(
      "-i",
      "--client_id",
      type=str,
      required=True,
      help="The OAuth2 client ID to use in the user authentication flow.",
  )
  arg_parser.add_argument(
      "-s",
      "--client_secret",
      type=str,
      required=True,
      help="The OAuth2 client secret to use in the user authentication flow.",
  )
  args = arg_parser.parse_args()

  gtm_parent = f"accounts/{args.account}/containers/{args.container}/workspaces/{args.workspace}"
  gcp_creds, project_id = google.auth.default()
  if not project_id:
    project_id = os.environ["GOOGLE_CLOUD_PROJECT"]

  enable_tagmanager_api(project_id=project_id, credentials=gcp_creds)

  api_creds = get_oauth_creds(
      client_id=args.client_id, client_secret=args.client_secret
  )
  with discovery.build(
      "tagmanager", "v2", credentials=api_creds
  ) as gtm_service:
    deploy_cwv_template(gtm_service=gtm_service, gtm_parent=gtm_parent)


if __name__ == "__main__":
  main()
