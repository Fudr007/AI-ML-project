import ast
import json
import pickle
import re
import numpy as np
import pandas as pd
from flask import Flask, render_template, request, jsonify
from curl_cffi import requests as curl_requests

app = Flask(__name__)

with open('model_domaci.dat', 'rb') as f:
    model_home = pickle.load(f)
with open('model_remiza.dat', 'rb') as f:
    model_draw = pickle.load(f)
with open('model_hoste.dat', 'rb') as f:
    model_away = pickle.load(f)

history = pd.read_csv('bundesliga_pripravena_data.csv')
history['datum_zapasu'] = pd.to_datetime(history['datum_zapasu'])

def form_of_gk(gk_list):
    goalkeeper_data = []
    for gk_name in gk_list:
        mask = (history['domaci_hraci'].str.contains(gk_name, na=False) | history['hoste_hraci'].str.contains(gk_name, na=False))
        goalkeeper_data.append(history[mask])

    if len(goalkeeper_data) == 0:
        return 15.0

    sum = 0.0
    for data in goalkeeper_data:
        sum += data['uspesnost_zakroku_prumer'].mean()

    avg = sum / len(goalkeeper_data)

    if pd.isna(avg):
        return 12.0

    return float(avg)

def goals_of_player(roster_str, player_name):
    try:
        if isinstance(roster_str, str):
            try:
                roster = json.loads(roster_str.replace("'", '"'))
            except:
                roster = ast.literal_eval(roster_str)
        else:
            roster = roster_str

        for player in roster:
            name_data = player.get('jmeno', player.get('name', ''))

            if player_name in name_data:
                return float(player.get('goly', player.get('goals', 0)))

    except Exception:
        pass

    return None

def predicted_goals(players):
    player_names = [name for name in players if name.strip() != ""]

    if not player_names:
        return 15.0

    sum_of_goals = 0.0

    for name in player_names:
        goals_of_one = []

        maska = (
                history['domaci_hraci'].astype(str).str.contains(name, na=False) |
                history['hoste_hraci'].astype(str).str.contains(name, na=False)
        )

        player_matches = history[maska]

        if player_matches.empty:
            sum_of_goals += 1.0
            continue

        for _, match in player_matches.iterrows():
            goals = None

            if name in str(match['domaci_hraci']):
                goals = goals_of_player(match['domaci_hraci'], name)

            if goals is None and name in str(match['hoste_hraci']):
                goals = goals_of_player(match['hoste_hraci'], name)

            if goals is not None:
                goals_of_one.append(goals)

        if len(goals_of_one) > 0:
            avg_player = sum(goals_of_one) / len(goals_of_one)
            sum_of_goals += avg_player
        else:
            sum_of_goals += 1.0

    return sum_of_goals

def h2h_wins_home(team_home, team_away, date):
    history_matches = history[history['datum_zapasu'] < date]

    h2h = history_matches[
        ((history_matches['domaci_tym'] == team_home) & (history_matches['hoste_tym'] == team_away)) |
        ((history_matches['domaci_tym'] == team_away) & (history_matches['hoste_tym'] == team_home))
    ]

    last_five = h2h.tail(5)

    if len(last_five) == 0:
        return 0.5

    wins_home = 0
    for _, match in last_five.iterrows():
        if match['domaci_tym'] == team_home and match['goly_domaci'] > match['goly_hoste']:
            wins_home += 1
        elif match['hoste_tym'] == team_home and match['goly_hoste'] > match['goly_domaci']:
            wins_home += 1

    return wins_home / len(last_five)

@app.route('/', methods=['GET', 'POST'])
def index():
    results = None
    error = None

    if request.method == 'POST':
        try:
            team_home = request.form.get('team_home')
            team_away = request.form.get('team_away')
            date = pd.to_datetime(request.form.get('date'))

            home_gk = request.form.getlist('home_gk')
            home_pl = request.form.getlist('home_pl')

            away_gk = request.form.getlist('away_gk')
            away_pl = request.form.getlist('away_pl')

            form_of_gk(home_gk)


            form_of_gk(away_gk)

            history_home = history[(history['domaci_tym'] == team_home) | (history['hoste_tym'] == team_home)]
            if history_home.empty:
                raise Exception("No data for this team in the history. Check the spelling or try another team.")
            history_home = history_home[history_home['datum_zapasu'] < date].iloc[-1]
            if history_home['domaci_tym'] == team_home:
                elo_h = history_home['elo_domaci']
                form_h = history_home['forma_tymu_domaci']
            elif history_home['hoste_tym'] == team_home:
                elo_h = history_home['elo_hoste']
                form_h = history_home['forma_tymu_hoste']
            else:
                raise Exception()

            history_away = history[(history['domaci_tym'] == team_away) | (history['hoste_tym'] == team_away)]
            if history_home.empty:
                raise Exception("No data for this team in the history. Check the spelling or try another team.")
            history_away = history_away[history_away['datum_zapasu'] < date].iloc[-1]
            if history_away['domaci_tym'] == team_away:
                elo_a = history_away['elo_domaci']
                form_a = history_away['forma_tymu_domaci']
            elif history_away['hoste_tym'] == team_away:
                elo_a = history_away['elo_hoste']
                form_a = history_away['forma_tymu_hoste']
            else:
                raise Exception()

            input_for_models = pd.DataFrame([{
                "forma_tymu_domaci": form_h ,
                "forma_tymu_hoste": form_a,
                "domaci_dane_goly": history_home['domaci_dane_goly'] if history_home['domaci_tym'] == team_home else history_home['hoste_dane_goly'],
                "domaci_dostane_goly": history_home['domaci_dostane_goly'] if history_home['domaci_tym'] == team_home else history_home['hoste_dostane_goly'],
                "hoste_dane_goly": history_away['hoste_dane_goly'] if history_away['hoste_tym'] == team_away else history_away['domaci_dane_goly'],
                "hoste_dostane_goly": history_away['hoste_dostane_goly'] if history_away['hoste_tym'] == team_away else history_away['domaci_dostane_goly'],
                "domaci_forma_doma": history_home['domaci_forma_doma'] if 'domaci_forma_doma' in history_home else 0.5,
                "hoste_forma_venku": history_away['hoste_forma_venku'] if 'hoste_forma_venku' in history_away else 0.5,
                "h2h_uspesnost_domacich": h2h_wins_home(team_home, team_away, date),
                "domaci_ocekavane_goly": predicted_goals(home_pl),
                "hoste_ocekavane_goly": predicted_goals(away_pl),
                "domaci_forma_brankare": form_of_gk(home_gk),
                "hoste_forma_brankare": form_of_gk(away_gk),
                "mesic": date.month,
                "den_v_tydnu": date.dayofweek,
                "elo_domaci": elo_h,
                "elo_hoste": elo_a,
                "elo_rozdil": elo_h - elo_a
            }])

            prob_1 = np.clip(model_home.predict(input_for_models)[0], 0.01, 0.99)
            prob_x = np.clip(model_draw.predict(input_for_models)[0], 0.01, 0.99)
            prob_2 = np.clip(model_away.predict(input_for_models)[0], 0.01, 0.99)

            sum = prob_1 + prob_x + prob_2
            prob_1, prob_x, prob_2 = prob_1 / sum, prob_x / sum, prob_2 / sum

            results = {
                'kurz_1': round(1 / prob_1, 2),
                'kurz_x': round(1 / prob_x, 2),
                'kurz_2': round(1 / prob_2, 2)
            }

        except Exception as e:
            error = f"Could not predict the odds. Detail: {str(e)}"

    sent = request.form if request.method == 'POST' else None
    return render_template('index.html', results=results, error=error, form=sent)

@app.route('/fetch_roster', methods=['POST'])
def fetch_roster():
    data = request.get_json()
    url = data.get('url', '')

    match = re.search(r'id:(\d+)', url)
    if not match:
        return jsonify({'error': 'There is no ID match in the provided URL. Check legitimacy of the URL'}), 400

    event_id = match.group(1)
    api_url = f"https://api.sofascore.com/api/v1/event/{event_id}/lineups"
    api_url_teams = f"https://api.sofascore.com/api/v1/event/{event_id}"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Referer": "https://www.sofascore.com/",
        "Origin": "https://www.sofascore.com",
        "Cache-Control": "no-cache"
    }

    try:
        response = curl_requests.get(api_url, headers=headers, impersonate="chrome110")
        response_teams = curl_requests.get(api_url_teams, headers=headers, impersonate="chrome110")

        if response.status_code == 404:
            return jsonify({'error': f'Lineup for this event isnt there yet. Code: {response.status_code}'}), 404

        if response.status_code != 200 or response_teams.status_code != 200:
            return jsonify({'error': f'Blocked or other error. Code: {response.status_code}'}), 403

        json_data = response_teams.json()
        home_team = json_data.get('event', {}).get('homeTeam', {}).get('name', '')
        away_team = json_data.get('event', {}).get('awayTeam', {}).get('name', '')
        date = json_data.get('event', {}).get('startTimestamp', '')

        json_data = response.json()

        home_players = [
            {
                'name': p['player']['name'],
                'position': p.get('position', '')
            }
            for p in json_data.get('home', {}).get('players', [])
        ]

        away_players = [
            {
                'name': p['player']['name'],
                'position': p.get('position', '')
            }
            for p in json_data.get('away', {}).get('players', [])
        ]

        if not home_players and not away_players:
            return jsonify({'error': 'Rosters arent there yet.'}), 404

        return jsonify({
            'home_team': home_team,
            'away_team': away_team,
            'date': date,
            'home_players': home_players,
            'away_players': away_players
        })

    except Exception as e:
        return jsonify({'error': f'Error while processing data : {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True)