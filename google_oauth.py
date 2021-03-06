# -*- coding: utf-8 -*-


import pickle
import os.path, sys
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# @staticmethod
# def oauth():

SCOPES = ['https://www.googleapis.com/auth/drive']
# print(locals(creds))

# print(locals(creds))
# global creds, token, service
creds = None

if os.path.exists('/app/data/rclone_expand/token.pickle'):            
    with open('/app/data/rclone_expand/token.pickle', 'rb') as token:
        creds = pickle.load(token)

# If there are no (valid) credentials available, let the user log in.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            '/app/data/rclone_expand/credentials.json', SCOPES)
        creds = flow.run_local_server(port=0)
    # Save the credentials for the next run
    with open('/app/data/rclone_expand/token.pickle', 'wb') as token:
        pickle.dump(creds, token)


service = build('drive', 'v3', credentials=creds)
page_token = None

# return(creds, token, service)

