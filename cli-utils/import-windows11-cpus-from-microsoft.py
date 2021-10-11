#!/usr/bin/env python3

# vim: autoindent tabstop=4 shiftwidth=4 expandtab softtabstop=4 filetype=python

import sys
import argparse
import pickle
from typing import Tuple
from googleapiclient.discovery import build, Resource
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


def upload_to_google(credentials_file: str, shared_owner_email: str):
    spreadsheet_file_name = "Vendor CPU-lists"

    # Load data from file
    with open(CpuScraper.production_filename, 'rb') as f:
        # Pickle the 'data' dictionary using the highest protocol available.
        vendor_cpus = pickle.load(f)
    spreadsheet_title = list(vendor_cpus.keys())[0]

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
    log.info("Done setting GCP up")

    # Populate the sheet
    header_row = ('Processor Title', 'Processor Number', 'Launch', 'Family', 'URL to information')
    value_input_option = 'USER_ENTERED'
    for spreadsheet_title in vendor_cpus:
        # Confirm the spreadsheet file exists and is shared.
        # Create necessary sheets into the file, if necessary.
        spreadsheet_id, sheet = _confirm_spreadsheet_existence(drive_service, sheets_service,
                                                               spreadsheet_id, spreadsheet_title,
                                                               spreadsheet_file_name, shared_owner_email)

        cpu_values = [header_row] + vendor_cpus[spreadsheet_title]
        result = sheet.values().clear(
            spreadsheetId=spreadsheet_id, range=spreadsheet_title, body={}).execute()
        body = {
            'values': cpu_values
        }
        result = sheet.values().update(
            spreadsheetId=spreadsheet_id, range=spreadsheet_title,
            valueInputOption=value_input_option, body=body).execute()
        log.debug('Sheet {}, Updated {} cells.'.format(spreadsheet_title, result.get('updatedCells')))

    log.info("Done updating data")


def _confirm_spreadsheet_existence(drive_service: Resource, sheets_service: Resource, spreadsheet_id: str,
                                   sheet_title: str,
                                   file_title: str, shared_owner_email: str) -> Tuple[str, Resource]:
    sheet = sheets_service.spreadsheets()
    if spreadsheet_id:
        # Assume existing. Get a handle of it.
        info = sheet.get(spreadsheetId=spreadsheet_id).execute()

        # Metadata indicates, the sheet would exist
        for sheet_props in info['sheets']:
            if sheet_props['properties']['title'] == sheet_title:
                # Try requesting the sheet. As metadata suggest, this MUST succeed.
                result = sheet.values().get(spreadsheetId=spreadsheet_id, range=sheet_title).execute()

                return spreadsheet_id, sheet

    # Create entire file?
    # Create only a new sheet into existing file?
    if not spreadsheet_id:
        # Not existing, go create a new one!
        # Code from: https://developers.google.com/sheets/api/guides/create#python
        # Properties defined in: https://developers.google.com/sheets/api/reference/rest/v4/spreadsheets#Spreadsheet
        create_props = {
            'properties': {
                'title': file_title
            },
            "sheets": [
                {
                    'properties': {
                        'title': sheet_title
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

    else:
        # New sheet creation code from: https://stackoverflow.com/a/67150492/1548275
        create_props = {
            'requests': [
                {
                    'addSheet': {
                        'properties': {
                            'title': sheet_title
                        }
                    }
                }
            ]
        }
        request = sheet.batchUpdate(spreadsheetId=spreadsheet_id, body=create_props)
        response = request.execute()

    return spreadsheet_id, sheet


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
        log.info("Done uploading.")
    else:
        scrape()
        log.info("Done scraping.")


if __name__ == '__main__':
    main()
