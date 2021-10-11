#!/usr/bin/env python3

# vim: autoindent tabstop=4 shiftwidth=4 expandtab softtabstop=4 filetype=python

import sys
import argparse
import pickle
from typing import Tuple
import re
from datetime import datetime
from googleapiclient.discovery import build, Resource
from google.oauth2 import service_account
from windows11cpus import CpuScraper
import logging

log = logging.getLogger(__name__)

ACTION_SCRAPE = "scrape"
ACTION_UPLOAD = "upload"


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


def scrape(credentials_file: str = None, shared_owner_email: str = None) -> None:
    # Scrape Microsoft compatibility list
    cpus = CpuScraper.scrape_win11_cpus()

    # This should be a simple load instead of a slow scraping-operation.
    vendor_cpus = CpuScraper.scrape_vendors()

    # Prepare the list
    amd_cpu_titles = [(cpu_idx, cpu[0]) for cpu_idx, cpu in enumerate(vendor_cpus['AMD'])]
    intel_cpu_titles = [(cpu_idx, cpu[0]) for cpu_idx, cpu in enumerate(vendor_cpus['Intel'])]

    # Iterate
    compatible_cpus = {}
    enriched_vendor_cpus = {}
    for cpu_list in cpus:
        vendor = cpu_list[0][0]
        if vendor == 'AMD':
            list_to_check = amd_cpu_titles
        elif vendor.startswith('Intel'):
            list_to_check = intel_cpu_titles
            vendor = 'Intel'
        elif vendor.startswith('Qualcomm'):
            continue
        else:
            raise RuntimeError("Don't know vendor {}!".format(vendor))
        compatible_cpus[vendor] = []
        for cpu in cpu_list:
            # Match model. In many cases that will do the trick
            matching_model_idxs = [s[0] for s in list_to_check if cpu[2] in s[1]]
            if len(matching_model_idxs) == 0:
                log.debug("Win11 is compatible with {}: {}, but it cannot be found".format(cpu[0], cpu[2]))
            elif len(matching_model_idxs) == 1:
                log.debug("Win11 is compatible with {}: {}".format(cpu[0], cpu[2]))
                compatible_cpus[vendor].append(list_to_check[matching_model_idxs[0]])
            else:
                # Refine model match:
                cpu_to_match = " {} ".format(cpu[2])
                refined_matching_model_idxs = [s[0] for s in list_to_check if cpu_to_match in s[1]]
                if 0 < len(refined_matching_model_idxs) < len(matching_model_idxs):
                    # Refining did help make this more accurate match.
                    matching_model_idxs = refined_matching_model_idxs

                # Secondary matching based on product family / brand.
                models_to_search = [(cpu_idx, list_to_check[cpu_idx]) for cpu_idx in matching_model_idxs]
                matching_brand_idxs = [s[0] for s in models_to_search if cpu[1] in s[1]]
                if len(matching_brand_idxs) == 0:
                    matching_brand_idxs = matching_model_idxs
                if len(matching_brand_idxs) == 1:
                    log.debug("Win11 is compatible with {}: {}".format(cpu[0], cpu[2]))
                    compatible_cpus[vendor].append(list_to_check[matching_brand_idxs[0]])
                else:
                    log.warning(
                        "Win11 is compatible with {}: {}, "
                        "but there are several such units: {}".format(cpu[0], cpu[2], ', '.join(
                            [list_to_check[cpu_idx][1] for cpu_idx in matching_brand_idxs])))
                    compatible_cpus[vendor].extend([list_to_check[cpu_idx] for cpu_idx in matching_brand_idxs])

    # Done searching for matches: Intel® / AMD
    log.info(
        "There are {} compatible Intel CPUs out of {}".format(len(compatible_cpus['Intel']), len(intel_cpu_titles)))
    log.info("There are {} compatible AMD CPUs out of {}".format(len(compatible_cpus['AMD']), len(amd_cpu_titles)))

    for vendor in vendor_cpus:
        enriched_vendor_cpus[vendor] = []
        compatible_cpu_idxs = set(s[0] for s in compatible_cpus[vendor])
        for cpu_idx, cpu in enumerate(vendor_cpus[vendor]):
            is_compatible = cpu_idx in compatible_cpu_idxs
            if not cpu[2]:
                launch_date = None
            elif not isinstance(cpu[2], str):
                raise ValueError("Argh!")
            else:
                launch_date = _parse_launch_date(cpu[2])

            enriched_data = (
                cpu[0],
                cpu[1],
                is_compatible,
                launch_date,
                cpu[2],
                cpu[3],
                cpu[4],
            )
            enriched_vendor_cpus[vendor].append(enriched_data)

    # Done enriching --> to Google Spreadsheet
    if credentials_file and shared_owner_email:
        header_row = (
        'Processor Title', 'Processor Number', 'Win11', 'Launch', 'Launch Q', 'Family', 'URL to information')
        upload_to_google(credentials_file, enriched_vendor_cpus, header_row, "Vendor enriched CPU-lists",
                         shared_owner_email)


def _parse_launch_date(launch_date_str: str) -> str:
    # Parse launch date
    launch_date_in = launch_date_str
    if ',' in launch_date_in:
        launch_date_in = launch_date_in.split(',', 1)[0]
    match = re.search(r'^Q(\d)\D?(\d{2})$', launch_date_in)  # Q2'17, Q216
    if match:
        quarter = int(match.group(1))
        year = 2000 + int(match.group(2))
        launch_date = "{}-Q{}".format(year, quarter)
        return launch_date

    match = re.search(r"^(\d{1,2})['/](\d{2})$", launch_date_in)  # 04'16, 04/16
    if match:
        quarter = 1 + int(match.group(1)) // 4
        year = 2000 + int(match.group(2))
        launch_date = "{}-Q{}".format(year, quarter)

        return launch_date

    match = re.search(r"(\d+)/(\d+)/(\d{4})$", launch_date_in)  # 11/5/2020
    if match:
        quarter = 1 + int(match.group(1)) // 4
        year = int(match.group(3))
        launch_date = "{}-Q{}".format(year, quarter)

        return launch_date

    match = re.search(r"^(\d{1,2})/(\d{4})$", launch_date_in)  # 7/2020
    if match:
        quarter = 1 + int(match.group(1)) // 4
        year = int(match.group(2))
        launch_date = "{}-Q{}".format(year, quarter)

        return launch_date

    match = re.search(r"^(\d+)/(\d+)/(\d{2})$", launch_date_in)  # 3/16/20
    if match:
        quarter = 1 + int(match.group(1)) // 4
        year = 2000 + int(match.group(3))
        launch_date = "{}-Q{}".format(year, quarter)

        return launch_date

    match = re.search(r"^(\D+)\s+(\d{4})$", launch_date_in)  # September 2018
    if match:
        month = int(datetime.strptime(match.group(1)[:3], '%b').strftime('%m'))
        quarter = 1 + int(month) // 4
        year = int(match.group(2))
        launch_date = "{}-Q{}".format(year, quarter)

        return launch_date

    match = re.search(r'^Q(\d)\s?(\d{4})$', launch_date_in)  # Q12021
    if match:
        quarter = int(match.group(1))
        year = int(match.group(2))
        launch_date = "{}-Q{}".format(year, quarter)

        return launch_date

    match = re.search(r'^(\d)Q\D?(\d{2})$', launch_date_in)  # 2Q18
    if match:
        quarter = int(match.group(1))
        year = 2000 + int(match.group(2))
        launch_date = "{}-Q{}".format(year, quarter)

        return launch_date

    match = re.search(r'^(\d)Q\s?(\d{4})$', launch_date_in)  # 3Q 2016
    if match:
        quarter = int(match.group(1))
        year = int(match.group(2))
        launch_date = "{}-Q{}".format(year, quarter)

        return launch_date
    else:
        # Give up!
        raise ValueError(
            "Don't know how to handle launch date: {}".format(launch_date_str))


def upload_to_google(credentials_file: str, vendor_cpus: dict, header_row: tuple,
                     spreadsheet_file_name: str, shared_owner_email: str):
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
    parser.add_argument('action', metavar='ACTION-TO-DO',
                        help='Mandatory action to do: scrape or upload.')
    parser.add_argument('--google-credentials', metavar='GOOGLE-JSON-CREDENTIALS-FILE',
                        help='JSON-file with Google Sheets API Service Account credentials.')
    parser.add_argument('--spreadsheet-co-owner-email', metavar='GOOGLE-DRIVE-USER-EMAIL',
                        help='Service account will create a Spreadsheet into Google Drive. '
                             'It needs to be shared with a human.')

    args = parser.parse_args()
    _setup_logger()

    if args.action == ACTION_UPLOAD:
        # Load data from file
        filename = "{}/{}".format(CpuScraper.data_dir, CpuScraper.production_filename)
        with open(filename, 'rb') as f:
            # Pickle the 'data' dictionary using the highest protocol available.
            vendor_cpus = pickle.load(f)

        header_row = ('Processor Title', 'Processor Number', 'Launch', 'Family', 'URL to information')
        upload_to_google(args.google_credentials, vendor_cpus, "Vendor CPU-lists", args.spreadsheet_co_owner_email)
        log.info("Done uploading.")
    elif args.action == ACTION_SCRAPE:
        scrape(args.google_credentials, args.spreadsheet_co_owner_email)
        log.info("Done scraping.")
    else:
        parser.print_help()
        exit(1)


if __name__ == '__main__':
    main()
