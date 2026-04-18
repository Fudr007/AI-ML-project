# AI-LM-project
## Prediction of Bundesliga handball matches betting odds
This project aims to predict betting odds for German Bundesliga handball matches using Machine Learning (XGBoost). 
The project covers the entire lifecycle from custom data collection to deployment as a web application.

## How to run
1. Download this repository
2. Unzip the directory
3. Go to the App folder
4. Run the run.bat file
5. Go to the printed local address in the browser

## Analysis
* Base atributes { date, home_team, guest_team, score_home, score_guest, home_goalkeepers, guest_goalkeepers, home_field_players, guest_field_players }
* User input of which teams are playing, when is the match, who are goalkeepers, and who is playing in the field
* The output will be a prediction of betting odds

## Data collection
* A custom asynchronous crawler based on Playwright was developed to fetch data from Sofascore.com
* The filter.py script removed incomplete records
* In refactor.ipynb, JSON structures were converted into numerical attributes, moving averages for "team form" were calculated, and a dynamic ELO rating system was implemented
* Graph of the importance of different attributes for model_domaci: [output.png](output.png)

## ML model
* XGBoost (Extreme Gradient Boosting) was used
* Regression (predicting probability/implied odds)