-- Creates a stored procedure that retrieves the p75 values for the given date
-- range.

CREATE OR REPLACE
  PROCEDURE analytics_<GA_ID>.get_cwv_p75_for_date(start_date date, num_days INT64) BEGIN
SELECT
  metric_name, APPROX_QUANTILES(metric_value, 100)[OFFSET(75)] AS p75, COUNT(1) AS count
FROM `<PROJECT_ID>.analytics_<GA_ID>.web_vitals_summary`
WHERE
  PARSE_DATE('%Y%m%d', event_date)
  BETWEEN DATE_SUB(start_date, INTERVAL num_days DAY)
  AND DATE_SUB(start_date, INTERVAL 1 DAY)
GROUP BY 1;

END
