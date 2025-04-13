import os
import ftplib
import pandas as pd
import requests
from google.cloud import storage
import random
import re

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

        # Extract valid image URLs if the 'image' column exists
        if 'image' in df.columns:
            df['image'] = df['image'].str.extract(r'(https?://.*\.(jpg|png))')[0].fillna('')
            df = df[df['image'] != '']
        else:
            df['image'] = ''

        # Convert and mark up price values
        df['price'] = pd.to_numeric(df.get('price', 0), errors='coerce').fillna(0)
        df['price'] = df['price'].apply(self.markup)

        # Choose the proper template based on product type
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
        # For gemstones, some column names differ (e.g., 'gemType', 'Color', 'Clarity', etc.)
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

            # Step 2: Process each file
            processed_dfs = {}
            for product_type, file_info in self.files_to_load.items():
                df = self.process_file(file_info["file_path"], product_type)
                processed_dfs[product_type] = df

            # Determine the maximum allowed rows per category 
            # so that the total across categories is under 100,000 products
            max_total = 100000
            num_categories = len(processed_dfs)  # ideally 3 categories: natural, lab_grown, gemstone
            max_per_category = max_total // num_categories  # e.g., 33333

            # Find the minimum available count among the three categories;
            # even if max_per_category is higher, we can only take as many as available.
            min_available = min(len(df) for df in processed_dfs.values())
            # The number to take from each category is the minimum of the maximum allowed and the smallest count
            n = min(max_per_category, min_available)

            # For each category, randomly sample n records (or take all if not exceeding n)
            dataframes = []
            for product_type, df in processed_dfs.items():
                if len(df) > n:
                    df_sample = df.sample(n=n, random_state=42)
                else:
                    df_sample = df
                dataframes.append(df_sample)

            # Combine the equally sampled dataframes
            combined_df = pd.concat(dataframes, ignore_index=True)

            # Reorder columns to match the Reddit catalog structure:
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
            combined_df = combined_df[reddit_columns]

            # Save the combined Reddit catalog to the output folder
            combined_file = os.path.join(self.output_folder, "combined_reddit_catalog.csv")
            combined_df.to_csv(combined_file, index=False)
            print(f"Combined Reddit catalog saved to {combined_file}")

            # Upload generated files to Google Cloud Storage
            self.upload_to_gcs()
            print("Processing completed successfully")
        except Exception as e:
            print(f"Error in main process: {e}")

if __name__ == "__main__":
    processor = RedditCatalogProcessor()
    processor.run()
