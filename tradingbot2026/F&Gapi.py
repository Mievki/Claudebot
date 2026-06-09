import requests
import csv
from datetime import datetime


def fetch_fng_data():
    # URL met limit=0 haalt alle beschikbare historische data op
    url = "https://api.alternative.me/fng/?limit=0&format=json"

    print("Data ophalen van API...")
    response = requests.get(url)

    if response.status_code != 200:
        print("Fout bij het ophalen van data.")
        return

    data = response.json()['data']

    # Doeldatum: 1 januari 2020
    start_date = datetime(2018, 1, 1)

    filtered_data = []

    for entry in data:
        # De API geeft een UNIX timestamp terug, deze zetten we om naar een datum object
        entry_date = datetime.fromtimestamp(int(entry['timestamp']))

        # Alleen data toevoegen die op of na 1 maart 2020 is
        if entry_date >= start_date:
            filtered_data.append({
                'date': entry_date.strftime('%Y-%m-%d'),
                'fng_value': entry['value'],
                'fng_classification': entry['value_classification']
            })

    # Omdat de API de nieuwste data bovenaan zet, draaien we de lijst om (oud naar nieuw)
    filtered_data.reverse()

    # Opslaan als CSV
    filename = r"C:\Users\kiang\Documents\Pycharm\TradingBOT\F&G\fear_and_greed_index_2020_2026.csv"
    keys = filtered_data[0].keys()

    with open(filename, 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(filtered_data)

    print(f"Klaar! Er zijn {len(filtered_data)} dagen opgeslagen in {filename}")


if __name__ == "__main__":
    fetch_fng_data()