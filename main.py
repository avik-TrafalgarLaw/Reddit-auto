import os
import ftplib
import pandas as pd
import requests
from google.cloud import storage
import random
import re

# ----------------------------
# QUALITY FILTERING PARAMETERS
# ----------------------------
BEST_SHAPES = ['Round', 'Princess', 'Cushion', 'Oval', 'Emerald', 'Asscher', 'Radiant', 'Pear', 'Marquise', 'Heart']
BEST_COLORS = ['D', 'E', 'F', 'G']
MIN_CARAT = 0.5
BEST_CLARITIES = ['IF', 'VVS1', 'VVS2', 'VS1', 'VS2']
# BEST_PRICING_THRESHOLD defines the maximum allowed price (after markup) per carat.
BEST_PRICING_THRESHOLD = 10000  # USD per carat

# ----------------------------
# FTP DOWNLOAD CONFIGURATION
# ----------------------------
FTP_SERVER = "ftp.nivoda.net"
FTP_PORT = 21
FTP_USERNAME = "leeladiamondscorporate@gmail.com"
FTP_PASSWORD = "r[Eu;9NB"

# Set download directory from env (defaults to /tmp/raw)
ftp_download_dir = os.environ.get("FTP_DOWNLOAD_DIR", "/tmp/raw")
os.makedirs(ftp_download_dir, exist_ok=True)

ftp_files = {
    "natural": {
         "remote_filename": "Leela Diamond_natural.csv",
         "local_path": os.path.join(ftp_download_dir, "Natural.csv")
    },
    "lab_grown": {
         "remote_filename": "Leela Diamond_labgrown.csv",
         "local_path": os.path.join(ftp_download_dir, "Labgrown.csv")
    },
    "gemstone": {
         "remote_filename": "Leela Diamond_gemstones.csv",
         "local_path": os.path.join(ftp_download_dir, "gemstones.csv")
    }
}

def download_file_from_ftp(remote_filename, local_path):
    """Download a file from the FTP server to a local path."""
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(FTP_SERVER, FTP_PORT)
            ftp.login(FTP_USERNAME, FTP_PASSWORD)
            with open(local_path, 'wb') as f:
                ftp.retrbinary(f"RETR {remote_filename}", f.write)
            print(f"Downloaded {remote_filename} to {local_path}")
    except Exception as e:
        print(f"Error downloading {remote_filename}: {e}")

def download_all_files():
    """Download all raw files from the FTP server."""
    for product_type, file_info in ftp_files.items():
        download_file_from_ftp(file_info["remote_filename"], file_info["local_path"])

# ----------------------------
# FUNCTION TO SAVE CSV WITH SIZE LIMIT
# ----------------------------
def save_dataframe_with_limit(df, output_file, size_limit=200 * 1024 * 1024):
    """
    Save DataFrame to CSV and split into parts if file exceeds the given size limit.
    The size_limit is in bytes (default 200 MB).
    """
    df.to_csv(output_file, index=False)
    file_size = os.path.getsize(output_file)
    if file_size <= size_limit:
        print(f"File {output_file} size {file_size} bytes is within the limit.")
    else:
        print(f"File {output_file} size {file_size} bytes exceeds the limit. Splitting...")
        num_parts = file_size // size_limit + 1
        total_rows = len(df)
        chunk_size = total_rows // num_parts + 1
        for i in range(num_parts):
            part_file = output_file.replace(".csv", f"_part{i+1}.csv")
            df_chunk = df.iloc[i * chunk_size:(i + 1) * chunk_size]
            df_chunk.to_csv(part_file, index=False)
            print(f"Saved chunk {i+1} to {part_file}")
        os.remove(output_file)
        print(f"Removed original file {output_file} as it was split into {num_parts} parts.")

# ----------------------------
# REDDIT CATALOG PROCESSING SCRIPT
# ----------------------------
class RedditCatalogProcessor:
    def __init__(self):
        # Use the downloaded files from FTP.
        self.files_to_load = {
            "natural": {
                "file_path": os.path.join(os.environ.get("FTP_DOWNLOAD_DIR", "/tmp/raw"), "Natural.csv")
            },
            "lab_grown": {
                "file_path": os.path.join(os.environ.get("FTP_DOWNLOAD_DIR", "/tmp/raw"), "Labgrown.csv")
            },
            "gemstone": {
                "file_path": os.path.join(os.environ.get("FTP_DOWNLOAD_DIR", "/tmp/raw"), "gemstones.csv")
            }
        }
        # Google Cloud Storage configuration via environment variables
        self.gcs_config = {
            "bucket_name": os.environ.get("BUCKET_NAME", "sitemaps.leeladiamond.com"),
            "bucket_folder": os.environ.get("BUCKET_FOLDER", "redditcatalog")
        }
        # Output folder for generated Reddit catalog files; default to /tmp/reddit_output
        self.output_folder = os.environ.get("OUTPUT_FOLDER", "/tmp/reddit_output")
        os.makedirs(self.output_folder, exist_ok=True)

    def markup(self, x):
        """
        Computes a marked-up price based on the raw value.
        The calculation applies a base multiplier and an additional fee based on price tiers.
        """
        base = x * 1.05 * 1.13
        additional = (
            210 if x <= 500 else
            375 if x <= 1000 else
            500 if x <= 1500 else
            700 if x <= 2000 else
            900 if x <= 2500 else
            1100 if x <= 3000 else
            1200 if x <= 5000 else
            1500 if x <= 100000 else
            0
        ) * 1.15
        return round(base + additional, 2)

    def process_file(self, file_path, product_type):
        df = pd.read_csv(file_path, dtype=str)
        df = df.fillna('')

        # Convert the "carats" field to numeric for filtering
        df['carats_numeric'] = pd.to_numeric(df.get('carats', 0), errors='coerce')

        # ----------------------------
        # QUALITY FILTERING
        # ----------------------------
        if product_type in ['natural', 'lab_grown']:
            # Use columns 'shape', 'col', 'clar' for diamonds.
            df = df[df['shape'].isin(BEST_SHAPES)]
            df = df[df['col'].isin(BEST_COLORS)]
            df = df[df['carats_numeric'] >= MIN_CARAT]
            df = df[df['clar'].isin(BEST_CLARITIES)]
        elif product_type == 'gemstone':
            # Gemstones may use different column names. Here we assume color is in 'Color'
            df = df[df['shape'].isin(BEST_SHAPES)]
            df = df[df['Color'].isin(BEST_COLORS)]
            df = df[df['carats_numeric'] >= MIN_CARAT]
            if 'Clarity' in df.columns:
                df = df[df['Clarity'].isin(BEST_CLARITIES)]
        else:
            raise ValueError("Unsupported product type")

        # ----------------------------
        # BEST PRICING FILTER (for diamonds only)
        # ----------------------------
        # Only for natural and lab grown – compute price per carat (after markup)
        if product_type in ['natural', 'lab_grown']:
            # First, convert the price column from CSV to numeric then apply our markup
            df['price'] = pd.to_numeric(df.get('price', 0), errors='coerce').fillna(0)
            df['price'] = df['price'].apply(self.markup)
            # Compute price per carat
            df['price_per_carat'] = df['price'] / df['carats_numeric']
            filtered_df = df[df['price_per_carat'] <= BEST_PRICING_THRESHOLD]
            if filtered_df.empty:
                print(f"No records met the pricing criteria for {product_type} diamonds; using quality filtered data.")
            else:
                df = filtered_df
            # Remove the temporary pricing column
            df.drop(columns=['price_per_carat'], inplace=True)
        else:
            # For gemstones, simply apply markup to price.
            df['price'] = pd.to_numeric(df.get('price', 0), errors='coerce').fillna(0)
            df['price'] = df['price'].apply(self.markup)

        # ----------------------------
        # CLEAN IMAGE URL IF PRESENT
        # ----------------------------
        if 'image' in df.columns:
            df['image'] = df['image'].str.extract(r'(https?://.*\.(jpg|png))')[0].fillna('')
            df = df[df['image'] != '']
        else:
            df['image'] = ''

        # Remove the helper column for carats after filtering
        df.drop(columns=['carats_numeric'], inplace=True)

        # ----------------------------
        # Choose the proper template based on product type
        # ----------------------------
        if product_type == "natural":
            template = self.reddit_template_natural
        elif product_type == "lab_grown":
            template = self.reddit_template_lab_grown
        elif product_type == "gemstone":
            template = self.reddit_template_gemstone
        else:
            raise ValueError("Unsupported product type")

        # Apply the template to each row to build our Reddit catalog fields
        processed_df = df.apply(lambda row: pd.Series(template(row)), axis=1)
        return processed_df

    def reddit_template_natural(self, row):
        price = float(row['price'])
        sale_price = round(price * 0.95, 2)
        cost = round(price * 0.9, 2)
        return {
            "id": f"{row.get('ReportNo','')}RD",
            "title": f"{row.get('shape','')} Natural Diamond - {row.get('carats','')} Carats, {row.get('col','')} Color, {row.get('clar','')} Clarity",
            "description": f"Discover the brilliance of a natural diamond. {row.get('carats','')} carats of exquisite {row.get('shape','')} beauty with {row.get('col','')} color and {row.get('clar','')} clarity. Certified by {row.get('lab','')}.",
            "link": f"https://leeladiamond.com/pages/natural-diamond-catalog?id={row.get('ReportNo','')}",
            "image_link": row.get('image',''),
            "price": f"{row.get('price','')} USD",
            "item_group_id": f"NAT-{row.get('ReportNo','')}",
            "gtin": "",
            "mpn": f"MPN-{row.get('ReportNo','')}",
            "google_product_category": "Jewelry > Fine Jewelry > Diamonds",
            "product_type": "Natural Diamond",
            "brand": "Leela Diamond",
            "adult": "no",
            "is_bundle": "no",
            "sale_price": f"{sale_price} USD",
            "sale_price_effective_date": "2024-03-24T13:00-0800/2024-03-28T15:30-0800",
            "cost_of_goods_sold": f"{cost} USD",
            "mobile_link": f"http://m.leeladiamond.com/pages/natural-diamond-catalog?id={row.get('ReportNo','')}",
            "platform_specific_link": '{"ios": "https://leeladiamond.com/ios","android": "https://leeladiamond.com/android"}',
            "additional_image_links": "[]",
            "lifestyle_image_link": "",
            "availability": "in_stock",
            "expiration_date": "2025-12-31T23:59:59Z",
            "condition": "new",
            "age_group": "adult",
            "gender": "unisex",
            "color": row.get('col',''),
            "size": row.get('carats',''),
            "size_type": "N/A",
            "material": "diamond",
            "pattern": "",
            "product_detail": f"Shape: {row.get('shape','')}, Carats: {row.get('carats','')}, Cut: {row.get('cut','')}, Polish: {row.get('pol','')}",
            "product_highlight": "High quality natural diamond with excellent clarity and brilliance.",
            "average_review_rating": round(random.uniform(4, 5), 1),
            "number_of_ratings": random.randint(5, 50),
            "custom_label_0": "natural",
            "custom_label_1": "",
            "custom_label_2": "",
            "custom_label_3": "",
            "custom_label_4": "",
            "custom_number_0": 0,
            "custom_number_1": 0,
            "custom_number_2": 0,
            "custom_number_3": 0,
            "custom_number_4": 0
        }

    def reddit_template_lab_grown(self, row):
        price = float(row['price'])
        sale_price = round(price * 0.95, 2)
        cost = round(price * 0.9, 2)
        return {
            "id": f"{row.get('ReportNo','')}RD",
            "title": f"{row.get('shape','')} Lab Grown Diamond - {row.get('carats','')} Carats, {row.get('col','')} Color, {row.get('clar','')} Clarity",
            "description": f"Experience the innovation of lab grown diamonds. {row.get('carats','')} carats of stunning {row.get('shape','')} design with {row.get('col','')} color and {row.get('clar','')} clarity. Certified by {row.get('lab','')}.",
            "link": f"https://leeladiamond.com/pages/lab-grown-diamond-catalog?id={row.get('ReportNo','')}",
            "image_link": row.get('image',''),
            "price": f"{row.get('price','')} USD",
            "item_group_id": f"LAB-{row.get('ReportNo','')}",
            "gtin": "",
            "mpn": f"MPN-{row.get('ReportNo','')}",
            "google_product_category": "Jewelry > Fine Jewelry > Diamonds",
            "product_type": "Lab Grown Diamond",
            "brand": "Leela Diamond",
            "adult": "no",
            "is_bundle": "no",
            "sale_price": f"{sale_price} USD",
            "sale_price_effective_date": "2024-03-24T13:00-0800/2024-03-28T15:30-0800",
            "cost_of_goods_sold": f"{cost} USD",
            "mobile_link": f"http://m.leeladiamond.com/pages/lab-grown-diamond-catalog?id={row.get('ReportNo','')}",
            "platform_specific_link": '{"ios": "https://leeladiamond.com/ios","android": "https://leeladiamond.com/android"}',
            "additional_image_links": "[]",
            "lifestyle_image_link": "",
            "availability": "in_stock",
            "expiration_date": "2025-12-31T23:59:59Z",
            "condition": "new",
            "age_group": "adult",
            "gender": "unisex",
            "color": row.get('col',''),
            "size": row.get('carats',''),
            "size_type": "N/A",
            "material": "diamond",
            "pattern": "",
            "product_detail": f"Shape: {row.get('shape','')}, Carats: {row.get('carats','')}, Cut: {row.get('cut','')}, Polish: {row.get('pol','')}",
            "product_highlight": "High quality lab grown diamond with impeccable craftsmanship.",
            "average_review_rating": round(random.uniform(4, 5), 1),
            "number_of_ratings": random.randint(5, 50),
            "custom_label_0": "lab_grown",
            "custom_label_1": "",
            "custom_label_2": "",
            "custom_label_3": "",
            "custom_label_4": "",
            "custom_number_0": 0,
            "custom_number_1": 0,
            "custom_number_2": 0,
            "custom_number_3": 0,
            "custom_number_4": 0
        }

    def reddit_template_gemstone(self, row):
        price = float(row['price']) if row['price'] else 0.0
        sale_price = round(price * 0.95, 2) if price else 0.0
        cost = round(price * 0.9, 2) if price else 0.0
        return {
            "id": f"{row.get('ReportNo','')}RD",
            "title": f"{row.get('shape','')} {row.get('gemType','')} Gemstone - {row.get('carats','')} Carats, {row.get('Color','')} Color, {row.get('Clarity','')} Clarity",
            "description": f"Explore our exquisite gemstone: {row.get('shape','')} {row.get('gemType','')} with {row.get('carats','')} carats, {row.get('Color','')} color, and {row.get('Clarity','')} clarity. Lab: {row.get('Lab','')}, Treatment: {row.get('Treatment','')}, from {row.get('Mine of Origin','')}.",
            "link": f"https://leeladiamond.com/pages/gemstone-catalog?id={row.get('ReportNo','')}",
            "image_link": row.get('image',''),
            "price": f"{row.get('price','')} USD",
            "item_group_id": f"GEM-{row.get('ReportNo','')}",
            "gtin": "",
            "mpn": f"MPN-{row.get('ReportNo','')}",
            "google_product_category": "Jewelry > Gemstones",
            "product_type": "Gemstone",
            "brand": "Leela Diamond",
            "adult": "no",
            "is_bundle": "no",
            "sale_price": f"{sale_price} USD",
            "sale_price_effective_date": "2024-03-24T13:00-0800/2024-03-28T15:30-0800",
            "cost_of_goods_sold": f"{cost} USD",
            "mobile_link": f"http://m.leeladiamond.com/pages/gemstone-catalog?id={row.get('ReportNo','')}",
            "platform_specific_link": '{"ios": "https://leeladiamond.com/ios","android": "https://leeladiamond.com/android"}',
            "additional_image_links": "[]",
            "lifestyle_image_link": "",
            "availability": "in_stock",
            "expiration_date": "2025-12-31T23:59:59Z",
            "condition": "new",
            "age_group": "adult",
            "gender": "unisex",
            "color": row.get('Color',''),
            "size": row.get('carats',''),
            "size_type": "N/A",
            "material": row.get('Lab','') if row.get('Lab','') else "gemstone",
            "pattern": row.get('Treatment',''),
            "product_detail": f"GemType: {row.get('gemType','')}, Carats: {row.get('carats','')}",
            "product_highlight": "A standout gemstone known for its rarity and vibrant color.",
            "average_review_rating": round(random.uniform(4, 5), 1),
            "number_of_ratings": random.randint(5, 50),
            "custom_label_0": "gemstone",
            "custom_label_1": "",
            "custom_label_2": "",
            "custom_label_3": "",
            "custom_label_4": "",
            "custom_number_0": 0,
            "custom_number_1": 0,
            "custom_number_2": 0,
            "custom_number_3": 0,
            "custom_number_4": 0
        }

    def upload_to_gcs(self):
        try:
            storage_client = storage.Client()
            bucket = storage_client.bucket(self.gcs_config["bucket_name"])
            for file_name in os.listdir(self.output_folder):
                file_path = os.path.join(self.output_folder, file_name)
                if os.path.isfile(file_path):
                    destination_blob_name = f"{self.gcs_config['bucket_folder']}/{file_name}"
                    blob = bucket.blob(destination_blob_name)
                    blob.upload_from_filename(file_path)
                    print(f"Uploaded {file_name} to GCS")
        except Exception as e:
            print(f"GCS upload error: {e}")

    def run(self):
        try:
            # Step 1: Download raw files from FTP
            download_all_files()

            reddit_columns = [
                "id", "title", "description", "link", "image_link", "price",
                "item_group_id", "gtin", "mpn", "google_product_category", "product_type",
                "brand", "adult", "is_bundle", "sale_price", "sale_price_effective_date",
                "cost_of_goods_sold", "mobile_link", "platform_specific_link",
                "additional_image_links", "lifestyle_image_link", "availability",
                "expiration_date", "condition", "age_group", "gender", "color", "size",
                "size_type", "material", "pattern", "product_detail", "product_highlight",
                "average_review_rating", "number_of_ratings", "custom_label_0", "custom_label_1",
                "custom_label_2", "custom_label_3", "custom_label_4", "custom_number_0",
                "custom_number_1", "custom_number_2", "custom_number_3", "custom_number_4"
            ]

            # Step 2: Process each file separately and save individual CSVs per product type
            for product_type, file_info in self.files_to_load.items():
                df = self.process_file(file_info["file_path"], product_type)
                # Use reindex to ensure the DataFrame contains the desired columns (even if empty)
                df = df.reindex(columns=reddit_columns)
                output_file = os.path.join(self.output_folder, f"{product_type}_reddit_catalog.csv")
                save_dataframe_with_limit(df, output_file)
                print(f"{product_type.capitalize()} Reddit catalog saved (and split if needed).")

            # Step 3: Upload generated files to Google Cloud Storage
            self.upload_to_gcs()
            print("Processing completed successfully")
        except Exception as e:
            print(f"Error in main process: {e}")

if __name__ == "__main__":
    processor = RedditCatalogProcessor()
    processor.run()
