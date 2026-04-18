# SportVisionX
Sport Data Crawler & Championship Insights

## Usage

### React + FastAPI dashboard

Run the API server (it also serves the React UI):

```bash
uv run uvicorn app.api:app --reload --host 127.0.0.1 --port 8000
```

Open:

`http://127.0.0.1:8000`

Available endpoints:

- `GET /api/summary`
- `GET /api/sports`
- `GET /api/sports/{sport_id}/leagues`
- `GET /api/sports/by-name/{sport_name}/leagues`
- `GET /api/leagues/{league_id}/seasons?limit=200&offset=0`
- `GET /api/leagues/{league_id}/matches.csv` (latest season for that league)
- `GET /api/leagues/{league_id}/matches.csv?season_id=<season_id>` (specific season)
- `GET /api/leagues/{league_id}/matches-detailed.csv` (latest season detailed data)
- `GET /api/leagues/{league_id}/matches-detailed.csv?season_id=<season_id>&workers=8&max_matches=30`

Detailed CSV fields include:
`date/time, teams, intermediate scores, final score, goals, yellow/red cards (+ on_pitch), referee, stadium/city, attendance/capacity, Fortuna/Superbet 1X2 when available`.

Run one-off detailed export script (Serie A 2023/2024 default):

```bash
uv run python -m scripts.retrieve_match_details --workers 8
```

### To run the data crawler, use the following command:

```bash
python -m scripts.crawl_data --leagues leagues_data\basketball\leagues.txt --seasons leagues_data\basketball\seasons.txt --out_dir .results
```

You can create custom input files for the leagues and seasons by using the example files provided in the leagues_data/basketball folder as templates.
Once you have customized these files according to your needs, pass their paths as arguments to the script.

Important: When you run the script, you will be prompted to select a sport from a list. 
Use the arrow keys to navigate and choose the appropriate sport. 
This selection is crucial because the primary basketball league in Spain is called ACB, while the primary football league in Spain is called LaLiga.
Choosing the wrong sport may lead to incorrect data or no data at all being collected.


### To run the data analyser, use the command from bellow:

```bash
python -m scripts.analyse_data --sport_dir .results\basketball --outfile .results\stats.txt 
```
At this moment, the script performs the following tasks:

- Scans all files found within the .results\basketball directory (e.g., 2022-2023\spain-acb.csv, 2021-2022\france-lnb.csv).
- Calculates the number of victories, defeats, and draws that the top 3 teams have against the bottom 3 teams based on the standings at a specific point in time:
  - Given a predefined stabilization round (e.g., round 8), the script computes a live leaderboard before each round.
  - For the 9th round, the analyzer:
    - Computes the standings with matches played up to and including round 9.
    - Identifies the top 3 teams.
    - Identifies the bottom 3 teams.
    - Checks if any top team has played against a bottom team and records the match outcome.
  - Repeats the above process for each round until the season is completed.
  - Merges the results into a dictionary for further analysis.
- Displays the results by season and championship.
- At the end, an overall summary of statistics is generated as a comprehensive overview.


## Terminology

***Stabilization round*** = A round in which the leaderboard stabilizes, meaning that the top-performing teams consistently occupy the upper positions,
while the under-performing teams settle at the bottom. Typically, after the stabilization round, it becomes clearer which teams are likely contenders
for the championship and which teams will be fighting to avoid relegation.

***first k teams*** = given a live-standing, the first k teams that have the highest win_rate

***last k teams*** = given a live-standing, the first k teams that have the lowest win_rate

### Synonyms:

***first k teams*** = ***top k teams*** = ***best k teams***

***last k teams*** = ***bottom k teams*** = ***worst k teams***
