import time
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from chromedriver_py import binary_path  # Ensure chromedriver_py is installed
from sqlalchemy import create_engine, Table, MetaData, insert
from urllib.parse import urlparse


EXPECTED_PAGE_LOADING_TIME_SEC = 3

chrome_options = ChromeOptions()
chrome_options.add_argument("--headless")
chrome_service = ChromeService(executable_path=binary_path)
driver = webdriver.Chrome(service=chrome_service, options=chrome_options)

sport = "basketball"
driver.get(f"https://www.flashscore.com/{sport}/")

time.sleep(EXPECTED_PAGE_LOADING_TIME_SEC)

while True:
    try:
        show_more_button = driver.find_element(By.CLASS_NAME, "lmc__itemMore")
        driver.execute_script("arguments[0].click()", show_more_button)
        print("Clicked the 'Show more' button successfully.")
        time.sleep(EXPECTED_PAGE_LOADING_TIME_SEC)
    except:
        break

# Expand all blocks
country_elems = driver.find_elements(By.CLASS_NAME, "lmc__elementName")
for country in country_elems:
    driver.execute_script("arguments[0].click()", country)

division_elems = driver.find_elements(By.CLASS_NAME, "lmc__templateHref")
links = []
for div in division_elems:
    links.append(div.get_attribute("href"))
driver.quit()

# Database connection string
DATABASE_URL = "postgresql+psycopg2://postgres:admin@localhost:5432/sport_vision_x"

# Connect to the database
engine = create_engine(DATABASE_URL)
metadata = MetaData()

# Reflect the championship_links table
championship_links_table = Table("championship_links", metadata, autoload_with=engine)

# Function to parse sport, country, and league from URLs
def parse_links(links):
    parsed_data = []
    for url in links:
        try:
            parsed = urlparse(url)
            parts = parsed.path.strip("/").split("/")
            if len(parts) >= 3:
                sport, country, league = parts[0], parts[1], parts[2]
                parsed_data.append({"url": url, "sport": sport, "country": country, "league": league})
            else:
                print(f"Skipping malformed URL: {url}")
        except Exception as e:
            print(f"Error parsing URL {url}: {e}")
    return parsed_data

# Function to insert links into the database
def insert_links(links):
    parsed_data = parse_links(links)
    if not parsed_data:
        print("No valid links to insert.")
        return
    try:
        with engine.begin() as connection:  # Automatically manages transaction commit/rollback
            connection.execute(insert(championship_links_table), parsed_data)
            print(f"Inserted {len(parsed_data)} links successfully!")
    except Exception as e:
        print(f"Error inserting links: {e}")

insert_links(links)