import asyncio
import json
import random
import os
from datetime import datetime
from playwright.async_api import async_playwright

TOURNAMENT_ID = "149"
CONCURRENCY_LIMIT = 100

async def get_match_data(context, match_id):
    try:
        # 1. PARALELNÍ VOLÁNÍ: Základní info, Sestavy a Kurzy
        event_task = context.request.get(f"https://www.sofascore.com/api/v1/event/{match_id}")
        lineups_task = context.request.get(f"https://www.sofascore.com/api/v1/event/{match_id}/lineups")
        odds_task = context.request.get(f"https://www.sofascore.com/api/v1/event/{match_id}/odds/1/all")

        resps = await asyncio.gather(event_task, lineups_task, odds_task)
        event_resp, lineups_resp, odds_resp = resps

        if not event_resp.ok:
            return None

        # --- ZÁKLADNÍ INFO O ZÁPASU ---
        event_json = await event_resp.json()
        event = event_json.get("event", {})

        home_team = event.get("homeTeam", {}).get("name", "Unknown Home")
        away_team = event.get("awayTeam", {}).get("name", "Unknown Away")
        home_goals = event.get("homeScore", {}).get("current", 0)
        away_goals = event.get("awayScore", {}).get("current", 0)

        start_ts = event.get("startTimestamp")
        date_final = datetime.fromtimestamp(start_ts).strftime('%d.%m.%Y') if start_ts else "Unknown Date"

        # --- HRÁČI A RATINGY ---
        home_players_data = []
        away_players_data = []

        if lineups_resp.ok:
            lineups_json = await lineups_resp.json()

            # Pomocná funkce pro vytažení dat z listu hráčů
            def parse_players(player_list):
                extracted = []
                for p in player_list:
                    p_name = p.get("player", {}).get("name", "Unknown Player")
                    p_pos = p.get("player", {}).get("position", "")  # 'G' = Goalkeeper
                    stats = p.get("statistics", {})

                    # Logika pro brankáře
                    if p_pos == "G":
                        # SofaScore posílá 'saves' a 'shotsFaced'
                        saves = stats.get("saves", 0)
                        shots = stats.get("shotsFaced", 0)
                        # Výpočet procent (např. 0.35 pro 35%)
                        save_percentage = round(saves / shots, 2) if shots and shots > 0 else 0.0

                        extracted.append({
                            "jmeno": p_name,
                            "uspesnost_zakroku": save_percentage,
                            "zakroky": saves
                        })

                    # Logika pro hráče v poli
                    else:
                        p_goals = stats.get("goals", 0)
                        extracted.append({
                            "jmeno": p_name,
                            "goly": int(p_goals) if p_goals else 0
                        })
                return extracted

            home_players_data = parse_players(lineups_json.get("home", {}).get("players", []))
            away_players_data = parse_players(lineups_json.get("away", {}).get("players", []))

        # --- KURZY (1X2) ---
        kurz_1, kurz_X, kurz_2 = None, None, None
        if odds_resp.ok:
            odds_json = await odds_resp.json()
            for market in odds_json.get("markets", []):
                if market.get("marketName") == "Full time":
                    for choice in market.get("choices", []):
                        name = choice.get("name")
                        frac = choice.get("fractionalValue")
                        if frac and "/" in frac:
                            n, d = frac.split("/")
                            # Výpočet desetinného kurzu: 1 + (n/d)
                            decimal_odd = round(1 + (int(n) / int(d)), 2)
                            if name == "1":
                                kurz_1 = decimal_odd
                            elif name == "X":
                                kurz_X = decimal_odd
                            elif name == "2":
                                kurz_2 = decimal_odd
                    break

        # --- FINÁLNÍ OBJEKT ---
        return {
            "match_id": str(match_id),
            "datum_zapasu": date_final,
            "domaci_tym": home_team.strip(),
            "hoste_tym": away_team.strip(),
            "goly_domaci": int(home_goals),
            "goly_hoste": int(away_goals),
            "kurz_domaci": kurz_1,
            "kurz_remiza": kurz_X,
            "kurz_hoste": kurz_2,
            "domaci_hraci": home_players_data,
            "hoste_hraci": away_players_data
        }

    except Exception as e:
        print(f"Chyba u match_id {match_id}: {e}")
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
        if os.path.exists("bundesliga_data_w_kurz.jsonl"):
            with open("bundesliga_data_w_kurz.jsonl", "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        if "match_id" in data:
                            seen_match_ids.add(str(data["match_id"]))
                    except json.JSONDecodeError:
                        continue
            print(f"Načteno {len(seen_match_ids)} již zpracovaných zápasů.")

        # Globální čítač a zámek pro zápis do souboru
        state = {"saved_count": len(seen_match_ids)}
        file_lock = asyncio.Lock()
        semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

        # 2. DEFINICE WORKERA PRO SOUBĚŽNÉ ZPRACOVÁNÍ ZÁPASŮ
        async def process_match_worker(m_id, file_obj):
            async with semaphore:  # Zajistí, že nikdy neběží víc než 'CONCURRENCY_LIMIT' úloh
                # Malé náhodné zpoždění před samotným spuštěním, abychom neodeslali 5 dotazů v jedinou milisekundu
                await asyncio.sleep(random.uniform(0.1, 0.8))

                data = await get_match_data(context, m_id)
                if data:
                    async with file_lock:  # Zámek: sem v jednu chvíli vstoupí jen jeden zápas
                        file_obj.write(json.dumps(data, ensure_ascii=False) + "\n")
                        file_obj.flush()
                        seen_match_ids.add(m_id)
                        state["saved_count"] += 1
                        print(
                            f"[{state['saved_count']}] Uloženo: {data['datum_zapasu']} | {data['domaci_tym']} {data['goly_domaci']}:{data['goly_hoste']} {data['hoste_tym']}")

        print("\nStahuji seznam všech dostupných sezón...")
        seasons_resp = await context.request.get(
            f"https://www.sofascore.com/api/v1/unique-tournament/{TOURNAMENT_ID}/seasons")

        if not seasons_resp.ok:
            print("Nepodařilo se načíst seznam sezón ze serveru.")
            await browser.close()
            return

        seasons_data = await seasons_resp.json()
        all_seasons = seasons_data.get("seasons", [])

        with open("bundesliga_data_w_score.jsonl", "a", encoding="utf-8") as f:
            for season in all_seasons:
                season_id = str(season.get("id"))
                season_name = season.get("name", "Unknown")
                season_year = season.get("year", "Unknown")

                if "cancel" in season_name.lower() or "zruš" in season_name.lower():
                    continue

                print(f"\n--- Zpracovávám sezónu: {season_name} ({season_year}) ---")

                try:
                    match_ids_in_season = []
                    page_num = 0

                    while True:
                        api_url = f"https://www.sofascore.com/api/v1/unique-tournament/{TOURNAMENT_ID}/season/{season_id}/events/last/{page_num}"
                        resp = await context.request.get(api_url)
                        if not resp.ok:
                            break
                        events_list = (await resp.json()).get("events", [])
                        if not events_list:
                            break
                        for ev in events_list:
                            if str(ev["id"]) not in seen_match_ids:
                                match_ids_in_season.append(str(ev["id"]))
                        page_num += 1

                    if not match_ids_in_season:
                        continue

                    print(f"Připraveno ke stahování: {len(match_ids_in_season)} nových zápasů v této sezóně.")

                    # 3. SPOUŠTĚNÍ ÚLOH V DÁVKÁCH
                    # Vytvoříme seznam "slibů" (coroutines) pro všechny zápasy v sezóně
                    tasks = [process_match_worker(m_id, f) for m_id in match_ids_in_season]

                    # Spustíme je všechny. Semafor se postará o to, aby reálně běželo max 5 najednou.
                    if tasks:
                        await asyncio.gather(*tasks)

                except Exception as e:
                    print(f"Chyba při stahování sezóny {season_name}: {e}")

        await browser.close()
        print(f"\nSkript dokončen! Celkem máš uložených {state['saved_count']} unikátních zápasů.")


if __name__ == "__main__":
    asyncio.run(main())