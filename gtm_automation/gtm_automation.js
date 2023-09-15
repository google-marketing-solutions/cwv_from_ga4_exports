/*
  Copyright 2023 Google LLC

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

  http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
*/
/**
 * @fileoverview Provides the functions to deploy the tags required to track
 * Core Web Vitals in GA4 to Google Tag Manager.
 *
 * The gPS Core Web Vitals tag add the [web-vitals](https://github.com/GoogleChrome/web-vitals)
 * library to the page, and sets up the callbacks for when CWV metrics are
 * reported. The callbacks push the CWV measurement to the data layer as an
 * event in the following format:
 *   ```
 *     {
 *      event: 'core-web-vitals',
 *      core_web_vitals_measurement: {
 *        metric_name: string,
 *        metric_id: string,
 *        metric_rating: string,
 *        metric_value: number,
 *        value: number,
 *        attribution: string
 *      }
 *     }
 *   ```
 * where the attribution property is a stringified JSON representation of the
 * attribution object passed from the webvitals library.
 *
 * The gPS Core Web Vitals GA4 Event Tag is a Google Analytis 4 Event tag that
 * is triggered when a core-web-vitals event happens. The tag forwards the CWV
 * data to GA4 as an event with the form:
 *   ```
 *     Event Name: The name of the CWV being reported
 *     Event Parameters:
 *       name: metric_name     value: the metric being reported (e.g. LCP)
 *       name: metric_id       value: unique ID used to aggregate events
 *       name: metric_rating   value: string rating of the value (e.g. 'good')
 *       name: metric_value    value: the numeric value of the metric
 *       name: value           value: delta between measurements to allow summing
 *       name: attribution     value: stringified JSON of the attribution object
 *   ```
 *
 * The workflow must be run from start to finish without error. This means that
 * if an error occurs partway through deployment, everything already added to
 * GTM will need to be removed before the workflow can be run again.
 */

// The OAuth token client used to authenticate API calls.
let tokenClient;
// The trigger ID of the custom event trigger used to trigger the GA4 Event Tag.
let customEventTriggerId;

/**
 * Adds a message to the success-messages div on the page.
 *
 * @param {string} message The message to add to the page.
 */
function addSuccessMessage(message) {
  const successDiv = document.getElementById('success-messages');
  successDiv.innerHTML += message + '<br>';
}

/**
 * Adds a message to the error-messages div on the page.
 *
 * @param {string} message The error message to add to the page.
 */
function addErrorMessage(message) {
  const errorDiv = document.getElementById('error-messages');
  errorDiv.innerHTML += message + '<br>';
}

/**
 * Runs the authorization flow to allow the app to use the GTM API. If completed
 * successfully, deployTag() is called.
 *
 * The user will be asked in a pop-up to choose an account to authorise with,
 * and then asked to allow the app to edit GTM containers.
 *
 * The success-messages and error-messages divs are also cleared.
 *
 * @param {Event} event The event that triggers the function. This event is
 *                      ignored.
 */
function authorizeApp(event) {
  document.getElementById('success-messages').innerHTML = '';
  document.getElementById('error-messages').innerHTML = '';
  event.preventDefault();
  const clientId = document.getElementById('client-id').value;
  tokenClient = google.accounts.oauth2.initTokenClient({
    client_id: clientId,
    scope: 'https://www.googleapis.com/auth/tagmanager.edit.containers',
    callback: '',
  });
  gapi.load('client', () => {
    gapi.client.init({})
      .then(function () {
        gapi.client.load('https://tagmanager.googleapis.com/$discovery/rest?version=v2');
      })
      .then(deployTag());
  });
}

/**
 * Deploys the gPS Core Web Vitals Tag to the GTM workspace entered into the
 * form on the accompanying webpage. The tag is triggered once on all page
 * loads.
 *
 * If completed successfully, a message is added to the web page and
 * deployEventTrigger() is called. If the tag creation fails, an error message
 * is added to the web page and the script stops.
 */
function deployTag() {
  tokenClient.callback = (resp) => {
    if (resp.error !== undefined) {
      throw (resp);
    }
    gtmAccount = document.getElementById('account').value;
    gtmContainer = document.getElementById('container').value;
    gtmWorkspace = document.getElementById('workspace').value;
    gtmParent = `accounts/${gtmAccount}/containers/${gtmContainer}/workspaces/${gtmWorkspace}`;
    gapi.client.tagmanager.accounts.containers.workspaces.tags.create({
      parent: gtmParent,
      name: 'gPS Core Web Vitals Tag',
      type: 'html',
      parameter: [
        {
          type: 'template',
          key: 'html',
          value: cwvTagValue,
        },
        {
          'type': 'boolean',
          key: 'supportDocumentWrite',
          value: 'false',
        },
      ],
      // Trigger ID for the standard "All Pages" trigger
      firingTriggerId: [
        "2147479553"
      ],
      tagFiringOption: "oncePerEvent",
    })
      .then((gtmResp) => {
        addSuccessMessage('Deployed GTM Tag.');
        deployEventTrigger(gtmParent);
      })
      .catch((err) => {
        addErrorMessage('Error deploying GTM Tag: ' + err.result.error.details[0].detail);
      });
  };
  if (gapi.client.getToken() === null) {
    tokenClient.requestAccessToken({ prompt: 'consent' });
  } else {
    tokenClient.requestAccessToken({ prompt: '' });
  }
}

/**
 * Deploys the custom event trigger fired when a core-web-vitals event is pushed
 * to the data layer. If completed successfully, deployDataLayerVariables is
 * called. If the creation fails, an error message is added to the web page and
 * the script stops.
 *
 * @param {string} gtmParent The parent path of the workspace to deploy to.
 */
function deployEventTrigger(gtmParent) {
  gapi.client.tagmanager.accounts.containers.workspaces.triggers.create({
    parent: gtmParent,
    name: 'gPS Core Web Vitals Event Trigger',
    type: 'customEvent',
    customEventFilter: [
      {
        type: 'equals',
        parameter: [
          {
            type: 'template',
            key: 'arg0',
            value: '{{_event}}',
          },
          {
            type: 'template',
            key: 'arg1',
            value: 'core-web-vitals',
          },
        ],
      },
    ],
  })
    .then((gtmResp) => {
      addSuccessMessage('Deployed custom event trigger.');
      customEventTriggerId = gtmResp.result.triggerId;
      deployDataLayerVariables(gtmParent);
    })
    .catch((err) => {
      addErrorMessage('Error deploying GTM Event Trigger: ' + err.result.error.details[0].detail);
    });
}

/**
 * Creates the data layer variables used to store the core web vitals
 * measurements in for use with the GA4 event tag. The variables are all
 * prefixed with `core_web_vitals_measurement`.
 *
 * If completed successfully, a message is added to the web page and
 * deployGA4EventTag() is called. If an error occurs, a message is added to the
 * web page and the script stops.
 *
 * @param {string} gtmParent The parent path of the workspace to deploy to.
 */
function deployDataLayerVariables(gtmParent) {
  const variableNames = [
    'metric_name',
    'metric_id',
    'metric_rating',
    'metric_value',
    'value',
    'attribution',
  ];

  count = 0;
  for (const name of variableNames) {
    gapi.client.tagmanager.accounts.containers.workspaces.variables.create({
      parent: gtmParent,
      resource: {
        name: 'core-web-vitals - ' + name,
        type: 'v',
        formatValue: {},
        parameter: [
          {
            type: 'integer',
            key: 'dataLayerVersion',
            value: '2',
          },
          {
            type: 'boolean',
            key: 'setDefaultValue',
            value: 'false',
          },
          {
            type: 'template',
            key: 'name',
            value: 'core_web_vitals_measurement.' + name,
          },
        ],
      }
    })
      .then((gtmResp) => {
        addSuccessMessage('Deployed data layer variable - ' + name);
        if (++count === variableNames.length) {
          deployGA4EventTag(gtmParent);
        }
      })
      .catch((err) => {
        addErrorMessage('Error deploying GTM Variable: ' + err.result.error.details[0].detail);
      });
  }
}

/**
 * Deploys the GA4 Event tag that sends core-web-vitals events to GA4. The tag
 * is triggered using the custom even trigger deployed in `deployEventTrigger`.
 *
 * If completed successfully, an completion message is added to the web page. If
 * an error occurs, an error message is added to the web page and the script
 * stops.
 *
 * @param {string} gtmParent The parent path of the workspace to deploy to.
 */
function deployGA4EventTag(gtmParent) {
  const ga4Id = document.getElementById('ga4').value;
  gapi.client.tagmanager.accounts.containers.workspaces.tags.create({
    parent: gtmParent,
    name: 'gPS Core Web Vitals GA4 Event Tag',
    type: 'gaawe',
    firingTriggerId: [
      customEventTriggerId,
    ],
    tagFiringOption: "oncePerEvent",
    parameter: [
      {
        type: 'template',
        key: 'measurementId',
        value: 'none',
      },
      {
        type: 'template',
        key: 'measurementIdOverride',
        value: ga4Id,
      },
      {
        type: 'template',
        key: 'eventName',
        value: '{{core-web-vitals - metric_name}}'
      },
      {
        type: 'list',
        key: 'eventParameters',
        list: [
          {
            type: 'map',
            map: [
              {
                type: 'template',
                key: 'name',
                value: 'metric_name',
              },
              {
                type: 'template',
                key: 'value',
                value: '{{core-web-vitals - metric_name}}'
              },
            ],
          },
          {
            type: 'map',
            map: [
              {
                type: 'template',
                key: 'name',
                value: 'metric_id',
              },
              {
                type: 'template',
                key: 'value',
                value: '{{core-web-vitals - metric_id}}'
              },
            ],
          },
          {
            type: 'map',
            map: [
              {
                type: 'template',
                key: 'name',
                value: 'metric_rating',
              },
              {
                type: 'template',
                key: 'value',
                value: '{{core-web-vitals - metric_rating}}'
              },
            ],
          },
          {
            type: 'map',
            map: [
              {
                type: 'template',
                key: 'name',
                value: 'metric_value',
              },
              {
                type: 'template',
                key: 'value',
                value: '{{core-web-vitals - metric_value}}'
              },
            ],
          },
          {
            type: 'map',
            map: [
              {
                type: 'template',
                key: 'name',
                value: 'value',
              },
              {
                type: 'template',
                key: 'value',
                value: '{{core-web-vitals - value}}'
              },
            ],
          },
          {
            type: 'map',
            map: [
              {
                type: 'template',
                key: 'name',
                value: 'attribution',
              },
              {
                type: 'template',
                key: 'value',
                value: '{{core-web-vitals - attribution}}'
              },
            ],
          },
        ]
      },
    ],
  })
    .then((gtmResp) => {
      addSuccessMessage('Deployed GA4 Event Tag');
      addSuccessMessage('<br><strong>All Done!</strong>');
      addSuccessMessage(`Please open <a href="https://tagmanager.google.com/#/container/${gtmParent}"> your GTM Workspace</a>, check that no changes conflict with existing work, and then submit and publish the workspace to complte the setup.`)
    })
    .catch((err) => {
      addErrorMessage('Error deploying GA4 Event Tag: ' + err.result.error.details[0].detail);
    });
}

// add event listener to the submit button on the page.
document.getElementById('deploy-form').addEventListener('submit', authorizeApp);

// The content of the custom HTML tag begin deployed to GTM that will collect
// Core Web Vitals data.
const cwvTagValue = `
<script src="https://unpkg.com/web-vitals@3/dist/web-vitals.attribution.iife.js" ></script>
<script>
/**
 * Extracts the CWV data from the object passed by web-vitals.
 *
 * @param event The event object passed by web-vitals when this is used as a
 *              callback.
 *
 * @returns A new object with the CWV data.
 */
function extractCWVData(metric) {
  var cwvData = {
    metric_name: metric.name,
    metric_id: metric.id,
    metric_rating: metric.rating,
    metric_value: metric.value,
    value: metric.delta,
    attribution: JSON.stringify(metric.attribution),
  };
  return cwvData;
}

/** Pushes a CWV measurement object to the GTM data layer.
 *
 * @param event An object returned from extractCWVData.
 */
function pushToDataLayer(metric) {
  dataLayer.push({
    event: 'core-web-vitals',
    core_web_vitals_measurement: extractCWVData(metric)
  });
}

webVitals.onCLS(pushToDataLayer);
webVitals.onFID(pushToDataLayer);
webVitals.onLCP(pushToDataLayer);
webVitals.onINP(pushToDataLayer);
webVitals.onTTFB(pushToDataLayer);
console.log('CWV Tag Ready');

</script>
`;
