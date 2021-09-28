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

// areCWVValuesGood returns whether the CWV metrics meet the good threshold set
// in the environment variables GOOD_LCP, GOOD_CLS, and GOOD_FID.
// The metrics are returned in the order Largest Contentful Paint (LCP),
// Cumulative Layout Shift (CLS), First Input Delay (FID).
func areCWVValuesGood(lcp float64, cls float64, fid float64) (bool, bool, bool) {
	var goodLCP, goodCLS, goodFID float64
	var isLCPGood, isCLSGood, isFIDGood bool // bools default to false
	var err error
	if goodLCP, err = strconv.ParseFloat(os.Getenv("GOOD_LCP"), 64); err != nil {
		panic(fmt.Sprintf("Problem converting LCP threshold: %v", err))
	}
	if goodCLS, err = strconv.ParseFloat(os.Getenv("GOOD_CLS"), 64); err != nil {
		panic(fmt.Sprintf("Problem converting CLS threshold: %v", err))
	}
	if goodFID, err = strconv.ParseFloat(os.Getenv("GOOD_FID"), 64); err != nil {
		panic(fmt.Sprintf("Problem converting FID threshold: %v", err))
	}

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

func sendAlertEmail(lcp float64, cls float64, fid float64) error {
	// TODO (adamread): write this function. It's been left out of the initial CL
	// to keep the size down.
	return nil
}
