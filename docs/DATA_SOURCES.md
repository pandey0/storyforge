# Data Sources — Authoritative Reference

> These are the exact sources used for case research, news monitoring, and report downloads.
> Add new sources here immediately when discovered. Never scrape without checking legal status first.

---

## 1. Live News Monitoring (RSS + Scraping)

### Primary News Sources
| Source | URL | RSS Feed | Notes |
|--------|-----|----------|-------|
| NDTV Crime | https://www.ndtv.com/crime | https://feeds.feedburner.com/ndtvnews-crime | Most reliable Indian crime RSS |
| Times of India | https://timesofindia.indiatimes.com/topic/crime | https://timesofindia.indiatimes.com/rssfeedstopstories.cms | Broad coverage |
| Indian Express | https://indianexpress.com/section/cities/crime/ | https://indianexpress.com/section/india/feed/ | Good investigative |
| The Hindu | https://www.thehindu.com/topic/Crime/ | https://www.thehindu.com/news/national/?service=rss | Credible, analytical |
| India Today | https://www.indiatoday.in/crime | https://www.indiatoday.in/rss/1206513 | High reach |
| Hindustan Times | https://www.hindustantimes.com/topic/crime | https://www.hindustantimes.com/feeds/rss/crime/rssfeed.xml | Good north India coverage |
| Scroll.in | https://scroll.in/topic/crime | https://scroll.in/feed | Analytical, long-form perspective |
| The Wire | https://thewire.in/crime | https://thewire.in/feed | Investigative, systemic angles |
| Quint | https://www.thequint.com/crime | https://www.thequint.com/feeds/rss/news | Good multimedia |
| News18 | https://www.news18.com/commonman/crime/ | https://www.news18.com/rss/crime.xml | Broad national |

### Legal News Sources
| Source | URL | Notes |
|--------|-----|-------|
| LiveLaw | https://www.livelaw.in/ | Best for court coverage. RSS: https://www.livelaw.in/feed |
| Bar & Bench | https://www.barandbench.com/ | Legal analysis. RSS: https://www.barandbench.com/feed |
| SCC Online Blog | https://www.scconline.com/blog/ | Supreme Court analysis |
| Verdictum | https://verdictum.in/ | Court judgments in plain English |
| Legal India | https://www.legalindia.com/ | Case law news |

### Regional Crime (Key States)
| Source | State | URL |
|--------|-------|-----|
| The New Indian Express | South India | https://www.newindianexpress.com/nation |
| Deccan Herald | Karnataka | https://www.deccanherald.com/crime |
| Tribune India | Punjab/Haryana | https://www.tribuneindia.com/news/nation |
| Telangana Today | Telangana | https://telanganatoday.com/category/crime |

---

## 2. Court Judgments (Primary Legal Source)

### Indian Kanoon (MOST IMPORTANT)
- **URL:** https://indiankanoon.org/
- **API:** https://api.indiankanoon.org/ (free, registration required)
- **Search:** https://indiankanoon.org/search/?formInput={query}
- **What it has:** Full text of Supreme Court, High Court judgments, FIR references, CBI charge sheets
- **How to use:** Search case name → download full judgment text → extract facts, timeline, legal findings
- **Rate limit:** ~100 requests/day on free tier
- **Format:** Plain text + HTML

```python
# Indian Kanoon API usage
import requests

def search_judgment(case_name):
    url = f"https://api.indiankanoon.org/search/"
    params = {"formInput": case_name, "pagenum": 0}
    headers = {"Authorization": "Token YOUR_TOKEN"}
    return requests.post(url, data=params, headers=headers).json()
```

### Supreme Court of India
- **Official:** https://www.sci.gov.in/
- **Judgments:** https://www.sci.gov.in/judgements
- **Search:** https://www.sci.gov.in/case-status (case number lookup)
- **Notes:** Official source but harder to parse; Indian Kanoon is better for bulk research

### High Courts (State-wise)
| Court | URL | Notes |
|-------|-----|-------|
| Delhi High Court | https://delhihighcourt.nic.in/ | Key for Delhi cases |
| Bombay High Court | https://bombayhighcourt.nic.in/ | Maharashtra cases |
| Allahabad HC | https://www.allahabadhighcourt.in/ | UP, Uttarakhand |
| Madras HC | https://www.hcmadras.tn.nic.in/ | Tamil Nadu |
| Karnataka HC | https://karnatakajudiciary.kar.nic.in/ | Karnataka |
| Calcutta HC | https://calcuttahighcourt.gov.in/ | West Bengal |

### eCourts (District Court Records)
- **URL:** https://ecourts.gov.in/
- **Case status:** https://services.ecourts.gov.in/ecourtindia_vs/
- **Has:** District court orders, bail orders, charge sheets
- **Search by:** Case number, CNR number, party name

---

## 3. Police & Investigation Agency Reports

### CBI (Central Bureau of Investigation)
| Resource | URL | Notes |
|----------|-----|-------|
| Official site | https://cbi.gov.in/ | |
| Press releases | https://cbi.gov.in/press-releases | All CBI case announcements |
| Charge sheets | Search via Indian Kanoon or LiveLaw | Not directly downloadable |
| Annual reports | https://cbi.gov.in/annual-reports | CBI performance data |

### NCRB (National Crime Records Bureau) — CRITICAL DATA SOURCE
| Resource | URL | Notes |
|----------|-----|-------|
| Crime in India reports | https://ncrb.gov.in/crime-in-india.html | Annual, state-wise crime data |
| 2022 report | https://ncrb.gov.in/uploads/nationalcrimerecordsbureau/custom/CrimeinIndia2022.pdf | Latest available |
| 2021 report | https://ncrb.gov.in/uploads/nationalcrimerecordsbureau/custom/CrimeinIndia2021Complete.pdf | |
| Prison statistics | https://ncrb.gov.in/prison-statistics-india.html | |
| Accidental deaths | https://ncrb.gov.in/accidental-deaths-suicides-in-india.html | |
| **API:** None | Scrape PDF + parse | Use pdfplumber Python lib |

```python
# Download NCRB reports
import requests

NCRB_REPORTS = {
    "2022": "https://ncrb.gov.in/uploads/nationalcrimerecordsbureau/custom/CrimeinIndia2022.pdf",
    "2021": "https://ncrb.gov.in/uploads/nationalcrimerecordsbureau/custom/CrimeinIndia2021Complete.pdf",
}

def download_ncrb_report(year):
    url = NCRB_REPORTS[year]
    r = requests.get(url, stream=True)
    with open(f"data/reports/ncrb_crime_india_{year}.pdf", "wb") as f:
        f.write(r.content)
```

### Other Investigation Agencies
| Agency | URL | What They Publish |
|--------|-----|------------------|
| NIA (Natl Investigation Agency) | https://nia.gov.in/ | Terror cases, press releases |
| ED (Enforcement Directorate) | https://enforcementdirectorate.gov.in/ | Financial crime press notes |
| NCB (Narcotics) | https://narcoticsindia.nic.in/ | Drug cases |
| SFIO (Serious Fraud) | https://sfio.nic.in/ | Corporate fraud reports |
| CVC (Central Vigilance) | https://cvc.gov.in/ | Corruption cases |

### State Police Press Releases
| State | URL |
|-------|-----|
| Delhi Police | https://www.delhipolice.gov.in/press-release |
| Maharashtra Police | https://mahapolice.gov.in/ |
| UP Police | https://uppolice.gov.in/ |
| Karnataka Police | https://ksp.karnataka.gov.in/ |
| Tamil Nadu Police | https://www.tnpolice.gov.in/ |

---

## 4. Government Reports & RTI

### Ministry of Home Affairs
- **URL:** https://www.mha.gov.in/
- **Annual reports:** https://www.mha.gov.in/MHA1/Par2017/pdfs/par2022-23.pdf
- **Crime stats:** https://www.mha.gov.in/sites/default/files/CriminalJusticeSystem.pdf

### RTI (Right to Information) Disclosures
- **Portal:** https://rtionline.gov.in/
- **Use:** File RTI for specific case documents, police records
- **Note:** 30-day response time. Use for specific deep-dive cases.
- **Central RTI:** https://cic.gov.in/ (for central govt agencies)

### National Commission for Women
- **URL:** https://ncw.nic.in/
- **Reports:** https://ncw.nic.in/reports
- **Use:** Women victim cases, dowry deaths, trafficking stats

### Press Information Bureau (Govt press releases)
- **URL:** https://pib.gov.in/
- **Search:** https://pib.gov.in/allRel.aspx
- **Use:** Official government statements on high-profile cases

---

## 5. News Archives (Historical Cases)

### For Pre-2010 Cases
| Source | URL | Notes |
|--------|-----|-------|
| The Hindu Archives | https://www.thehindu.com/archive/ | Searchable by date, free |
| Times of India Archives | https://timesofindia.indiatimes.com/archive.cms | Partial free access |
| Indian Express Archive | https://indianexpress.com/archive/ | Searchable |
| Google News Archive | https://news.google.com/ | Use date filter |
| Wayback Machine | https://web.archive.org/ | Archived news pages |

### NewsAPI.io (Programmatic, Last 1 Month)
- **URL:** https://newsapi.org/
- **Free tier:** 100 requests/day, last 30 days
- **Paid:** $149/mo for archives + more requests
- **Python:**
```python
from newsapi import NewsApiClient
newsapi = NewsApiClient(api_key='YOUR_KEY')
articles = newsapi.get_everything(q='Indian crime murder', language='en', sort_by='relevancy')
```

---

## 6. Wikipedia (Secondary Research)
- **Use:** Timeline of events, background context, linked sources
- **NOT primary:** Never cite Wikipedia; use it to find primary sources
- **API:** https://en.wikipedia.org/w/api.php
- **Useful pages:**
  - https://en.wikipedia.org/wiki/Jessica_Lal_murder_case
  - https://en.wikipedia.org/wiki/Aarushi_Talwar_murder_case
  - https://en.wikipedia.org/wiki/Sheena_Bora_murder_case
  - https://en.wikipedia.org/wiki/Nanavati_v._State_of_Maharashtra

---

## 7. B-Roll Video Sources

| Source | URL | Cost | License | Quality |
|--------|-----|------|---------|---------|
| Pexels API | https://api.pexels.com/ | Free | CC0 | Good |
| Pixabay API | https://pixabay.com/api/docs/ | Free | CC0 | Good |
| Unsplash (photos) | https://api.unsplash.com/ | Free | CC0 | Excellent |
| Storyblocks | https://www.storyblocks.com/ | $35/mo | Licensed | Excellent |
| Archive.org | https://archive.org/details/movies | Free | Varies | Historical |
| Doordarshan Archives | https://www.ddinews.gov.in/ | Free | Public domain | Old India footage |
| Videvo | https://www.videvo.net/ | Free tier | Mixed | Good |

```python
# Pexels API B-roll fetch
import requests

PEXELS_KEY = "YOUR_KEY"

def fetch_broll(query, per_page=5):
    url = "https://api.pexels.com/videos/search"
    headers = {"Authorization": PEXELS_KEY}
    params = {"query": query, "per_page": per_page, "orientation": "landscape"}
    r = requests.get(url, headers=headers, params=params)
    videos = r.json()["videos"]
    return [v["video_files"][0]["link"] for v in videos]
```

---

## 8. Data Freshness Policy

| Source Type | Cache Duration | Re-fetch When |
|-------------|---------------|---------------|
| RSS news feeds | 6 hours | Scheduled scraper |
| Court judgments | Permanent | Case closed or new ruling |
| NCRB reports | Annual | New report published |
| CBI press releases | 24 hours | Breaking case |
| B-roll videos | Permanent (once downloaded) | Never re-fetch same clip |
| Wikipedia | Per-case research only | Script writing phase |

---

## 9. Source Citation Format (in Scripts)

When Claude writes scripts, cite sources in this format (removed from TTS, kept in description):
```
[SOURCE: LiveLaw, 2019-03-14 — Delhi HC judgment text]
[SOURCE: CBI Press Release, 2021-08-02 — Charge sheet filed]
[SOURCE: NCRB 2022, Table 2.3 — Delhi crime stats]
[SOURCE: Indian Kanoon — W.P. 1234/2019]
```

These become YouTube video description citations. Builds credibility.

---

## 10. Scraping Rules

1. Always check `robots.txt` before scraping
2. Use NewsAPI for commercial content (licensed)
3. Delay between requests: minimum 2 seconds
4. Identify bot in User-Agent: `IndianCrimeChannel-Research/1.0`
5. Never download paywalled content
6. Cache everything locally — don't re-scrape what's already saved
7. Indian Kanoon: Use API (not scraping) — registration required
