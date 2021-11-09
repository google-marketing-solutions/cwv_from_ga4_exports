// Provides a Google Cloud Run function that sends email notifications if Core
// Web Vital (CWV) values drop below a defined threshold.
//
// The Core Web Vitals are a set of metrics designed to measure the performance
// of websites based on user experience. They are
//   - Largest Contentful Paint (LCP)
//   - Cumulative Layout Shift (CLS)
//   - First Input Delay (FID)
// For more information on CWV, see https://web.dev/vitals
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/smtp"
	"os"
	"regexp"
	"strconv"
	"strings"
	"time"

	"cloud.google.com/go/bigquery"
	"golang.org/x/oauth2/google"
	"google.golang.org/api/compute/v1"
	"google.golang.org/api/iterator"
)

// The standard values for a good score according to the Chrome DevRel team.
// The values are:
//   - Largest Contentful Paint  2500 ms
//   - Cumulative Layout Shift   0.1
//   - First Input Delay         100 ms
// For more information see https://web.dev/vitals
const StandardGoodLCP = 2500.0 // ms
const StandardGoodCLS = 0.1    // unitless
const StandardGoodFID = 100.0  // ms

// The top of the email message. The from and to addresses need to be filled in.
// Exported for ease of testing.
var EmailMessageHeader = strings.Join([]string{
	"From: CWV Alerter <%s>",
	"To: %s",
	"Subject: Core Web Vitals are not meeting thresholds",
	"MIME-Version: 1.0",
	"Content-Type: multipart/alternative; boundary=\"part_boundary\"",
	"",
	"--part_boundary",
	"Content-Type: text/plain; charset=\"UTF-8\"",
	"Content-Transfer-Encoding: quoted-printable",
	"",
	"Your Core Web Vitals values are not meeting your budgeted values:",
	""}, "\r\n")

// The start of the html part of the email.
var EmailHTMLStart = strings.Join([]string{
	"",
	"--part-boundary",
	"Content-Type: text/html; charset=\"UTF-8\"",
	"Content-Transfer-Encoding: quoted-printable",
	"",
	"<h1>Core Web Vitals Alert</h1>",
	"<p>Your Core Web Vitals scores are not meeting your budgeted values:</p>",
	"<table style=\"border-spacing: 0.5em\">",
	"<caption>Core Web Vitals Issues</caption>",
	"<thead><tr><th>Metric</th><th>Value</th><th>Budget</th><th>% Over</th></tr></thead>",
	"<tbody>",
}, "\r\n")

// The end of the html part of the email and the end of the email as a whole.
var EmailHTMLEnd = strings.Join([]string{
	"</tbody></table>",
	"--part-boundary--",
	"",
}, "\r\n")

// cloudEvent represents the body of an Eventarc event. Only the parts of the
// event that are required to determine if it's an event we're interested in
// are included.
type cloudEvent struct {
	ProtoPayload struct {
		ServiceName  string
		MethodName   string
		ResourceName string
		Metadata     struct {
			TableCreation struct {
				Table struct {
					TableName string
				}
			}
		}
	}
}

type cwvMeasurement struct {
	Metric_name string
	P75         float64
	Count       int
}

// main is the entry point for the Cloud Run function. An http server is started
// and waits for a request, which is then handed off to the handler.
func main() {
	log.Print("Starting Server...")
	http.HandleFunc("/", handler)
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
		log.Printf("Defaulting to port %s", port)
	}
	if err := http.ListenAndServe(":"+port, nil); err != nil {
		log.Fatal(err)
	}
}

// handler decodes the request and checks if the event is a Big Query insert
// event for GA daily export tables. If so, it checks for a significant
// regression in the CWV values and sends an email if one is found.
func handler(writer http.ResponseWriter, req *http.Request) {
	log.Print("Starting request handler")
	if contentType := req.Header.Get("Content-Type"); !strings.HasPrefix(contentType, "application/json") {
		log.Printf("Received bad request with content-type %s", contentType)
		writer.WriteHeader(http.StatusUnsupportedMediaType)
		body := []byte(fmt.Sprint(http.StatusUnsupportedMediaType) + ": Content-Type must be application/json")
		writer.Write(body)
		return
	}

	service, method, tableName := getCloudEventDataFromRequest(req.Body)
	isGoodTable, _ := regexp.MatchString(`events_\d{8}`, tableName)

	if service == "bigquery.googleapis.com" && method == "google.cloud.bigquery.v2.JobService.InsertJob" && isGoodTable {
		lcp, cls, fid := getCWVValues(time.Now(), 7)
		goodLCP, goodCLS, goodFID := areCWVValuesGood(lcp, cls, fid)
		if !goodLCP || !goodCLS || !goodFID {
			if err := sendAlertEmail(lcp, cls, fid); err != nil {
				log.Fatal("Problem sending alert mail: ", err)
			}
		}
	}
}

// getProjectID returns the current GCP project ID
func getProjectID() string {
	context := context.Background()
	credentials, err := google.FindDefaultCredentials(context, compute.ComputeScope)
	if err != nil {
		fmt.Println(err)
	}
	return credentials.ProjectID
}

// getCloudEventDataFromJson takes an http Request Body containing a cloud event
// JSON object, decodes the JSON to a cloudEvent struct, and then returns the
// ProtoPayload.ServiceName, ProtoPayload.MethodNane, and the TableName if the
// event was for a TableCreation.
func getCloudEventDataFromRequest(req io.ReadCloser) (string, string, string) {
	event := cloudEvent{}
	jsonDecoder := json.NewDecoder(req)
	if err := jsonDecoder.Decode(&event); err != nil {
		log.Fatal("Problem decoding request body: ", err)
	}
	service := event.ProtoPayload.ServiceName
	method := event.ProtoPayload.MethodName
	// Used instead of the resource because we need a TableCreation event, which
	// will not be present for other events for the table.
	tableName := event.ProtoPayload.Metadata.TableCreation.Table.TableName

	return service, method, tableName
}

// getCWVThresholds retrieves the Core Web Vital metric thresholds defined in
// the GOOD_LCP, GOOD_CLS, and GOOD_FID environment variables. If the threshold
// is not set, the standard values from the Chrome DevRel team (defined at the
// top of the module for ease of maintenance) are used.
func getCWVThresholds() (float64, float64, float64) {
	// parseEnvToFloat is a utility function that takes an environment variable name
	// and then returns the value as a float64 or the default value specified if the
	// variable isn't defined or cannot be parsed.
	parseEnvToFloat := func(varName string, defaultVal float64) float64 {
		var varValue float64
		var err error
		if varValue, err = strconv.ParseFloat(os.Getenv(varName), 64); err != nil {
			if _, exists := os.LookupEnv(varName); exists {
				log.Printf("Problem converting %s threshold. Using default.", varName)
			}
			varValue = defaultVal
		}

		return varValue
	}

	LCPThresh := parseEnvToFloat("GOOD_LCP", StandardGoodLCP)
	CLSThresh := parseEnvToFloat("GOOD_CLS", StandardGoodCLS)
	FIDThresh := parseEnvToFloat("GOOD_FID", StandardGoodFID)

	return LCPThresh, CLSThresh, FIDThresh
}

// areCWVValuesGood returns whether the CWV metrics meet the good threshold set
// in the environment variables GOOD_LCP, GOOD_CLS, and GOOD_FID.
// The metrics are returned in the order Largest Contentful Paint (LCP),
// Cumulative Layout Shift (CLS), First Input Delay (FID).
func areCWVValuesGood(lcp float64, cls float64, fid float64) (bool, bool, bool) {
	goodLCP, goodCLS, goodFID := getCWVThresholds()
	var isLCPGood, isCLSGood, isFIDGood bool // bools default to false

	if lcp <= goodLCP {
		isLCPGood = true
	}
	if cls <= goodCLS {
		isCLSGood = true
	}
	if fid <= goodFID {
		isFIDGood = true
	}

	return isLCPGood, isCLSGood, isFIDGood
}

// getCWVValues fetches the CWV values starting on the given date for the given
// interval in days. The metrics are returned in the order LCP, CLS, FID.
func getCWVValues(startDate time.Time, numDays int) (float64, float64, float64) {
	ctx := context.Background()
	projectID := getProjectID()
	bqClient, err := bigquery.NewClient(ctx, projectID)
	if err != nil {
		log.Fatal("Problem connecting to BigQuery: ", err)
	}
	analyticsID := os.Getenv("ANALYTICS_ID")
	bqProcedureName := "analytics_" + analyticsID + "get_cwv_p75_for_date"
	startDateString := "PARSE_DATE('%Y%m%d', '" + startDate.Format("20060201") + "')"
	bqQuery := bqClient.Query(fmt.Sprintf("CALL %s(%s, %d)", bqProcedureName, startDateString, numDays))

	bqResult, err := bqQuery.Read(ctx)
	if err != nil {
		log.Fatal("Problem querying BigQuery: ", err)
	}

	lcp := 0.0
	cls := 0.0
	fid := 0.0
	for {
		var m cwvMeasurement
		err := bqResult.Next(&m)
		if err == iterator.Done {
			break
		}
		switch name := m.Metric_name; name {
		case "LCP":
			lcp = m.P75
		case "CLS":
			cls = m.P75
		case "FID":
			fid = m.P75
		}
	}

	return lcp, cls, fid
}

// sendAlertEmail retrieves the environment variables required to send the alert
// email using the given CWV values. The required environment variables are:
//  - ALERT_RECEIVERS: a comma-separated list of email addresses to receive the alert
//  - EMAIL_FROM: the email address to use as the alert sender
//  - EMAIL_SERVER: the address of the SMTP server to use
//  - EMAIL_USER: the username to use when authenticating with the SMTP server
//  - EMAIL_PASS: the password to use when authenticating with the SMTP server
func sendAlertEmail(lcp float64, cls float64, fid float64) error {
	toAddresses := os.Getenv("ALERT_RECEIVERS")
	fromAddress := os.Getenv("EMAIL_FROM")
	message := createEmailMessage(fromAddress, toAddresses, lcp, cls, fid)

	mailServer := os.Getenv("EMAIL_SERVER")
	mailUser := os.Getenv("EMAIL_USER")
	mailPass := os.Getenv("EMAIL_PASS")
	mailAuth := smtp.PlainAuth("", mailUser, mailPass, mailServer)
	err := smtp.SendMail(mailServer, mailAuth, fromAddress, strings.Split(toAddresses, ","), message)

	return err
}

// createEmailMessage builds the byte array to be used as the message when
// sending an email. It is assumed that at least one of the metrics is failing.
// The message is a multipart MIME message with a plain text and an HTML part.
func createEmailMessage(from string, to string, lcp float64, cls float64, fid float64) []byte {
	LCPIsGood, CLSIsGood, FIDIsGood := areCWVValuesGood(lcp, cls, fid)
	goodLCP, goodCLS, goodFID := getCWVThresholds()
	lcpPercent := lcp / goodLCP * 100
	clsPercent := cls / goodCLS * 100
	fidPercent := fid / goodFID * 100

	message := fmt.Sprintf(EmailMessageHeader, from, to)

	if !LCPIsGood {
		message += fmt.Sprintf("LCP of %.0f ms is %.0f%% of %.0f ms budget.\r\n", lcp, lcpPercent, goodLCP)
	}
	if !CLSIsGood {
		message += fmt.Sprintf("CLS of %.0f is %.0f%% of %.0f budget.\r\n", cls, clsPercent, goodCLS)
	}
	if !FIDIsGood {
		message += fmt.Sprintf("FID of %.0f ms is %.0f%% of %.0f ms budget.\r\n", fid, fidPercent, goodFID)
	}

	message += EmailHTMLStart

	if !LCPIsGood {
		message += "<tr><td style=\"background: lightgray; font-weight: bolder; text-align: center\">LCP</td>" +
			fmt.Sprintf("<td>%.0fms</td><td>%.0fms</td><td style=\"color: red\">%.0f%%</td>", lcp, goodLCP, lcpPercent) +
			"</tr>"
	}
	if !CLSIsGood {
		message += "<tr><td style=\"background: lightgray; font-weight: bolder; text-align: center\">CLS</td>" +
			fmt.Sprintf("<td>%.0f</td><td>%.0f</td><td style=\"color: red\">%.0f%%</td>", cls, goodCLS, clsPercent) +
			"</tr>"
	}
	if !FIDIsGood {
		message += "<tr><td style=\"background: lightgray; font-weight: bolder; text-align: center\">FID</td>" +
			fmt.Sprintf("<td>%.0fms</td><td>%.0fms</td><td style=\"color: red\">%.0f%%</td>", fid, goodFID, fidPercent) +
			"</tr>"
	}

	message += EmailHTMLEnd

	return []byte(message)
}
