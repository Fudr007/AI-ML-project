import json
import os
from urllib.parse import urlparse

INPUT_FILE = "sauto_ojete_auta.jsonl"
OUTPUT_FILE = "deduplicated.jsonl"
input_urls = "visited_urls.txt"
output_urls = "visited_urls_archive.txt"


def normalize_url(url: str) -> str:
    """
    Remove everything after the first dot in the last URL path segment
    """
    parsed = urlparse(url)
    parts = parsed.path.rstrip("/").split("/")

    if not parts:
        return url

    last = parts[-1]
    if "?" in last:
        last = last.split("?", 1)[0]
        parts[-1] = last

    normalized_path = "/".join(parts)

    return f"{parsed.scheme}://{parsed.netloc}{normalized_path}"

def rm_archive_pages():
    with open(input_urls, "r", encoding="utf-8") as fin, \
         open(output_urls, "w", encoding="utf-8") as fout:
        for line in fin:
            if "https://www.idnes.cz/zpravy/archiv/" in line:
                continue
            fout.write(line)


def main():
    seen = {}
    total = 0
    duplicates = 0
    nulls = 0

    with open(INPUT_FILE, "r", encoding="utf-8") as fin, \
         open(OUTPUT_FILE, "w", encoding="utf-8") as fout:

        for line in fin:
            total += 1
            article = json.loads(line)

            original_url = article.get("url")
            if not original_url:
                continue

            norm_url = normalize_url(original_url)

            if norm_url in seen:
                duplicates += 1
                continue

            if "null" in line:
                nulls += 1
                continue

            seen[norm_url] = original_url
            article["url"] = norm_url
            fout.write(json.dumps(article, ensure_ascii=False) + "\n")

    print("✅ Hotovo")
    print(f"📄 Celkem záznamů: {total}")
    print(f"🧹 Duplicit odstraněno: {duplicates}")
    print(f"📦 Unikátních článků: {total - duplicates}")
    print(f"🫙 Obsahujicich null: {nulls}")
    print(f"💾 Výstupní soubor: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
    #if not os.path.exists(INPUT_FILE):
    #    print("❌ Vstupní soubor neexistuje")
    #else:
    #    main()