#!/usr/bin/env python3

# vim: autoindent tabstop=4 shiftwidth=4 expandtab softtabstop=4 filetype=python

import sys
import argparse
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
    cpus = CpuScraper.scrape()
    for cpu_list in cpus:
        for cpu in cpu_list:
            log.debug("Query for {}: {}".format(cpu[0], cpu[2]))
            updated_info = CpuScraper.get_info(cpu)
            if updated_info:
                log.info("{}, launched at: {}".format(updated_info[0], updated_info[2]))


def main() -> None:
    parser = argparse.ArgumentParser(description='Windows 11 CPU information scraper')
    parser.add_argument('--image-file', metavar="IMAGE-FILE",
                        help='Image to read QR-code from')

    args = parser.parse_args()
    _setup_logger()

    scrape()


if __name__ == '__main__':
    main()
