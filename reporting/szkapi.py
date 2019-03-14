import os
import sys
import json
import time
import pytz
import logging
import requests
import pandas as pd
import datetime as dt
import reporting.utils as utl

config_path = utl.config_path

login_url = 'https://adapi.sizmek.com/sas/login/login/'
report_url = 'https://adapi.sizmek.com/analytics/reports/saveAndExecute'
base_report_get_url = 'https://adapi.sizmek.com/analytics/reports/executions/'

def_dimensions = ["Site Name", "Placement Name", "Ad Name",
                  "Placement Dimension", "Campaign Name", "Ad ID"]

def_metrics = ["Served Impressions", "Total Clicks", "Video Played 25%",
               "Video Played 50%", "Video Played 75%", "Video Started",
               "Video Fully Played", "Total Conversions",
               "Post Click Conversions", "Post Impression Conversions",
               "Total Media Cost"]


class SzkApi(object):
    def __init__(self):
        self.config = None
        self.config_file = None
        self.username = None
        self.password = None
        self.api_key = None
        self.campaign_ids = None
        self.config_list = None
        self.headers = None
        self.df = pd.DataFrame()
        self.r = None

    def input_config(self, config):
        if str(config) == 'nan':
            logging.warning('Config file name not in vendor matrix.  '
                            'Aborting.')
            sys.exit(0)
        logging.info('Loading Sizmek config file: {}'.format(config))
        self.config_file = os.path.join(config_path, config)
        self.load_config()
        self.check_config()

    def load_config(self):
        try:
            with open(self.config_file, 'r') as f:
                self.config = json.load(f)
        except IOError:
            logging.error('{} not found.  Aborting.'.format(self.config_file))
            sys.exit(0)
        self.username = self.config['username']
        self.password = self.config['password']
        self.api_key = self.config['api_key']
        self.campaign_ids = self.config['campaign_ids']
        self.config_list = [self.config, self.username, self.password,
                            self.api_key, self.campaign_ids]

    def check_config(self):
        for item in self.config_list:
            if item == '':
                logging.warning('{} not in Sizmek config file.  '
                                'Aborting.'.format(item))
                sys.exit(0)

    def set_headers(self):
        self.headers = {'api-key': self.api_key}
        data = {'username': self.username, 'password': self.password}
        r = requests.post(login_url, data=json.dumps(data),
                          headers=self.headers)
        session_id = r.json()['result']['sessionId']
        self.headers['Authorization'] = session_id

    @staticmethod
    def date_check(sd, ed):
        if sd > ed:
            logging.warning('Start date greater than end date.  Start date '
                            'was set to end date.')
            sd = ed - dt.timedelta(days=1)
        timezone = 'US/Pacific'
        sd = pytz.timezone(timezone).localize(sd).isoformat()
        ed = pytz.timezone(timezone).localize(ed).isoformat()
        return sd, ed

    def get_data_default_check(self, sd, ed):
        if sd is None:
            sd = dt.datetime.today() - dt.timedelta(days=2)
        if ed is None:
            ed = dt.datetime.today() - dt.timedelta(days=1)
        sd, ed = self.date_check(sd, ed)
        return sd, ed

    def get_data(self, sd=None, ed=None, fields=None):
        sd, ed = self.get_data_default_check(sd, ed)
        report_get_url = self.request_report(sd, ed)
        report_dl_url = self.get_report_dl_url(report_get_url)
        self.df = self.download_report_to_df(report_dl_url)
        return self.df

    def request_report(self, sd, ed):
        self.set_headers()
        report = self.create_report_body(sd, ed)
        r = requests.post(report_url, headers=self.headers, json=report)
        execution_id = r.json()['result']['executionID']
        report_get_url = '{}{}'.format(base_report_get_url, execution_id)
        return report_get_url

    def get_report_dl_url(self, url):
        report_dl_url = None
        for attempt in range(100):
            time.sleep(60)
            logging.info('Checking report.  Attempt: {}'.format(attempt))
            r = requests.get(url, headers=self.headers)
            if r.json()['result']['executionStatus'] == 'FINISHED':
                logging.info('Report has been generated.')
                report_dl_url = r.json()['result']['files'][0]['url']
                break
        return report_dl_url

    def download_report_to_df(self, url):
        if url:
            r = requests.get(url)
            self.df = pd.DataFrame(r.json()['reportData'])
        else:
            logging.warning('No report download url, returning empty df.')
            self.df = pd.DataFrame()
        return self.df

    def create_report_body(self, sd, ed):
        report = {'entities': [{
                  "type": "AnalyticsReport",
                  "reportName": "test",
                  "reportScope": {
                    "entitiesHierarchy": {
                      "entitiesHierarchyLevelType": "CAMPAIGN",
                      "accounts": [
                        454
                      ],
                      "advertisers": [],
                      "campaigns": [int(x) for x in
                                    self.campaign_ids.split(',')],
                      "sites": []
                    },
                    "attributionModelID": -1,
                    "impressionCookieWindow": 0,
                    "clickCookieWindow": 0,
                    "filters": {},
                    "currencyOptions": {
                      "type": "Custom",
                      "defaultCurrency": 1,
                      "targetCurrency": 1,
                      "currencyExchangeDate": "2019-03-14"
                    },
                    "timeRange": {
                      "timeZone": "US/Pacific",
                      "type": "Custom",
                      "dataStartTimestamp": "{}".format(sd),
                      "dataEndTimestamp": "{}".format(ed)
                    },
                  },
                  "reportStructure": {
                    "attributeIDs": def_dimensions,
                    "metricIDs": def_metrics,
                    "attributeIDsOnColumns": [
                      "Conversion Tag Name"
                    ],
                    "timeBreakdown": "Day"
                  },
                  "reportExecution": {
                    "type": "Ad_Hoc"
                  },
                  "reportDeliveryMethods": [
                    {
                      "type": "URL",
                      "exportFileType": "JSON",
                      "compressionType": "NONE",
                      "emailRecipients": [""],
                      "exportFileNamePrefix": "test"
                    }
                  ],
                "reportAuthorization": {
                    "type": "mm3",
                    "userID": 1073752812
                },
                }]}
        return report