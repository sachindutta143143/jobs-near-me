import requests
import json
import time
import os
import hashlib
import re
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9"
}

SCRAPED_FILE = "scraped.json"


def make_id(title, link):
    return hashlib.md5((title + link).encode("utf-8")).hexdigest()[:12]


def load_old():
    if not os.path.exists(SCRAPED_FILE):
        return []
    try:
        with open(SCRAPED_FILE, encoding="utf-8") as f:
            return json.load(f)
    except:
        return []


def save_jobs(new_jobs):
    old = load_old()
    existing = {j["id"]: j for j in old}
    added = 0

    for j in new_jobs:
        if j["id"] not in existing:
            old.append(j)
            added += 1
        else:
            oj = existing[j["id"]]
            if oj.get("edited"):
                continue
            if not oj.get("details"):
                oj["details"] = j.get("details", "")
            if not oj.get("image"):
                oj["image"] = j.get("image", "")
            if not oj.get("apply_link"):
                oj["apply_link"] = j.get("apply_link", "")

    old.sort(key=lambda x: x.get("created_at", 0), reverse=True)

    with open(SCRAPED_FILE, "w", encoding="utf-8") as f:
        json.dump(old, f, indent=2, ensure_ascii=False)

    print(f"💾 Saved: {added} new | Total: {len(old)}")


def is_job(title):
    t = title.lower()
    bad = ["admit", "result", "answer key", "syllabus", "login", "download", "certificate"]
    if any(b in t for b in bad):
        return False
    good = ["recruitment", "vacancy", "job", "apply", "post", "bharti", "notification", "walk-in", "opening", "hiring"]
    return any(g in t for g in good) or len(title) > 30


def detect_cat(title):
    t = title.lower()
    if "private" in t or "company" in t or "startup" in t:
        return "private"
    if "all india" in t or "central" in t or "ssc" in t or "upsc" in t or "railway" in t or "bank" in t:
        return "india"
    return "assam"


def detect_loc(title, default="India"):
    t = title.lower()
    states = {
        "assam": "Assam", "delhi": "Delhi", "mumbai": "Mumbai", "kolkata": "Kolkata",
        "bihar": "Bihar", "guwahati": "Guwahati", "bangalore": "Bangalore",
        "chennai": "Chennai", "hyderabad": "Hyderabad", "pune": "Pune",
        "rajasthan": "Rajasthan", "gujarat": "Gujarat", "kerala": "Kerala",
        "maharashtra": "Maharashtra", "karnataka": "Karnataka"
    }
    for k, v in states.items():
        if k in t:
            return v
    return default


def get_page(url, timeout=15):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  ❌ {url}: {e}")
    return None


def get_image(soup, base=""):
    try:
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            return og["content"]

        for img in soup.find_all("img", limit=8):
            src = img.get("src") or img.get("data-src") or ""
            if not src:
                continue
            if any(x in src.lower() for x in ["logo", "icon", "avatar", "1x1", "pixel", "emoji", "gravatar"]):
                continue
            w = img.get("width", "999")
            try:
                if int(w) < 80:
                    continue
            except:
                pass
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = urljoin(base, src)
            elif not src.startswith("http"):
                src = urljoin(base, src)
            return src
    except:
        pass
    return ""


def get_details(soup):
    try:
        for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        c = soup.find("article") or soup.find("div", class_="entry-content") or soup.find("div", class_="post-content") or soup.find("div", class_="td-post-content") or soup.find("main") or soup.find("body")
        if not c:
            return ""
        text = c.get_text("\n")
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines)[:4000]
    except:
        return ""


def get_apply(soup):
    try:
        for a in soup.find_all("a"):
            txt = a.get_text().lower()
            href = a.get("href", "")
            if any(k in txt for k in ["apply online", "apply now", "apply here", "click here to apply"]):
                if href and href.startswith("http"):
                    return href
    except:
        pass
    return ""


def scrape_blog_site(url, source, default_loc="India", default_cat="india"):
    """Generic blog scraper for WordPress-style sites"""
    print(f"\n🌐 Scraping: {source} ({url})")
    jobs = []

    soup = get_page(url)
    if not soup:
        return jobs

    articles = soup.find_all("article", limit=25)
    if not articles:
        articles = soup.find_all("div", class_=re.compile("post|entry|job"), limit=25)

    links_done = set()

    for art in articles:
        try:
            a = art.find("a")
            title_tag = art.find(["h2", "h3", "h4"])
            if not a:
                continue

            title = (title_tag or a).get_text(strip=True)
            link = a.get("href", "")
            if not title or not link or len(title) < 15:
                continue
            if not link.startswith("http"):
                link = urljoin(url, link)
            if link in links_done:
                continue
            links_done.add(link)

            if not is_job(title):
                continue

            # Scrape detail page
            detail_soup = get_page(link)
            details = ""
            image = ""
            apply_link = ""

            if detail_soup:
                details = get_details(detail_soup)
                image = get_image(detail_soup, link)
                apply_link = get_apply(detail_soup)

            if not image:
                image = get_image(art, url)

            cat = detect_cat(title)
            if cat == "assam" and default_cat != "assam":
                cat = default_cat

            jobs.append({
                "id": make_id(title, link),
                "title": title,
                "details": details,
                "image": image,
                "link": link,
                "apply_link": apply_link or link,
                "link2": "",
                "link3": "",
                "location": detect_loc(title, default_loc),
                "category": cat,
                "job_type": cat,
                "source": source,
                "status": "scraped",
                "created_at": int(time.time()),
                "edited": False,
                "deadline": "",
            })

            time.sleep(0.5)

        except Exception as e:
            continue

    print(f"  ✅ {len(jobs)} jobs from {source}")
    return jobs


def scrape_link_list(url, source, default_loc="All India", default_cat="india"):
    """For sites that are just lists of links (like SarkariResult)"""
    print(f"\n🌐 Scraping: {source} ({url})")
    jobs = []

    soup = get_page(url)
    if not soup:
        return jobs

    links_done = set()

    for a in soup.find_all("a", limit=60):
        try:
            title = a.get_text(strip=True)
            href = a.get("href", "")

            if not title or len(title) < 20:
                continue
            if not href or href.startswith("#") or "javascript" in href:
                continue

            if not href.startswith("http"):
                href = urljoin(url, href)

            if href in links_done:
                continue
            links_done.add(href)

            skip = ["home", "about", "contact", "privacy", "disclaimer", "sitemap", "login"]
            if any(s in title.lower() for s in skip):
                continue

            if not is_job(title):
                continue

            cat = detect_cat(title)
            if cat == "assam" and default_cat != "assam":
                cat = default_cat

            jobs.append({
                "id": make_id(title, href),
                "title": title,
                "details": "",
                "image": "",
                "link": href,
                "apply_link": href,
                "link2": "",
                "link3": "",
                "location": detect_loc(title, default_loc),
                "category": cat,
                "job_type": cat,
                "source": source,
                "status": "scraped",
                "created_at": int(time.time()),
                "edited": False,
                "deadline": "",
            })

        except:
            continue

    print(f"  ✅ {len(jobs)} jobs from {source}")
    return jobs


# =====================================================
# 🔥 ALL 10 SCRAPERS
# =====================================================

def scrape_all():
    print("\n" + "=" * 60)
    print(f"🚀 SCRAPER STARTED — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    all_jobs = []

    # 1. Assam Career
    try:
        all_jobs += scrape_blog_site("https://www.assamcareer.com", "AssamCareer", "Assam", "assam")
    except Exception as e:
        print(f"❌ AssamCareer: {e}")

    time.sleep(1)

    # 2. Job Assam
    try:
        all_jobs += scrape_blog_site("https://jobassam.in", "JobAssam", "Assam", "assam")
    except Exception as e:
        print(f"❌ JobAssam: {e}")

    time.sleep(1)

    # 3. Naukri Assam
    try:
        all_jobs += scrape_blog_site("https://www.naukriassam.com", "NaukriAssam", "Assam", "assam")
    except Exception as e:
        print(f"❌ NaukriAssam: {e}")

    time.sleep(1)

    # 4. Sarkari Result
    try:
        all_jobs += scrape_link_list("https://www.sarkariresult.com/latestjob.php", "SarkariResult", "All India", "india")
    except Exception as e:
        print(f"❌ SarkariResult: {e}")

    time.sleep(1)

    # 5. Free Job Alert
    try:
        all_jobs += scrape_link_list("https://www.freejobalert.com/latest-notifications/", "FreeJobAlert", "All India", "india")
    except Exception as e:
        print(f"❌ FreeJobAlert: {e}")

    time.sleep(1)

    # 6. Employment News
    try:
        all_jobs += scrape_blog_site("https://www.employmentnews.gov.in", "EmploymentNews", "All India", "india")
    except Exception as e:
        print(f"❌ EmploymentNews: {e}")

    time.sleep(1)

    # 7. Sarkari Exam
    try:
        all_jobs += scrape_link_list("https://www.sarkariexam.com/government-jobs", "SarkariExam", "All India", "india")
    except Exception as e:
        print(f"❌ SarkariExam: {e}")

    time.sleep(1)

    # 8. Freshersworld
    try:
        all_jobs += scrape_blog_site("https://www.freshersworld.com/jobs/category/latest-govt-jobs", "Freshersworld", "All India", "india")
    except Exception as e:
        print(f"❌ Freshersworld: {e}")

    time.sleep(1)

    # 9. Indeed (Private)
    try:
        all_jobs += scrape_link_list("https://assamjobalerts.com", "Indeed", "All India", "private")
    except Exception as e:
        print(f"❌ Indeed: {e}")

    time.sleep(1)

    # 10. NorthEast Jobs
    try:
        all_jobs += scrape_blog_site("https://assamjobalerts.com", "NorthEastNow", "North East", "assam")
    except Exception as e:
        print(f"❌ NorthEast: {e}")

    # Remove duplicates
    unique = {}
    for j in all_jobs:
        key = j["id"]
        if key not in unique:
            unique[key] = j
    final = list(unique.values())

    print(f"\n🔥 Total unique: {len(final)}")
    save_jobs(final)

    print(f"✅ SCRAPER DONE — {time.strftime('%H:%M:%S')}")
    print("=" * 60 + "\n")

    return len(final)


if __name__ == "__main__":
    scrape_all()