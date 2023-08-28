Copyright 2021 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License

# Deploying CWV with GA4

This solution makes it simple to get started with reporting on Core Web Vitals 
being exported from GA4 into Big Query.

Deploying the solution is a two-part process. In the first part, a custom HTML
tag is deployed to GTM. This facilitates the actual collection of the CWV data.
In the second step, the SQL needed to turn the GA4 events in BigQuery into easy
to use tables is deployed and scheduled. The optional email alerting can also be
deployed at this time.

## Prerequisites

### Before You Start

Before you start, you will require the following:

-   A Google Tag Manager Account linked to the website you will be measuring.
-   A Google Analytics 4 account, preferably exporting data to BigQuery.
-   A Google Cloud Project with a billing account associated with it. This
    should be the account you are exporting GA4 data to, if you already are.
-   (_Optional_) An SMTP (i.e. email) server 

## Part 1

In the first part, the tags, triggers, and variables necessary for collecting
CWV data and forwarding it to GA4 are deployed to GTM.

### The Information You'll Need

You will need the following information to deploy to GTM:

1.  The OAuth Client ID to use when authenticating (see [Getting an
    OAuth ID](#getting-an-oauth-id) for more information).
1.  The Google Tag Manager Account ID, Container ID, and Workspace ID
    for where the tag will be deployed to.
1.  The GA4 Measurement ID of the GA4 property to send the CWV
    measurements to.

To find your GTM workspace details, open tagmanager.google.com, choose the
container you plan to deploy the solution to, and check the URL in the browser.
It will have the form
https://tagmanager.google.com/#/container/accounts/&lt;ACCOUNT
ID&gt;/containers/&lt;CONTAINER ID&gt;/workspaces/&lt;WORKSPACE ID&gt;, where
the IDs you need are the numbers in place of the "&lt;SOMETHING ID&gt;" fields.

To find your GA4 measurement ID, open Google Analytics and choose the property
you will sending the CWV measurements to. The ID can be found under Settings >>
Data Streams >> Web, and then choose the stream you want to send the measurements
to. The Measurement ID is on the far right of the _Stream details_ box, and
should start with a "G-".

#### Getting an OAuth ID

An OAuth ID is required to authenticate with the GTM API when deploying the GTM
tags, etc. Before creating an OAuth ID, you will need to decide where you will
be hosting the solution web page. If you will be using you local computer, this
is local host. Otherwise, you will need the fully qualified domain name of the
server you will be using (i.e. everything after the http:// or https://, e.g.
stuff.example.com).

To create the OAuth ID, open the Google Cloud Project you will be using to store
your CWV data in BigQuery. From the overflow menu (aka hamburger menu), choose
_APIs & Services_ >> _OAuth consent screen_, then follow these steps:

1. 

## Part 2

### The Information You'll Need

You will need all of the following information to be able to deploy the 
solution:

1.  The ID of your Google Cloud project. This can be found on the Google Cloud 
    dashboard in the Project Info section. Be sure to use the ID, not the name.
1.  Your GA4 Property ID. This can be found on the Admin page's Property 
    Settings tab in the Property details box.
1.  Your Core Web Vitals performance budget. You will need this to set the 
    thresholds for when an alert email is sent.
1.  If deploying the email alerting service, the details for your SMTP server. 
This includes:
    +   the server's address.
    +   the username and password to use when authenticating with the server.
    +   the email address to use as the alert sender.
    +   the email addresses to send the alert to.
    
## Getting Core Web Vitals into BigQuery

For the solution to work, you first need to report CWV metrics to
GA4. From GA4, the data then needs to be exported to BigQuery.

### Sending CWV Data to GA4

The standard way to send CWV data to GA4 is by using 
[the web-vitals JavaScript library](https://github.com/GoogleChrome/web-vitals).
Follow the instructions on 
[using gtag.js](https://github.com/GoogleChrome/web-vitals#using-gtagjs-google-analytics-4) 
to send the metrics to GA4, or 
[the tutorial](https://www.simoahava.com/analytics/track-core-web-vitals-in-ga4-with-google-tag-manager/) 
on sending the metrics to GA via GTM.

If sending metrics directly to GA4, please use the naming convention specified
by Simo Ahava in the instructions for using GTM. This means that the event
parameters should be named

* `web_vitals_measurement_name` for the metric name
* `web_vitals_measurement_id` for the metric id
* `web_vitals_measurement_value` for the metric value
* `value` for the metric delta

If you use other parameter names, you will need to update [deploy.py])https://github.com/google-marketing-solutions/cwv_from_ga4_exports/blob/main/deploy.py)
to match the names you have chosen.

**Please Note:** If you use a custom solution for reporting CWV data, please be
sure to ensure the resulting tables in BigQuery match those that would be 
present if you were using the standard reporting.

### Exporting CWV Data to BigQuery

To export the CWV data to BigQuery, follow the 
[directions](https://support.google.com/analytics/answer/9358801) in the GA4 
documentation. 

When you are setting up the export, you _must_ select the daily option. The 
daily tables are used by the solution, as well as by the standard dashboards. 
The streaming (a.k.a. intraday) tables are optional.

## Deploying the Solution

Once you have CWV data in BigQuery, you can use this solution to create summary
tables in BigQuery and send alert emails when the CWV values don't meet your 
targets.

### Deployment Steps

To deploy the solution:

1.  Open a command line shell, either on your local computer or by using the 
    [Google Cloud Shell](https://cloud.google.com/shell).
    1.  If you are deploying from your local computer:
        1.  Install the Google Cloud SDK by following the 
            [instructions for your platform](https://cloud.google.com/sdk/docs/install).
        1.  Update the GCP SDK by running the command `gcloud components update`.
1.  Clone the solution git repository.
1.  Run the install script.
    +   During deployment, when asked if you want to enable Google Cloud 
        components and APIs, answer `y`.
    +   At one point you may be asked to open a URL and paste a version_info 
        string into the console. This is required to schedule updating the 
        materialized table.

The script will print status messages to the console, including errors if any
occur. On error, the script will exit. Otherwise, you will be returned to your 
prompt upon successful completion.

**Please Note:** Deploying the Cloud Run function for the first time can take a
significant amount of time (up to 30 minutes). Please be sure that your 
connection will not timeout during the first deployment.

### Updating Your Deployment

To update any of the details you entered during the deployment, including CWV 
thresholds, please re-run the install script. 

For security reasons, none of the
information you enter is saved outside the deployed container and cannot be 
reused during subsequent deployments.

## Visualizing Your Data

Once you have the solution deployed, you should see a table named 
_web_vitals_summary_ in your GCP project's BigQuery tables. You can use this 
table along with [Data Studio](https://datastudio.google.com/) to create 
dashboards to visualize your CWV progress.

Since creating good dashboards can be difficult, the Chrome DevRel team has 
released the [Web Vitals Connector](https://goo.gle/web-vitals-connector) for 
Data Studio. The tables created with this solution are compatible with this 
reusable dashboard. For more information, see the 
[documentation on web.dev](https://web.dev/vitals-ga4/#using-the-web-vitals-connector).
