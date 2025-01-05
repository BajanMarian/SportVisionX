from sqlalchemy import create_engine, MetaData, Table, Column, Integer, String, TIMESTAMP, func, inspect
from sqlalchemy.exc import SQLAlchemyError

# Replace these values with your actual database credentials
DATABASE_URL = "postgresql+psycopg2://postgres:admin@localhost:5432/sport_vision_x"

# Connect to the database
engine = create_engine(DATABASE_URL)

# Metadata object to manage the database schema
metadata = MetaData()

# Define the championship_links table schema
championship_links_table = Table(
    "championship_links", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("url", String, unique=True, nullable=False),  # Link URL
    Column("sport", String, nullable=False),             # Sport (e.g., basketball)
    Column("country", String, nullable=False),           # Country (e.g., turkey)
    Column("league", String, nullable=False),            # League (e.g., super-cup-women)
    Column("created_at", TIMESTAMP, server_default=func.now())  # Timestamp
)


# Function to create the table if it doesn't exist
def create_table_if_not_exists(engine, table):
    try:
        # Use the inspector to check if the table exists
        inspector = inspect(engine)
        if table.name not in inspector.get_table_names():
            # Create the table if it doesn't exist
            metadata.create_all(engine, tables=[table])
            print(f"Table '{table.name}' created successfully!")
        else:
            print(f"Table '{table.name}' already exists.")
    except SQLAlchemyError as e:
        print(f"An error occurred while checking or creating the table: {e}")


# Call the function to check and create the table
create_table_if_not_exists(engine, championship_links_table)
