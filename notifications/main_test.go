package main

import (
	"io"
	"os"
	"strings"
	"testing"
)

func Test_areCWVValuesGood(t *testing.T) {
	os.Setenv("GOOD_LCP", "2.5")
	os.Setenv("GOOD_CLS", "0.1")
	os.Setenv("GOOD_FID", "0.1")
	data := []struct {
		name        string
		inputLCP    float64
		inputCLS    float64
		inputFID    float64
		expectedLCP bool
		expectedCLS bool
		expectedFID bool
		errMsg      string
	}{
		{
			name:        "All good values",
			inputLCP:    0.1,
			inputCLS:    0.1,
			inputFID:    0.1,
			expectedLCP: true,
			expectedCLS: true,
			expectedFID: true,
			errMsg:      "Not all values returned as 0.0",
		},
		{
			name:        "All poor values",
			inputLCP:    5.0,
			inputCLS:    5.0,
			inputFID:    5.0,
			expectedLCP: false,
			expectedCLS: false,
			expectedFID: false,
			errMsg:      "Not all values returned as inputted",
		},
		{
			name:        "One good value",
			inputLCP:    0.1,
			inputCLS:    5.0,
			inputFID:    5.0,
			expectedLCP: true,
			expectedCLS: false,
			expectedFID: false,
			errMsg:      "Mix of good and poor values not correct",
		},
		{
			name:        "All zeros",
			inputLCP:    0.0,
			inputCLS:    0.0,
			inputFID:    0.0,
			expectedLCP: true,
			expectedCLS: true,
			expectedFID: true,
			errMsg:      "All zeros did not return zeros",
		},
	}

	for _, d := range data {
		t.Run(d.name, func(t *testing.T) {
			lcp, cls, fid := areCWVValuesGood(d.inputLCP, d.inputCLS, d.inputFID)
			if lcp != d.expectedLCP && cls != d.expectedCLS && fid != d.expectedFID {
				t.Errorf("%s (expected/received): LCP %t/%t; CLS %t/%t; FID %t/%t", d.errMsg, d.expectedLCP, lcp, d.expectedCLS, cls, d.expectedFID, fid)
			}
		})
	}

	t.Cleanup(func() {
		os.Unsetenv("GOOD_LCP")
		os.Unsetenv("GOOD_CLS")
		os.Unsetenv("GOOD_FID")
	})
}

func Test_getCwvValues(t *testing.T) {
	t.Skip("Would be bigquery integration test")
}

func Test_getCloudEventDataFromJSON(t *testing.T) {
	goodCE := io.NopCloser(strings.NewReader(`{
    "ProtoPayload": {
      "ServiceName": "bigquery.googleapis.com",
      "MethodName": "google.cloud.bigquery.v2.JobService",
      "MetaData": {
        "TableCreation": {
          "Table": {
            "TableName": "events_12345678"
          }
        }
      }
    }
  }`))

	service, method, tableName := getCloudEventDataFromRequest(goodCE)
	if service != "bigquery.googleapis.com" && method != "google.cloud.bigquery.v2.JobService" && tableName != "events_12345678" {
		t.Errorf("Expected event data not returned: service --> %s; method --> %s; table --> %s", method, service, tableName)
	}

	badCE := io.NopCloser(strings.NewReader(`{
    "ProtoPayload": {
      "ServiceName": "bigquery.googleapis.com",
      "MethodName": "google.cloud.bigquery.v2.JobService",
      "MetaData": {
        "TableUpdate": {
          "Table": {
            "TableName": "events_12345678"
          }
        }
      }
    }
  }`))

	service, method, tableName = getCloudEventDataFromRequest(badCE)
	if service != "bigquery.googleapis.com" && method != "google.cloud.bigquery.v2.JobService" && tableName != "" {
		t.Errorf("Table returned when none expected: %s", tableName)
	}
}
