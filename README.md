Copyright 2024 Google LLC

Licensed under the Apache License, Version 2.0 (the "License"); you may not use
this file except in compliance with the License. You may obtain a copy of the
License at

```
https://www.apache.org/licenses/LICENSE-2.0
```

Unless required by applicable law or agreed to in writing, software distributed
under the License is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR
CONDITIONS OF ANY KIND, either express or implied. See the License for the
specific language governing permissions and limitations under the License

# CWV with GA4 Exports

This solution makes it simple to get started with reporting on Core Web Vitals
being exported from GA4 into Big Query.

## Prerequisites

Before you start, you will require the following:

-   Website performance data from your being sent to GA4. We suggest using the
    [Web Vitals Template for Google Tag Manager](https://github.com/google-marketing-solutions/web-vitals-gtm-template)
    if you don't already have this set up.
-   A Google Analytics 4 account, preferably exporting data to BigQuery.
-   A Google Cloud Project with a billing account associated with it. This
    should be the project you are exporting GA4 data to.

## Using the Solution

### The Information You'll Need

You will need the following information to be able to deploy the solution:

1.  The **ID of your Google Cloud project**. This can be found on the Google
    Cloud dashboard in the Project Info section. Be sure to use the ID, not the
    name.
1.  The **GCP region** you will deploy to. This *must* be the same region you
    are exporting your GA4 data to. To find the region, open BigQuery Studio,
    select your project, and select the analytics dataset in the Explorer (it
    will be named analytics_### where **###** is your GA4 property ID). The GCP
    cloud region is listed in the details under **Data location**.
1.  Your **GA4 Property ID**. This can be found on the GA4 Admin page's Property
    Settings tab in the Property details box. It is also the numbers at the end
    of the BigQuery analytics dataset name.

### Exporting CWV Data to BigQuery

If not already doing so, start exporting the CWV data to BigQuery. Follow the
[directions](https://support.google.com/analytics/answer/9358801) in the GA4
documentation.

When you are setting up the export, you *must* select the daily option. The
daily tables are used by the solution, as well as by the standard dashboards.
The streaming (a.k.a. intraday) tables are optional.

### Deploying the Solution

Once you have CWV data in BigQuery, you can use this solution to create summary
tables in BigQuery and have them regularly updated.

#### Prerequisites

Before you can run the deployment script, you must enable the Cloud Resource
Manager API. To do this:

1.  Open the APIs & Services Library by clicking on **APIs & Services >
    Library** from the sidebar in the Google Cloud Console.
1.  Search for "Resource Manager" using the search field on the library welcome
    page.
1.  From the search results, select the **Cloud Resource Manager API**
1.  Click the **Enable** button on the Product details page.

#### Deployment Steps

To deploy the solution:

1.  Open a command line shell, either on your local computer or by using the
    [Google Cloud Shell](https://cloud.google.com/shell).
    1.  If you are deploying from your local computer:
        1.  Install the Google Cloud SDK by following the
            [instructions for your platform](https://cloud.google.com/sdk/docs/install).
        1.  Update the GCP SDK by running the command `gcloud components
            update`.
1.  Clone the solution git repository using the command `git clone
    https://github.com/google-marketing-solutions/cwv_from_ga4_exports.git`.
1.  Move into the solution directory using the command `cd
    cwv_from_ga4_exports`.
1.  Run the install script with the command `./install`. This will install the
    python packages required and launch the deployment script.
    +   During deployment, when asked if you want to enable Google Cloud
        components and APIs, answer `y`.
    +   At one point you may be asked to open a URL and paste a version_info
        string into the console. This is required to schedule updating the
        materialized table.

The script will print status messages to the console, including errors if any
occur. On error, the script will exit. Otherwise, you will be returned to your
prompt upon successful completion.

#### Updating Your Deployment

To update any of the details you entered during the deployment, including CWV
thresholds, please re-run the install script.

For security reasons, none of the information you enter is saved outside the
deployed container and cannot be reused during subsequent deployments.

### Visualizing Your Data

Once you have the solution deployed, you should see a table named
_web_vitals_summary_ in your GCP project's BigQuery tables. You can use this
table along with [Data Studio](https://datastudio.google.com/) to create
dashboards to visualize your CWV progress.

Since creating good dashboards can be difficult, the Chrome DevRel team has
released the [Web Vitals Connector](https://goo.gle/web-vitals-connector) for
Data Studio. The tables created with this solution are compatible with this
reusable dashboard. For more information, see the
[documentation on web.dev](https://web.dev/vitals-ga4/#using-the-web-vitals-connector).
