import asyncio
import json
import random
import os
from datetime import datetime
from playwright.async_api import async_playwright

TOURNAMENT_ID = "149"  # Bundesliga házená
CONCURRENCY_LIMIT = 100

async def get_match_data(context, match_id):
    try:
        # Paralelní volání obou API
        event_task = context.request.get(f"https://www.sofascore.com/api/v1/event/{match_id}")
        lineups_task = context.request.get(f"https://www.sofascore.com/api/v1/event/{match_id}/lineups")

        event_resp, lineups_resp = await asyncio.gather(event_task, lineups_task)

        if not event_resp.ok:
            return None

        event_json = await event_resp.json()
        event = event_json.get("event", {})

        home_team = event.get("homeTeam", {}).get("name", "Unknown Home")
        away_team = event.get("awayTeam", {}).get("name", "Unknown Away")

        # Celkové skóre
        home_goals = event.get("homeScore", {}).get("current", 0)
        away_goals = event.get("awayScore", {}).get("current", 0)

        # Poločasové skóre
        home_ht = event.get("homeScore", {}).get("period1", 0)
        away_ht = event.get("awayScore", {}).get("period1", 0)

        # OPRAVENÉ VYTAŽENÍ TRENÉRŮ Z HLAVNÍHO JSONU
        home_coach = event.get("homeManager", {}).get("name")
        if not home_coach:
            home_coach = event.get("homeTeam", {}).get("manager", {}).get("name", "Unknown")

        away_coach = event.get("awayManager", {}).get("name")
        if not away_coach:
            away_coach = event.get("awayTeam", {}).get("manager", {}).get("name", "Unknown")

        # FILTR ZMETKŮ: Zápas se skóre 0:0 zahodíme
        if int(home_goals) == 0 and int(away_goals) == 0:
            return None

        start_timestamp = event.get("startTimestamp")
        date_final = datetime.fromtimestamp(start_timestamp).strftime('%d.%m.%Y') if start_timestamp else "Unknown Date"

        # Třídění hráčů
        def extract_players(team_data):
            gks, field = [], []
            for item in team_data.get("players", []):
                name = item.get("player", {}).get("name", "Unknown")
                pos = item.get("player", {}).get("position") or item.get("position", "")
                if pos == "G":
                    gks.append(name)
                else:
                    field.append(name)
            return gks, field

        home_gks, home_field = [], []
        away_gks, away_field = [], []

        if lineups_resp.ok:
            lineups_json = await lineups_resp.json()
            if "home" in lineups_json:
                home_gks, home_field = extract_players(lineups_json["home"])
            if "away" in lineups_json:
                away_gks, away_field = extract_players(lineups_json["away"])

        return {
            "match_id": match_id,
            "datum_zapasu": date_final,
            "domaci_tym": home_team.strip(),
            "hoste_tym": away_team.strip(),
            "goly_domaci": home_goals,
            "goly_hoste": away_goals,
            "goly_domaci_polocas": home_ht,
            "goly_hoste_polocas": away_ht,
            "domaci_trener": home_coach,
            "hoste_trener": away_coach,
            "domaci_brankari": home_gks,
            "domaci_hraci_pole": home_field,
            "hoste_brankari": away_gks,
            "hoste_hraci_pole": away_field
        }

    except Exception as e:
        print(f"Chyba u zápasu {match_id}: {e}")
        return None


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print("Zahřívám spojení se SofaScore...")
        await page.goto("https://www.sofascore.com/", wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(3000)

        seen_match_ids = set()
        if os.path.exists("bundesliga_data.jsonl"):
            with open("bundesliga_data.jsonl", "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if "match_id" in data:
                            seen_match_ids.add(str(data["match_id"]))
                    except:
                        continue
            print(f"Načteno {len(seen_match_ids)} již zpracovaných zápasů.")

        state = {"saved_count": len(seen_match_ids)}
        file_lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        async def process_match_worker(m_id, file_obj):
            async with semaphore:
                await asyncio.sleep(random.uniform(0.1, 0.8))
                data = await get_match_data(context, m_id)
                if data:
                    async with file_lock:
                        file_obj.write(json.dumps(data, ensure_ascii=False) + "\n")
                        file_obj.flush()
                        seen_match_ids.add(m_id)
                        state["saved_count"] += 1
                        print(
                            f"[{state['saved_count']}] Uloženo: {data['domaci_tym']} {data['goly_domaci']}:{data['goly_hoste']} {data['hoste_tym']} (Pol: {data['goly_domaci_polocas']}:{data['goly_hoste_polocas']}) | Trenéři: {data['domaci_trener']} vs {data['hoste_trener']}"
                        )

        print("\nStahuji seznam všech dostupných sezón...")
        seasons_resp = await context.request.get(
            f"https://www.sofascore.com/api/v1/unique-tournament/{TOURNAMENT_ID}/seasons")

        if not seasons_resp.ok:
            print("Nepodařilo se načíst seznam sezón.")
            await browser.close()
            return

        all_seasons = (await seasons_resp.json()).get("seasons", [])

        with open("bundesliga_data.jsonl", "a", encoding="utf-8") as f:
            for season in all_seasons:
                season_id = str(season.get("id"))
                season_name = season.get("name", "Unknown")

                if "cancel" in season_name.lower() or "zruš" in season_name.lower():
                    continue

                print(f"\n--- Zpracovávám sezónu: {season_name} ---")

                try:
                    match_ids_in_season = []
                    page_num = 0

                    while True:
                        api_url = f"https://www.sofascore.com/api/v1/unique-tournament/{TOURNAMENT_ID}/season/{season_id}/events/last/{page_num}"
                        resp = await context.request.get(api_url)
                        if not resp.ok: break
                        events_list = (await resp.json()).get("events", [])
                        if not events_list: break

                        for ev in events_list:
                            if str(ev["id"]) not in seen_match_ids:
                                match_ids_in_season.append(str(ev["id"]))
                        page_num += 1

                    if match_ids_in_season:
                        print(f"Nalezeno {len(match_ids_in_season)} nových zápasů.")
                        tasks = [process_match_worker(m_id, f) for m_id in match_ids_in_season]
                        await asyncio.gather(*tasks)

                except Exception as e:
                    print(f"Chyba v sezóně {season_name}: {e}")

        await browser.close()
        print(f"\nHotovo! Celkem uloženo {state['saved_count']} perfektně čistých zápasů.")


if __name__ == "__main__":
    asyncio.run(main())