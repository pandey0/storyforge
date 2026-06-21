import os
import pdfplumber
import requests
from loguru import logger

NCRB_REPORTS = {
    "2022": "https://ncrb.gov.in/uploads/nationalcrimerecordsbureau/custom/CrimeinIndia2022.pdf",
    "2021": "https://ncrb.gov.in/uploads/nationalcrimerecordsbureau/custom/CrimeinIndia2021Complete.pdf",
    "2020": "https://ncrb.gov.in/uploads/nationalcrimerecordsbureau/custom/CrimeinIndia2020.pdf",
    "2019": "https://ncrb.gov.in/uploads/nationalcrimerecordsbureau/custom/CrimeinIndia2019.pdf",
}

_REPORTS_DIR = "data/reports"
_MIN_SIZE_BYTES = 100 * 1024  # 100 KB
_HEADERS = {"User-Agent": "IndianCrimeChannel-Research/1.0"}


class NCRBDownloader:
    def __init__(self):
        os.makedirs(_REPORTS_DIR, exist_ok=True)

    def get_local_path(self, year: str) -> str:
        return os.path.join(_REPORTS_DIR, f"ncrb_crime_india_{year}.pdf")

    def is_downloaded(self, year: str) -> bool:
        path = self.get_local_path(year)
        return os.path.isfile(path) and os.path.getsize(path) > _MIN_SIZE_BYTES

    def download_year(self, year: str, force: bool = False) -> str | None:
        if not force and self.is_downloaded(year):
            logger.info("NCRB {}: already downloaded, skipping", year)
            return self.get_local_path(year)

        url = NCRB_REPORTS.get(year)
        if url is None:
            logger.warning("NCRB {}: no URL configured", year)
            return None

        local_path = self.get_local_path(year)
        logger.info("Downloading NCRB {}: {}", year, url)

        try:
            with requests.get(url, headers=_HEADERS, stream=True, timeout=60) as resp:
                if resp.status_code == 404:
                    logger.warning("NCRB {}: 404 not found, skipping", year)
                    return None
                resp.raise_for_status()

                total_bytes = 0
                with open(local_path, "wb") as fh:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            fh.write(chunk)
                            total_bytes += len(chunk)

                size_mb = total_bytes / (1024 * 1024)
                logger.info("Downloading NCRB {}: {:.2f}MB", year, size_mb)
                return local_path

        except requests.HTTPError as exc:
            logger.error("NCRB {}: HTTP error — {}", year, exc)
            return None
        except requests.RequestException as exc:
            logger.error("NCRB {}: request failed — {}", year, exc)
            return None

    def download_all(self, force: bool = False) -> dict[str, str]:
        results: dict[str, str] = {}
        for year in NCRB_REPORTS:
            path = self.download_year(year, force=force)
            if path is not None:
                results[year] = path
        return results

    def extract_stats(self, year: str, keywords: list[str]) -> dict:
        path = self.get_local_path(year)
        if not self.is_downloaded(year):
            logger.warning("NCRB {}: file not downloaded, cannot extract stats", year)
            return {kw: [] for kw in keywords}

        matches: dict[str, list[str]] = {kw: [] for kw in keywords}
        lower_keywords = [kw.lower() for kw in keywords]

        try:
            with pdfplumber.open(path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text()
                    if not text:
                        continue
                    for line in text.splitlines():
                        line_lower = line.lower()
                        for kw, kw_lower in zip(keywords, lower_keywords):
                            if kw_lower in line_lower:
                                matches[kw].append(line.strip())
        except Exception as exc:
            logger.error("NCRB {}: pdfplumber error — {}", year, exc)

        return matches
