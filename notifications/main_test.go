package main

/*
 * Copyright 2021 Google LLC
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *     https://www.apache.org/licenses/LICENSE-2.0
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import (
	"fmt"
	"io"
	"os"
	"strings"
	"testing"
)

func Test_getCloudEventDataFromRequest(t *testing.T) {
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

func Test_getCWVThresholds(t *testing.T) {
	expectedLCP := 1.0
	expectedCLS := 2.0
	expectedFID := 3.0
	// all floats
	os.Setenv("GOOD_LCP", "1.0")
	os.Setenv("GOOD_CLS", "2.0")
	os.Setenv("GOOD_FID", "3.0")
	lcp, cls, fid := getCWVThresholds()
	if lcp != expectedLCP && cls != expectedCLS && fid != expectedFID {
		t.Errorf("Incorrect values returned from env variables when all floats: LCP %f/%f; CLS %f/%f; FID %f/%f", expectedLCP, lcp, expectedCLS, cls, expectedFID, fid)
	}

	// one number without a decimal
	os.Setenv("GOOD_LCP", "1")
	lcp, cls, fid = getCWVThresholds()
	if lcp != expectedLCP && cls != expectedCLS && fid != expectedFID {
		t.Errorf("Incorrect values returned from env variables when LCP has no decimal: LCP %f/%f; CLS %f/%f; FID %f/%f", expectedLCP, lcp, expectedCLS, cls, expectedFID, fid)
	}

	// one set as an invalid string
	os.Setenv("GOOD_LCP", "foobar")
	lcp, cls, fid = getCWVThresholds()
	if lcp != StandardGoodLCP && cls != expectedCLS && fid != expectedFID {
		t.Errorf("Incorrect values returned from env variables when LCP is invalid: LCP %f/%f; CLS %f/%f; FID %f/%f", expectedLCP, lcp, expectedCLS, cls, expectedFID, fid)
	}

	// one unset
	os.Unsetenv("GOOD_LCP")
	lcp, cls, fid = getCWVThresholds()
	if lcp != StandardGoodLCP && cls != expectedCLS && fid != expectedFID {
		t.Errorf("Incorrect values returned from env variables when all 0: LCP %f/%f; CLS %f/%f; FID %f/%f", StandardGoodLCP, lcp, StandardGoodCLS, cls, StandardGoodFID, fid)
	}

	// all unset
	os.Unsetenv("GOOD_CLS")
	os.Unsetenv("GOOD_FID")
	lcp, cls, fid = getCWVThresholds()
	if lcp != StandardGoodLCP && cls != StandardGoodCLS && fid != StandardGoodFID {
		t.Errorf("Incorrect values returned from env variables when all 0: LCP %f/%f; CLS %f/%f; FID %f/%f", StandardGoodLCP, lcp, StandardGoodCLS, cls, StandardGoodFID, fid)
	}

	t.Cleanup(func() {
		os.Unsetenv("GOOD_LCP")
		os.Unsetenv("GOOD_CLS")
		os.Unsetenv("GOOD_FID")
	})
}

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

func Test_sendAlertEmail(t *testing.T) {
	t.Skip("Would be testing net/smtp API")
}

func Test_createEmailMessage(t *testing.T) {
	os.Setenv("GOOD_LCP", "1")
	os.Setenv("GOOD_CLS", "1")
	os.Setenv("GOOD_FID", "1")

	emailTo := "receiver@example.com"
	emailFrom := "sender@example.com"

	// all poor metrics
	expectedEmail := fmt.Sprintf(EmailMessageHeader, emailFrom, emailTo) +
		"LCP of 10 ms is 1000% of 1 ms budget.\r\n" +
		"CLS of 10 is 1000% of 1 budget.\r\n" +
		"FID of 10 ms is 1000% of 1 ms budget.\r\n" +
		EmailHTMLStart +
		"<tr><td style=\"background: lightgray; font-weight: bolder; text-align: center\">LCP</td><td>10ms</td><td>1ms</td><td style=\"color: red\">1000%</td></tr>" +
		"<tr><td style=\"background: lightgray; font-weight: bolder; text-align: center\">CLS</td><td>10</td><td>1</td><td style=\"color: red\">1000%</td></tr>" +
		"<tr><td style=\"background: lightgray; font-weight: bolder; text-align: center\">FID</td><td>10ms</td><td>1ms</td><td style=\"color: red\">1000%</td></tr>" +
		EmailHTMLEnd

	email := createEmailMessage(emailFrom, emailTo, 10.0, 10.0, 10.0)
	if string(email) != expectedEmail {
		t.Error("Email not as expected with all poor metrics.")
	}
	// one poor metric
	expectedEmail = fmt.Sprintf(EmailMessageHeader, emailFrom, emailTo) +
		"CLS of 10 is 1000% of 1 budget.\r\n" +
		EmailHTMLStart +
		"<tr><td style=\"background: lightgray; font-weight: bolder; text-align: center\">CLS</td><td>10</td><td>1</td><td style=\"color: red\">1000%</td></tr>" +
		EmailHTMLEnd

	email = createEmailMessage(emailFrom, emailTo, 0.0, 10.0, 0.0)
	if string(email) != expectedEmail {
		t.Error("Email not as expected with one poor metric.")
	}

	t.Cleanup(func() {
		os.Unsetenv("GOOD_LCP")
		os.Unsetenv("GOOD_CLS")
		os.Unsetenv("GOOD_FID")
	})
}
