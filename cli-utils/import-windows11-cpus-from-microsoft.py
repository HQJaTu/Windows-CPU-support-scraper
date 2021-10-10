#!/usr/bin/env python3

# vim: autoindent tabstop=4 shiftwidth=4 expandtab softtabstop=4 filetype=python

import sys
import argparse
import pickle
from googleapiclient.discovery import build
from google.oauth2 import service_account
from windows11cpus import CpuScraper
import logging

log = logging.getLogger(__name__)


def _setup_logger() -> None:
    log_formatter = logging.Formatter("%(asctime)s [%(levelname)-5.5s]  %(message)s")
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(log_formatter)
    console_handler.propagate = False
    logging.getLogger().addHandler(console_handler)
    log.setLevel(logging.DEBUG)
    # log.setLevel(logging.INFO)

    lib_log = logging.getLogger("windows11cpus")
    lib_log.setLevel(logging.DEBUG)


def scrape() -> None:
    cpus = CpuScraper.scrape_win11_cpus()
    for cpu_list in cpus:
        for cpu in cpu_list:
            log.debug("Win11 is compatible with {}: {}".format(cpu[0], cpu[2]))
            if False:
                updated_info = CpuScraper.get_info(cpu)
                if updated_info:
                    log.info("{}, launched at: {}".format(updated_info[0], updated_info[2]))

    vendor_cpus = CpuScraper.scrape_vendors()
    with open('all-vendors-cpus.dat', 'wb') as f:
        # Pickle the 'data' dictionary using the highest protocol available.
        pickle.dump(vendor_cpus, f, pickle.HIGHEST_PROTOCOL)


def upload_to_google(credentials_file: str, shared_owner_email: str):
    spreadsheet_file_name = "Vendor CPU-lists"
    spreadsheet_title = "Intel"

    # From: https://developers.google.com/sheets/api/quickstart/python
    creds = service_account.Credentials.from_service_account_file(credentials_file)

    # Drive, figure out if the sheet already exists
    # Code from: https://developers.google.com/drive/api/v3/quickstart/python
    drive_service = build('drive', 'v3', credentials=creds)
    results = drive_service.files().list(pageSize=50, fields="nextPageToken, files(id, name, mimeType)").execute()
    items = results.get('files', [])
    if False:
        # Wipe out all files from service account's drive
        for drive_item in items:
            drive_service.files().delete(fileId=drive_item['id']).execute()
            log.debug("Deleted existing file {} ({})".format(drive_item['name'], drive_item['id']))
    spreadsheet_id = None
    for drive_item in items:
        if drive_item['mimeType'] != "application/vnd.google-apps.spreadsheet":
            continue
        if drive_item['name'] == spreadsheet_file_name:
            spreadsheet_id = drive_item['id']
            break

    # Call the Sheets API
    sheets_service = build('sheets', 'v4', credentials=creds)
    sheet = sheets_service.spreadsheets()
    if spreadsheet_id:
        # Existing. Get a handle of it
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=spreadsheet_title).execute()
        values = result.get('values', [])
    else:
        # Not existing, go create!
        # Create new
        # Code from: https://developers.google.com/sheets/api/guides/create#python
        # Properties defined in: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets#Spreadsheet
        create_props = {
            'properties': {
                'title': spreadsheet_file_name
            },
            "sheets": [
                {
                    'properties': {
                        'title': spreadsheet_title
                    }
                }
            ],
        }
        spreadsheet = sheet.create(body=create_props,
                                   fields='spreadsheetId').execute()
        spreadsheet_id = spreadsheet.get('spreadsheetId')
        log.info('Created spreadsheet with ID: {0}'.format(spreadsheet_id))
        share_failed = False

        def _drive_callback(request_id, response, exception):
            nonlocal share_failed
            if exception:
                # Handle error
                share_failed = True
                log.exception(exception)
            else:
                log.debug("Google Drive Permission Id: %s" % response.get('id'))

        batch = drive_service.new_batch_http_request(callback=_drive_callback)
        # Roles: owner, organizer, fileOrganizer, writer, commenter, reader
        # See: https://developers.google.com/drive/api/v3/reference/permissions
        role_to_set = 'writer'
        user_permission = {
            'type': 'user',
            'role': role_to_set,
            'emailAddress': shared_owner_email
        }
        batch.add(drive_service.permissions().create(
            fileId=spreadsheet_id,
            body=user_permission,
            fields='id',
            # transferOwnership=True,
        ))
        batch.execute()
        # Without batch:
        # drive_service.permissions().create(fileId=spreadsheet_id, body=user_permission).execute()
        if not share_failed:
            log.info("Shared created file with {} with role {}".format(shared_owner_email, role_to_set))
        else:
            log.error("Not shared the spreadsheet correctly.")
    log.info("Done setting GCP up")

    # Populate the sheet
    vendor_cpus = None
    with open('all-vendors-cpus.dat', 'rb') as f:
        # Pickle the 'data' dictionary using the highest protocol available.
        vendor_cpus = pickle.load(f)

    value_input_option = 'USER_ENTERED'
    body = {
        'values': vendor_cpus
    }
    result = sheet.values().update(
        spreadsheetId=spreadsheet_id, range=spreadsheet_title,
        valueInputOption=value_input_option, body=body).execute()
    log.debug('{0} cells updated.'.format(result.get('updatedCells')))

    log.info("Done updating data")


def main() -> None:
    parser = argparse.ArgumentParser(description='Windows 11 CPU information scraper')
    parser.add_argument('--google-credentials', metavar='GOOGLE-JSON-CREDENTIALS-FILE',
                        help='Mandatory. JSON-file with Google Sheets API Service Account credentials.')
    parser.add_argument('--spreadsheet-co-owner-email', metavar='GOOGLE-DRIVE-USER-EMAIL',
                        help='Mandatory. Service account will create a Spreadsheet into Google Drive. '
                             'It needs to be shared with a human.')

    args = parser.parse_args()
    _setup_logger()

    if args.google_credentials:
        upload_to_google(args.google_credentials, args.spreadsheet_co_owner_email)
    else:
        scrape()


if __name__ == '__main__':
    main()
