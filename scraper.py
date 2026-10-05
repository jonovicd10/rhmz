import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from supabase import create_client, Client

# 1. Supabase Kredencijali (Preuzimaju se iz Environment Variable-a)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def parse_number(val):
    if not val:
        return None
    val = val.replace(',', '.')
    match = re.search(r'[-+]?\d*\.?\d+', val)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None

def scrape_rhmz():
    url = "https://www.hidmet.gov.rs/ciril/osmotreni/index.php"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    response = requests.get(url, headers=headers)
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, 'html.parser')
    table = soup.find('table')

    if not table:
        print("Tabela nije pronađena na stranici.")
        return []

    data = []
    rows = table.find_all('tr')
    vreme_sada = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 4:
            continue

        grad = cols[0].text.strip()
        if not grad or grad.lower() in ['stanica', 'станција', 'град', 'mesto']:
            continue

        opis = ""
        temp = None
        pritisak = None
        vlaznost = None
        pravac_vetra = None
        brzina_vetra = None

        # 1. Potraga za slikom/opisom u svim ćelijama reda
        for col in cols[1:]:
            img = col.find('img')
            if img:
                opis = img.get('title') or img.get('alt') or ""
                if not opis and img.get('src'):
                    src_filename = os.path.basename(img['src'])
                    opis = os.path.splitext(src_filename)[0].replace('_', ' ').strip()
                break

        # 2. Parsiranje svih preostalih ćelija po sadržaju
        for col in cols[1:]:
            txt = col.text.strip()
            num = parse_number(txt)

            # Ako ćelija sadrži pravac vetra (npr. "NW 2", "W 1", "SE", "mirno")
            if any(p in txt for p in ['N', 'S', 'E', 'W', 'NW', 'NE', 'SW', 'SE', 'mirno', 'мирно']):
                parts = txt.split()
                if len(parts) >= 2:
                    pravac_vetra = parts[0]
                    brzina_vetra = parse_number(parts[1])
                elif len(parts) == 1:
                    if parts[0].isdigit():
                        brzina_vetra = parse_number(parts[0])
                    else:
                        pravac_vetra = parts[0]
                continue

            if num is None:
                # Ako je ostao tekst koji nije broj, a nemamo opis
                if txt and not txt.isdigit() and not opis and len(txt) > 3:
                    opis = txt
                continue

            # Klasifikacija po opsegu vrednosti
            if num > 800 and num < 1100:
                pritisak = num
            elif temp is None and -40 <= num <= 50:
                temp = num
            elif '%' in txt or (vlaznost is None and 0 <= num <= 100 and '.' not in txt):
                vlaznost = int(num)

        data.append({
            "grad": grad,
            "temperatura": temp,
            "pritisak": pritisak,
            "vlaznost": vlaznost,
            "pravac_vetra": pravac_vetra,
            "brzina_vetra": brzina_vetra,
            "opis_vremena": opis if opis else "Bez opisa",
            "vreme_osmotreno": vreme_sada
        })

    return data

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Greška: Nisu podešene SUPABASE_URL i SUPABASE_KEY promenljive!")
        return

    print("Prikupljanje podataka sa RHMZ...")
    records = scrape_rhmz()

    if records:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        # Upisivanje u bazu (upsert sprečava greške ako podatak već postoji)
        response = supabase.table("merenja").upsert(records, on_conflict="grad,vreme_osmotreno").execute()
        print(f"Uspešno upisano {len(records)} gradova u bazu.")
    else:
        print("Nema podataka za upis.")


if __name__ == "__main__":
    main()