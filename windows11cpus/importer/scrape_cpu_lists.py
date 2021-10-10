import requests
from bs4 import BeautifulSoup
import logging
from .intel import IntelInfo

log = logging.getLogger(__name__)


class CpuScraper:
    CPU_LISTS = (
        "https://docs.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-amd-processors",
        "https://docs.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-intel-processors",
        "https://docs.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-qualcomm-processors"
    )

    @staticmethod
    def scrape_win11_cpus() -> list:
        cpu_lists = []
        for url in CpuScraper.CPU_LISTS:
            r = requests.get(url)
            cpu_list = CpuScraper._html_parser(r.content)
            cpu_lists.append(cpu_list)

        return cpu_lists

    @staticmethod
    def _html_parser(content: str) -> list:
        parsed_html = BeautifulSoup(content, "html.parser")
        cpu_table = parsed_html.find('main', id='main').find('table').find('tbody')
        cpus_out = []
        for row in cpu_table.find_all('tr'):
            cpu_info = []
            for cell in row.find_all("td"):
                cpu_info.append(cell.text)
            if len(cpu_info) != 3:
                raise ValueError("Invalid data row!")
            cpus_out.append(tuple(cpu_info))

        return cpus_out

    @staticmethod
    def get_info(data: tuple) -> tuple:
        if data[0].startswith('Intel'):
            return IntelInfo.search_info_for(data)
        elif data[0].startswith('AMD'):
            return None

        raise NotImplementedError("Vendor {} not implemented yet!".format(data[0]))

    @staticmethod
    def scrape_vendors() -> list:
        cpus = []
        intel_cpus = IntelInfo.scrape()
        cpus.extend(intel_cpus)

        return cpus
