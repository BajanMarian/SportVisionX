# SportVisionX
Sport Data Crawler & Championship Insights

## Usage
To run the data crawler, use the following command:

```bash
python -m scripts.crawl_data --leagues leagues_data\basketball\leagues.txt --seasons leagues_data\basketball\seasons.txt --out_dir .results
```

You can create custom input files for the leagues and seasons by using the example files provided in the leagues_data/basketball folder as templates.
Once you have customized these files according to your needs, pass their paths as arguments to the script.

Important: When you run the script, you will be prompted to select a sport from a list. 
Use the arrow keys to navigate and choose the appropriate sport. 
This selection is crucial because the primary basketball league in Spain is called ACB, while the primary football league in Spain is called LaLiga.
Choosing the wrong sport may lead to incorrect data or no data at all being collected.