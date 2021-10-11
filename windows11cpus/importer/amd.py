import requests
from bs4 import BeautifulSoup
import re
from time import sleep
import logging

log = logging.getLogger(__name__)


class AmdInfo:
    LOAD_TIMEOUT = 15.0
    PROCESSORS_URL = "https://www.amd.com/en/products/specifications/processors"
    PROCESSOR_INFO_URL = "https://www.amd.com/en/product/{}"
    USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:92.0) Gecko/20100101 Firefox/92.0"

    @staticmethod
    def scrape() -> list:
        list_url = AmdInfo.PROCESSORS_URL
        log.debug("Get AMD CPU-family information from {}".format(list_url))

        sess = requests.session()
        if False:
            my_cookie = {
                "version": 0,
                "name": 'OptanonAlertBoxClosed',
                "value": '2021-10-10T19:26:12.934Z',
                "port": None,
                # "port_specified":False,
                "domain": 'www.mydomain.com',
                # "domain_specified":False,
                # "domain_initial_dot":False,
                "path": '/',
                # "path_specified":True,
                "secure": False,
                "expires": None,
                "discard": True,
                "comment": None,
                "comment_url": None,
                "rest": {},
                "rfc2109": False
            }
            sess.cookies.set(**my_cookie)
        headers = {
            # amd.com is very picky on User-Agent
            'User-Agent': AmdInfo.USER_AGENT,
        }
        sess.headers.update(headers)
        r = sess.get(list_url, timeout=AmdInfo.LOAD_TIMEOUT)
        parsed_html = BeautifulSoup(r.content, "html.parser")
        spec_table = parsed_html.find('table', id='spec-table').find('tbody')
        all_cpus = []
        for table_row in spec_table.find_all('tr'):
            cpu_name_column = table_row.find('td', {"headers": "view-name-table-column"})
            cpu_title = cpu_name_column.text
            processor_id = None
            for css_class in cpu_name_column['class']:
                match = re.search(r'^entity-(\d+)$', css_class)
                if match:
                    processor_id = match.group(1)
                    break
            if not processor_id:
                raise ValueError("AMD CPU {} does not have id!".format(cpu_title))

            try:
                cpu_data = AmdInfo._scrape_cpu(sess, processor_id)
                # AMD don't want us making that many requests.
                # Their Application Gateway will block the IPv4 on any attempts to crawl their site.
                sleep(1.5)
            except Exception:
                log.exception("Loading AMD CPU-info for ID {} failed!".format(processor_id))
                raise
            log.info("AMD CPU-family: {}, CPU: {}".format(cpu_data[3], cpu_data[0]))
            all_cpus.append(cpu_data)

        return all_cpus

    @staticmethod
    def _scrape_cpu(sess: requests.Session, processor_id: str) -> tuple:
        cpu_url = AmdInfo.PROCESSOR_INFO_URL.format(processor_id)
        r = sess.get(cpu_url, timeout=AmdInfo.LOAD_TIMEOUT)
        parsed_html = BeautifulSoup(r.content, "html.parser")
        title_html = parsed_html.find('div', id="block-amd-page-title").find('h2')
        cpu_title = title_html.text
        cpu_number = None
        spec_table = parsed_html.find('div', id='product-specs').find('div', {"class": "fieldset-wrapper"})
        launched_at_html = spec_table.find('div', {"class": "field--name-field-launch-date"})
        if not launched_at_html:
            # Attempt 2: Some CPUs have different field name
            launched_at_html = spec_table.find('div', {"class": "field--name-field-launch-date-new"})
        if launched_at_html:
            launched_at_html = launched_at_html.find('div', {"class": "field__item"})
            launched_at = launched_at_html.text
        else:
            # Both attempts failed. This CPU has no launch information in it's info-page.
            launched_at = None
        family_html = spec_table.find('div', {"class": "field--name-product-type"}).find('div',
                                                                                         {"class": "field__item"})
        product_group = family_html.text

        new_data = (
            cpu_title,
            cpu_number,
            launched_at,
            product_group,
            cpu_url,
        )

        return new_data
