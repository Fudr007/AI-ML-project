import requests
from bs4 import BeautifulSoup
import json
import time
import threading
from queue import Queue, Empty
from datetime import datetime
import re
from concurrent.futures import ThreadPoolExecutor
import os

# ================= KONFIGURACE =================
PAGE_START = 1
PAGE_MAX = 500
PAGE_COUNTER = PAGE_START
PAGE_LOCK = threading.Lock()

ALLOWED_DOMAIN = "sauto.cz"
MAX_THREADS = 10

OUTPUT_FILE = "sauto_ojete_auta.jsonl"
VISITED_FILE = "visited_urls_sauto.txt"

ARTICLE_BUFFER = []
BUFFER_LOCK = threading.Lock()
BUFFER_SIZE = 50

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ================= SDÍLENÉ PROMĚNNÉ =================
url_queue = Queue()
visited_urls = set()
visited_lock = threading.Lock()
file_lock = threading.Lock()
thread_local = threading.local()


# ================= POMOCNÉ FUNKCE =================
def load_visited():
    if os.path.exists(VISITED_FILE):
        with open(VISITED_FILE, "r", encoding="utf-8") as f:
            for line in f:
                visited_urls.add(line.strip())
    print(f"📂 Načteno {len(visited_urls)} navštívených URL")


def save_visited(url):
    with open(VISITED_FILE, "a", encoding="utf-8") as f:
        f.write(url + "\n")


def is_valid_detail_url(url: str) -> bool:
    """Kontrola, zda URL odpovídá detailu inzerátu"""
    if ALLOWED_DOMAIN not in url:
        return False
    if not url.startswith("https://www.sauto.cz/osobni/detail/"):
        return False

    blacklist = [".jpg", ".png", ".gif", ".pdf", "mailto:", "#"]
    return not any(b in url for b in blacklist)


def flush_buffer(force=False):
    global ARTICLE_BUFFER

    if not ARTICLE_BUFFER:
        return

    if len(ARTICLE_BUFFER) >= BUFFER_SIZE or force:
        with file_lock:
            with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                f.write("\n".join(ARTICLE_BUFFER) + "\n")

        print(f"💾 Uloženo {len(ARTICLE_BUFFER)} inzerátů")
        ARTICLE_BUFFER.clear()


def get_session():
    if not hasattr(thread_local, "session"):
        thread_local.session = requests.Session()
        thread_local.session.headers.update(HEADERS)
    return thread_local.session


def get_next_listing_url():
    """Vrátí další URL stránky s výpisem inzerátů"""
    global PAGE_COUNTER

    with PAGE_LOCK:
        if PAGE_COUNTER > PAGE_MAX:
            return None

        url = f"https://www.sauto.cz/inzerce/osobni/?stav=ojete&strana={PAGE_COUNTER}"
        PAGE_COUNTER += 1
        return url


def extract_car_data(soup, url):
    """Extrahuje data o autě ze stránky detailu"""
    try:
        car_data = {
            "url": url,
            "značka": None,
            "model": None,
            "rok_výroby": None,
            "karoserie": None,
            "palivo": None,
            "převodovka": None,
            "výkon": None,
            "cena": None,
            "stav_km": None,
            "scraped_at": datetime.now().isoformat()
        }

        # Značka a model - obvykle v h1 nebo title
        url_parts = url.split('/')
        if 'detail' in url_parts:
            idx = url_parts.index('detail')
            if len(url_parts) > idx + 1: car_data["značka"] = url_parts[idx + 1].capitalize()
            if len(url_parts) > idx + 2: car_data["model"] = url_parts[idx + 2].upper()

        # Hledání parametrů v tabulce/seznamu parametrů
        # Sauto.cz má parametry v různých formátech, zkusíme několik způsobů

        # Způsob 1: tabulka s parametry
        params_table = soup.find_all("tr")
        for row in params_table:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)

                if "rok" in label or "výrob" in label:
                    # Extrahuj pouze rok (číslo)
                    year_match = re.search(r'\b(19|20)\d{2}\b', value)
                    if year_match:
                        car_data["rok_výroby"] = int(year_match.group())

                elif "karoserie" in label or "karosérie" in label:
                    car_data["karoserie"] = value

                elif "palivo" in label:
                    car_data["palivo"] = value

                elif "převodovka" in label or "prevodovka" in label:
                    car_data["převodovka"] = value

                elif "výkon" in label or "vykon" in label:
                    # Extrahuj kW nebo HP
                    power_match = re.search(r'(\d+)\s*(kW|HP|hp|k)', value, re.IGNORECASE)
                    if power_match:
                        car_data["výkon"] = power_match.group(1) + " " + power_match.group(2)
                    else:
                        car_data["výkon"] = value

                elif "cena" in label:
                    # Odstraň měnu a formátování
                    price = re.sub(r'[^\d]', '', value)
                    if price:
                        car_data["cena"] = int(price)

                elif "tachometr" in label or "najeto" in label or "km" in label.lower():
                    km = re.sub(r'[^\d]', '', value)
                    if km:
                        car_data["stav_km"] = int(km)

        # Způsob 2: meta tagy a strukturovaná data
        if not car_data["cena"]:
            price_tag = soup.find("span", class_=re.compile(r"price|cena", re.I))
            if price_tag:
                price_text = price_tag.get_text(strip=True)
                price = re.sub(r'[^\d]', '', price_text)
                if price:
                    car_data["cena"] = int(price)

        desc_meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
        if desc_meta:
            desc_text = desc_meta.get("content", "")
            if not car_data["cena"]:
                c = re.search(r"cena ([\d\s]+) Kč", desc_text)
                if c: car_data["cena"] = int(re.sub(r"\s", "", c.group(1)))

        # Způsob 3: DD/DT seznamy
        dt_tags = soup.find_all("dt")
        dd_tags = soup.find_all("dd")

        for i, dt in enumerate(dt_tags):
            if i < len(dd_tags):
                label = dt.get_text(strip=True).lower()
                value = dd_tags[i].get_text(strip=True)

                if "karoserie" in label or "karosérie" in label:
                    car_data["karoserie"] = value

                elif "palivo" in label:
                    car_data["palivo"] = value

                elif "převodovka" in label or "prevodovka" in label:
                    car_data["převodovka"] = value

                elif "výkon" in label or "vykon" in label:
                    power_match = re.search(r'(\d+)\s*(kW|HP|hp|k)', value, re.IGNORECASE)
                    if power_match:
                        car_data["výkon"] = power_match.group(1) + " " + power_match.group(2)
                    else:
                        car_data["výkon"] = value

                elif "najeto" in label or "tachometr" in label:
                    km = re.sub(r'[^\d]', '', value)
                    if km:
                        car_data["stav_km"] = int(km)

        # Způsob 4: TH/TD tabulky
        th_tags = soup.find_all("th")
        td_tags = soup.find_all("td")
        for i, th in enumerate(th_tags):
            if i < len(td_tags):
                label = th.get_text(strip=True).lower()
                value = td_tags[i].get_text(strip=True)

                if "provozu" in label:
                    car_data["rok_výroby"] = value

                if not car_data["rok_výroby"]:
                    if "Vyrobeno" in label:
                        car_data["rok_výroby"] = value
                    else:
                        car_data["rok_výroby"] = None

        # Kontrola, že máme alespoň základní data
        if car_data["značka"] and car_data["model"]:
            return car_data

        return None

    except Exception as e:
        print(f"❌ Chyba při parsování {url}: {e}")
        return None


# ================= HLAVNÍ WORKER =================
def worker(url):
    try:
        session = get_session()

        # Malá pauza mezi requesty (antiban)
        time.sleep(0.5)

        r = session.get(url, timeout=15)

        if r.status_code != 200:
            return

        soup = BeautifulSoup(r.text, "html.parser")

        # Pokud je to stránka s výpisem, najdi všechny odkazy na detaily
        if "/inzerce/osobni/" in url:
            for a in soup.find_all("a", href=True):
                href = a["href"]

                # Doplň absolutní URL
                if href.startswith("/"):
                    href = "https://www.sauto.cz" + href

                # Zkontroluj, že je to detail ojetého auta
                if is_valid_detail_url(href):
                    with visited_lock:
                        if href not in visited_urls:
                            visited_urls.add(href)
                            save_visited(href)
                            url_queue.put(href)

        # Pokud je to detail inzerátu, extrahuj data
        elif "/osobni/detail/" in url:
            # Ověř, že je to opravdu ojeté auto
            page_text = r.text.lower()
            if "nové" in page_text or "nový" in page_text:
                # Další kontrola - pokud není explicitně označeno jako ojeté, přeskoč
                if "ojeté" not in page_text and "ojete" not in page_text and "použité" not in page_text:
                    print(f"⚠️  Přeskočeno (ne-ojeté): {url}")
                    return

            car_data = extract_car_data(soup, url)

            if car_data:
                json_line = json.dumps(car_data, ensure_ascii=False)

                with BUFFER_LOCK:
                    ARTICLE_BUFFER.append(json_line)
                    if len(ARTICLE_BUFFER) >= BUFFER_SIZE:
                        flush_buffer()

                print(f"✅ Uloženo: {car_data['značka']} {car_data['model']}")

    except Exception as e:
        print(f"❌ Chyba při zpracování {url}: {e}")


# ================= MAIN =================
def main():
    print("🚀 Spouštím crawler SAUTO.CZ (ojetá auta)")
    print(f"📄 Rozsah stránek: {PAGE_START} - {PAGE_MAX}")
    print(f"🔧 Počet vláken: {MAX_THREADS}")

    load_visited()

    # Přidej prvních 10 stránek s výpisem
    for _ in range(10):
        listing_url = get_next_listing_url()
        if not listing_url:
            break

        if listing_url not in visited_urls:
            visited_urls.add(listing_url)
            url_queue.put(listing_url)

    try:
        with ThreadPoolExecutor(MAX_THREADS) as executor:
            while True:
                try:
                    url = url_queue.get(timeout=15)
                    executor.submit(worker, url)
                except Empty:
                    if url_queue.empty():
                        print("📚 Fronta prázdná – přidávám další stránky výpisu")

                        added = False
                        for _ in range(10):
                            listing_url = get_next_listing_url()
                            if not listing_url:
                                print("🏁 Dosaženo maximální stránky")
                                return

                            if listing_url not in visited_urls:
                                visited_urls.add(listing_url)
                                url_queue.put(listing_url)
                                added = True

                        if not added:
                            print("🏁 Všechny stránky zpracovány")
                            return

                        time.sleep(2)

    except KeyboardInterrupt:
        print("🛑 Ukončeno uživatelem")
    finally:
        flush_buffer(force=True)
        print(f"✅ Crawling dokončen! Data uložena v {OUTPUT_FILE}")


if __name__ == "__main__":
    if not os.path.exists(VISITED_FILE):
        open(VISITED_FILE, "w").close()
    if not os.path.exists(OUTPUT_FILE):
        open(OUTPUT_FILE, "w").close()
    main()
