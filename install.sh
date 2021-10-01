#!/bin/bash

# Deploys the SQL tables and scripts needed to collect CWVs according to the 
# standard set in https://web.dev/vitals-ga4/ as well as a cloud run function
# for alerting.

set -e # stop on error
set -u # on unset variables allowed
\unalias -a # don't use the user's aliases
set -x

# save the current working dir and then cd into the script's dir
readonly original_dir=${PWD}
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}" )" && pwd)"

# Get all of the info we need
readonly gcp_project=$(gcloud config get-value project)
read -p "Is ${gcp_project} the correct project? (y/N) " is_correct_project
if [[ ! $is_correct_project =~ [yY] ]]; then
  echo 'Please udapte your project using the command "gloud config set project 
<project name>" and start again.'
  exit 1
fi

read -p 'What is the ID of your GA propery? ' ga_property
if [[ ! ${ga_property} =~ ^[0-9]+$ ]]; then
  echo 'Only GA4 properties are supported at this time. Please check your 
property ID and try again.'
  exit 1
fi

# replace the values in the files to be deployed
if [[ -d deployment_files ]]; then
  rm -r deployment_files
fi
mkdir deployment_files

gcp_replace="s/<PROJECT_ID>/${gcp_project}/g" 
ga_replace="s/<GA_ID>/${ga_property}/g" 
for sql_file in ./sql/*.sql; do
  sed -e ${gcp_replace} -e ${ga_replace} ${sql_file} \
  > deployment_files/$(basename ${sql_file});
done

# deploy the files
bq='bq query --use_legacy_sql=false'
for d_file in ./deployment_files/*.sql; do
  if ! ${bq} < ${d_file}; then
    echo "Error deploying ${d_file} to bigquery" >&2
    exit 1
  fi
done

# clean up
rm -r deployment_files
cd ${original_dir}
