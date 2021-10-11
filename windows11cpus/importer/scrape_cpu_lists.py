import os
import requests
from bs4 import BeautifulSoup
import pickle
import logging
from .intel import IntelInfo
from .amd import AmdInfo

log = logging.getLogger(__name__)


class CpuScraper:
    CPU_LISTS = (
        "https://docs.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-amd-processors",
        "https://docs.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-intel-processors",
        "https://docs.microsoft.com/en-us/windows-hardware/design/minimum/supported/windows-11-supported-qualcomm-processors"
    )

    production_filename = 'all-vendors-cpus.dat'
    intel_filename = 'intel-cpus.dat'
    amd_filename = 'amd-cpus.dat'

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
    def scrape_vendors(force: bool = False) -> dict:
        cpus = {}

        # Intel
        if not force and os.path.exists(CpuScraper.intel_filename):
            with open(CpuScraper.intel_filename, 'rb') as f:
                intel_cpus = pickle.load(f)
        else:
            intel_cpus = IntelInfo.scrape()
            with open(CpuScraper.intel_filename, 'wb') as f:
                # Pickle the 'data' dictionary using the highest protocol available.
                pickle.dump(intel_cpus, f, pickle.HIGHEST_PROTOCOL)
        cpus['Intel'] = intel_cpus
        CpuScraper._save_cpus(cpus)

        # AMD
        if not force and os.path.exists(CpuScraper.amd_filename):
            with open(CpuScraper.amd_filename, 'rb') as f:
                amd_cpus = pickle.load(f)
        else:
            amd_cpus = AmdInfo.scrape()
            with open(CpuScraper.amd_filename, 'wb') as f:
                # Pickle the 'data' dictionary using the highest protocol available.
                pickle.dump(amd_cpus, f, pickle.HIGHEST_PROTOCOL)
        cpus['AMD'] = amd_cpus

        # All done!
        CpuScraper._save_cpus(cpus, final=True)

        return cpus

    @staticmethod
    def _save_cpus(vendor_cpus: dict, final: bool = False) -> None:
        wip_filename = 'all-vendors-cpus-work-in-progress.dat'
        if final:
            filename = CpuScraper.production_filename
        else:
            filename = wip_filename
        with open(filename, 'wb') as f:
            # Pickle the 'data' dictionary using the highest protocol available.
            pickle.dump(vendor_cpus, f, pickle.HIGHEST_PROTOCOL)

        if final and os.path.exists(wip_filename):
            os.unlink(wip_filename)
