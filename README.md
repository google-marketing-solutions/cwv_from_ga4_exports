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
This solution makes it simple to get started with reporting on Core Web Vitals being exported from GA4 into Big Query.

## Setting up a GCP project
- deploy webvitals.js to site via gtag or GTM and send to GA4
- Create a new GCP project
- Add a billing account (most people forget this) to GCP project
- Enable BQ
- connect GA to BQ in the GA UI
  - there is no API for doing this =(
- wait 24 hours for data to appear
  - need to check this as part of the install script
- run the install script
