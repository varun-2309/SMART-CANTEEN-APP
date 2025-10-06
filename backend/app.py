from fastapi import FastAPI, HTTPException
from pathlib import Path
import csv

app = FastAPI(title="Smart Canteen API")

# Looks for Veg_Menu.csv in the SAME folder as this file (backend/)
CSV_FILE = Path(__file__).with_name("Veg_Menu.csv")

def load_veg():
    # Reads the CSV and converts it to a list of dicts
    items = []
    if not CSV_FILE.exists():
        return items
    with CSV_FILE.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)  # expects a header row
        for i, row in enumerate(reader, start=1):
            # Be flexible about column names (Name/name, Price/price, etc.)
            name = row.get("name") or row.get("Name") or row.get("item") or row.get("Item") or f"Item {i}"
            price_raw = row.get("price") or row.get("Price") or row.get("cost") or row.get("Cost") or "0"
            category = row.get("category") or row.get("Category") or "Veg"
            id_raw = row.get("id") or row.get("ID") or str(i)
            try:
                price = float(price_raw)
            except Exception:
                price = 0.0
            try:
                item_id = int(id_raw)
            except Exception:
                item_id = i
            items.append({"id": item_id, "name": name, "price": price, "category": category})
    return items

@app.get("/")
def read_root():
    return {"message": "Smart Canteen Backend is running"}

@app.get("/menu/veg")
def list_veg_menu():
    return load_veg()

@app.get("/menu/veg/{item_id}")
def get_veg_item(item_id: int):
    for item in load_veg():
        if item["id"] == item_id:
            return item
    raise HTTPException(status_code=404, detail="Item not found")
