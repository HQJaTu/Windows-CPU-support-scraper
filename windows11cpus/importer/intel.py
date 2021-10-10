import requests
from bs4 import BeautifulSoup
from urllib import parse
import logging

log = logging.getLogger(__name__)


class IntelInfo:
    SEARCH_URL = "https://ark.intel.com/content/www/us/en/ark/search.html?_charset_=UTF-8&q={}"
    PROCESSORS_URL = "https://ark.intel.com/content/www/us/en/ark.html#@Processors"

    @staticmethod
    def search_info_for(data: tuple) -> tuple:
        # Example search: https://ark.intel.com/content/www/us/en/ark/search.html?_charset_=UTF-8&q=x6200FE
        # Becomes: https://ark.intel.com/content/www/us/en/ark/products/207904/intel-atom-x6200fe-processor-1-5m-cache-1-00-ghz.html
        # Via HTML: <input id="FormRedirectUrl" type="hidden" value="/content/www/us/en/ark/products/207904/intel-atom-x6200fe-processor-1-5m-cache-1-00-ghz.html"/>
        search_url = IntelInfo.SEARCH_URL.format(data[2])
        base_url_parsed = parse.urlparse(search_url)
        log.debug("Get Intel CPU information for {} from {}".format(data[2], search_url))
        r = requests.get(search_url)

        # Check search result
        parsed_html = BeautifulSoup(r.content, "html.parser")
        cpu_link = parsed_html.find('input', id='FormRedirectUrl')
        if not cpu_link:
            raise FileNotFoundError("No results!")
        partial_cpu_url = cpu_link['value']
        cpu_url_parts = parse.ParseResult(scheme=base_url_parsed.scheme, netloc=base_url_parsed.netloc,
                                          path=partial_cpu_url, params=None, query=None, fragment=None)
        cpu_url = parse.urlunparse(cpu_url_parts)

        log.debug("CPU-info is at {}".format(cpu_url))

        return IntelInfo._get_cpu_info(cpu_url)

    @staticmethod
    def _get_cpu_info(cpu_url: str) -> tuple:
        # Get the CPU-info
        r = requests.get(cpu_url)

        # <h1 class="h1">Intel Atom® x6427FE Processor </h1>
        # <span class="value" data-key="ProcessorNumber">6427FE</span>
        # <span class="value" data-key="BornOnDate">Q1'21</span>
        # <span class="value" data-key="ProductGroup">
        #   <a href="/content/www/us/en/ark/products/series/87465/intel-atom-processor-x-series.html" class="ark-accessible-color hrefcolor">Intel Atom® Processor X Series</a>
        # </span>
        parsed_html = BeautifulSoup(r.content, "html.parser")
        cpu_title_html = parsed_html.find('h1', {"class": "h1"})
        cpu_number_html = parsed_html.find('span', {"class": "value", "data-key": "ProcessorNumber"})
        cpu_launch_html = parsed_html.find('span', {"class": "value", "data-key": "BornOnDate"})
        product_group_html = parsed_html.find('span', {"class": "value", "data-key": "ProductGroup"}).find('a')

        cpu_title = cpu_title_html.text.strip()
        if cpu_number_html:
            # Legacy CPUs may not have a number at all
            cpu_number = cpu_number_html.text.strip()
        else:
            cpu_number = None
        if cpu_launch_html:
            # Legacy CPUs may not have launch quarter
            launched_at = cpu_launch_html.text.strip()
        else:
            launched_at = None
        product_group = product_group_html.text.strip()
        new_data = (
            cpu_title,
            cpu_number,
            launched_at,
            product_group,
            cpu_url,
        )

        return new_data

    @staticmethod
    def scrape() -> list:
        families_url = IntelInfo.PROCESSORS_URL
        base_url_parsed = parse.urlparse(families_url)
        log.debug("Get Intel CPU-family information from {}".format(families_url))
        r = requests.get(families_url)
        parsed_html = BeautifulSoup(r.content, "html.parser")
        if False:
            cpu_launch_html = parsed_html.find('div', {"data-parent-panel-key": "Processors"})
            families = cpu_launch_html.find_all('div', {"class": "Processors", "data-wap_ref": "category|subcategory"})
            for family in families:
                from pprint import pprint
                pprint(family)

        # Intel® Core™ Processors
        cpu_blocks1 = parsed_html.find_all('div', {"class": "products processors",
                                                   "data-parent-panel-key": "PanelLabel122139"})
        # Intel® Pentium® Processor
        cpu_blocks2 = parsed_html.find_all('div',
                                           {"class": "products processors", "data-parent-panel-key": "PanelLabel29862"})
        # Intel® Celeron® Processor
        cpu_blocks3 = parsed_html.find_all('div',
                                           {"class": "products processors", "data-parent-panel-key": "PanelLabel43521"})
        # Intel® Xeon® Processors
        cpu_blocks4 = parsed_html.find_all('div',
                                           {"class": "products processors", "data-parent-panel-key": "PanelLabel595"})
        # Intel® Xeon Phi™ Processors
        cpu_blocks5 = parsed_html.find_all('div',
                                           {"class": "products processors", "data-parent-panel-key": "PanelLabel75557"})
        #  Intel® Itanium® Processor
        cpu_blocks6 = parsed_html.find_all('div',
                                           {"class": "products processors", "data-parent-panel-key": "PanelLabel451"})
        #  Intel Atom® Processor
        cpu_blocks7 = parsed_html.find_all('div',
                                           {"class": "products processors", "data-parent-panel-key": "PanelLabel29035"})
        cpu_blocks = [cpu_blocks1, cpu_blocks2, cpu_blocks3, cpu_blocks4, cpu_blocks5, cpu_blocks6, cpu_blocks7]
        all_cpus = []
        for family_block in [item for sublist in cpu_blocks for item in sublist]:
            for family in family_block.find_all('a'):
                family_name = family.text
                link = family['href']
                family_link_parts = parse.ParseResult(scheme=base_url_parsed.scheme, netloc=base_url_parsed.netloc,
                                                      path=link, params=None, query=None, fragment=None)
                family_url = parse.urlunparse(family_link_parts)
                log.debug("Got Intel CPU-family {}".format(family_name))
                family_cpus = IntelInfo._scrape_family(family_name, family_url)
                all_cpus.extend(family_cpus)

        return all_cpus

    @staticmethod
    def _scrape_family(family_name: str, family_url: str) -> list:
        base_url_parsed = parse.urlparse(family_url)
        r = requests.get(family_url)
        parsed_html = BeautifulSoup(r.content, "html.parser")
        cpu_table = parsed_html.find('table', id="product-table").find('tbody')

        all_cpus = []
        for cpu_row in cpu_table.find_all('tr'):
            cpu_cell = cpu_row.find('td', {"data-component": "arkproductlink"})
            cpu_link_html = cpu_cell.find('a')
            cpu_link = cpu_link_html['href']
            cpu_link_parts = parse.ParseResult(scheme=base_url_parsed.scheme, netloc=base_url_parsed.netloc,
                                               path=cpu_link, params=None, query=None, fragment=None)
            cpu_url = parse.urlunparse(cpu_link_parts)
            try:
                cpu_data = IntelInfo._get_cpu_info(cpu_url)
            except Exception:
                log.exception("Loading Intel CPU-info from {} failed!".format(cpu_url))
                raise
            log.info("Intel CPU-family: {}, CPU: {}".format(family_name, cpu_data[0]))
            all_cpus.append(cpu_data)

        return all_cpus
