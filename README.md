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
to use tables is deployed and scheduled.

## Prerequisites

Before you start, you will require the following:

-   A Google Tag Manager Account linked to the website you will be measuring.
-   A Google Analytics 4 account, preferably exporting data to BigQuery.
-   A Google Cloud Project with a billing account associated with it. This
    should be the project you are exporting GA4 data to, if you already are.

You also need to enable the tagmanager API for your Cloud Project. See the next
section, [Enabling the tagmanager API](#enabling-the-tagmanager-api) for more
information.

### Enabling the tagmanager API

Enabling the tagmanager API for your Google Cloud project is necessary for
allowing the solution to make changes to your Tag Manager workspaces. To enable
the API, follow these steps:

1.  Open the Google Cloud Console and navigate to the APIs & Services page
    ([link](https://console.cloud.google.com/apis/dashboard))
1.  Click the **+ ENABLE APIS AND SERVICES** button at the top of the page.
1.  Using the search box at the top of the page, search for _Tag Manager API_
1.  Click the resulting card labeled **Tag Manager API**
1.  Click the **ENABLE** button to enable the API.

You may need to wait a few minutes for the API to be usable after enabling it.

## Part 1 - Setting up GTM

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

#### Getting an OAuth ID

An OAuth ID is required to authenticate with the GTM API when deploying the GTM
tags, etc. Before creating an OAuth ID, you will need to decide where you will
be hosting the solution web page. If you will be using you local computer, this
is localhost. Otherwise, you will need the fully qualified domain name of the
server you will be using (i.e. everything after the http:// or https://, e.g.
stuff.example.com).

To create the OAuth ID, open the Google Cloud Project you will be using to store
your CWV data in BigQuery. From the overflow menu (aka hamburger menu), choose
_APIs & Services_ >> _OAuth consent screen_, then follow these steps:

1.  On the first page of the OAuth Consent Screen set up, choose the _Internal
    User_ type and click the **Create** button.
1.  Fill in the _App name_, _User support email_, and _Developer contact
    information > Email address_ fields in the form. Click the **+ ADD DOMAIN**
    button and add `http://localhost:<PORT NUMBER>` replacing &lt;PORT
    NUMBER&gt; with the port you will run your webserver on locally (often 8000
    or 8080). If you plan on serving the page on a public webserver, us the
    address of that webserver instead.
1.  Click the **Save and Continue** button and then, on the Scopes page, click
    **Save and Continue** again.

Once you have configured the OAuth consent screen, you can create the actual
OAuth Client ID. To do so,

1.  Open the _Credentials_ page in the GCP console.
1.  Click the **+ CREATE CREDENTIALS** button at the top of the page.
1.  Choose _OAuth Client ID_ from the menu.
1.  Choose _Web application_ as the application type.
1.  Name your client ID something meaningful to you. This will not be shown
    publicly.
1.  Use the **+ADD URI** button to add the origin you will be serving the
    application from. If serving from your local computer, this should be
    `localhost`. If you are hosting this on a public server, it will be that
    server’s domain. Don’t forget to add http:// or https:// and the port you
    will be serving from (e.g. http://localhost:8080).
1.  Click the **Save** button to finish.

### Serving the Solution Website

There are a number of ways to serve the solution website. The simplest is to use
your local computer. Below are two ways you can do that from the command line.

Once you have started serving the website open the URL in your browser. For
example, if you are serving the site from your computer on port 8080, open the
URL http://localhost:8080.

#### Using Python
1.  Move to the directory you downloaded the solution to using (e.g. `cd
    cwv_from_ga4_exports`)
1.  Type `python -m http.server <PORT>` where &lt;PORT&gt; is the port number
    specified when setting up the OAuth Client ID.

#### Using NodeJS
1.  Install the http-server module by typing `sudo npm i -g http-server`
1.  Move to the directory you downloaded the solution to.
1.  Type `http-server . -p <PORT>` where &lt;PORT&gt; is the port number
    specified when setting up the OAuth Client ID.

### Using the Solution to Deploy to GTM

On the solution webpage, fill in the form and click the **Deploy GTM Tag**
button. When asked, authorize the app to make changes to your GTM workspace
(this may be asked multiple times).

You can find the information you need in the following places:

<dl> <dt>OAuth Client ID</dt> <dd>Found in the GCP Console >> API &amp; Services
>> Credentials (created in [Getting an OAuth ID](#getting-an-oauth-id))</dd>
<dt>GTM Account, Container, &amp; Workspace IDs</dt> <dd>Found in the URL to
your GTM workspace and are the numbers after the words <em>accounts</em>, <em>containers</em>,
&amp; <em>workspaces</em>, respectively.</dd> <dt>GA4 Measurement ID</dt> <dd>Found in
your GA4 property >> Admin >> Data Streams >> the details for the Web Stream
being used to collect the data. It will start with "G-".</dd> </dl>

As the parts are deployed, success messages will be displayed on the page. Once
the **All Done** message is displayed, open the GTM workspace you deployed to in
your browser. Check if all of the changes are acceptable and don't conflict with
anything else you're currently working on. If everything is good, submit the
changes and deploy the new version of the GTM container to start collecting Core
Web Vitals for your website.

## Part 2 - Setting up BiqQuery

### The Information You'll Need

You will need the following information to be able to deploy the solution:

1.  The **ID of your Google Cloud project**. This can be found on the Google Cloud 
    dashboard in the Project Info section. Be sure to use the ID, not the name.
1.  The **GCP region** you will deploy to. This _must_ be the same region you are
    exporting your GA4 data to. To find the region, open BigQuery Studio, select
    your project, and select the analytics dataset in the Explorer (it will be
    named analytics_### where __###__ is your GA4 property ID). The GCP cloud
    region is listed in the details under __Data location__.
1.  Your **GA4 Property ID**. This can be found on the Admin page's Property
    Settings tab in the Property details box. It is also the numbers at the end
    of the BigQuery analytics dataset name.
    
### Exporting CWV Data to BigQuery

If not already doing so, start exporting the CWV data to BigQuery. Follow the 
[directions](https://support.google.com/analytics/answer/9358801) in the GA4 
documentation. 

When you are setting up the export, you _must_ select the daily option. The 
daily tables are used by the solution, as well as by the standard dashboards. 
The streaming (a.k.a. intraday) tables are optional.

### Deploying the Solution

Once you have CWV data in BigQuery, you can use this solution to create summary
tables in BigQuery and send alert emails when the CWV values don't meet your 
targets.

#### Prerequisites

Before you can run the deployment script, you must enable the Cloud Resource Manager API. To do this:

1.  Open the APIs & Services Library by clicking on __APIs & Services > Library__ from the sidebar in the Google Cloud Console.
1.  Search for "Resource Manager" using the search field on the library welcome page.
1.  From the search results, select the **Cloud Resource Manager API**
1.  Click the **Enable** button on the Product details page.

#### Deployment Steps

To deploy the solution:

1.  Open a command line shell, either on your local computer or by using the 
    [Google Cloud Shell](https://cloud.google.com/shell).
    1.  If you are deploying from your local computer:
        1.  Install the Google Cloud SDK by following the 
            [instructions for your
            platform](https://cloud.google.com/sdk/docs/install).
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

For security reasons, none of the
information you enter is saved outside the deployed container and cannot be 
reused during subsequent deployments.

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
