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

        # 1. Tražimo opis (sliku)
        opis = ""
        for col in cols:
            img = col.find('img')
            if img:
                opis = img.get('title') or img.get('alt') or ""
                if not opis and img.get('src'):
                    src_filename = os.path.basename(img['src'])
                    opis = os.path.splitext(src_filename)[0].replace('_', ' ').strip()
                break

        # 2. Uzimamo sve ćelije sa tekstom (osim prve koja je grad i ćelije sa slikom)
        text_cols = []
        for col in cols[1:]:
            if col.find('img'):
                continue
            text_cols.append(col.text.strip())

        # Na RHMZ sajtu struktura tekstualnih kolona kada se ukloni slika je uvek:
        # [0]: Temperatura (npr. "26")
        # [1]: Pritisak (npr. "1005.1") -- *ponekad nedostaje*
        # [-2]: Vetar (npr. "W 1" ili "NW 2") -- *uvek predposlednji*
        # [-1]: Vlažnost (npr. "21" ili "21%") -- *uvek poslednji*

        temp = None
        pritisak = None
        pravac_vetra = None
        brzina_vetra = None
        vlaznost = None

        if len(text_cols) >= 1:
            temp = parse_number(text_cols[0])

        # Poslednja kolona je UVEK vlažnost
        if len(text_cols) >= 2:
            vlaznost_num = parse_number(text_cols[-1])
            if vlaznost_num is not None and 0 <= vlaznost_num <= 100:
                vlaznost = int(vlaznost_num)

        # Predposlednja kolona je UVEK vetar
        if len(text_cols) >= 3:
            vetar_raw = text_cols[-2]
            if vetar_raw:
                parts = vetar_raw.split()
                if len(parts) >= 2:
                    pravac_vetra = parts[0]
                    brzina_vetra = parse_number(parts[1])
                elif len(parts) == 1:
                    if parts[0].isdigit():
                        brzina_vetra = parse_number(parts[0])
                    else:
                        pravac_vetra = parts[0]
                        brzina_vetra = 0.0

        # Pritisak je kolona između temperature i vetra (ako postoji)
        if len(text_cols) >= 4:
            press_num = parse_number(text_cols[1])
            if press_num and press_num > 800:
                pritisak = press_num

        data.append({
            "grad": grad,
            "temperatura": temp,
            "pritisak": pritisak,
            "vlaznost": vlaznost,
            "pravac_vetra": pravac_vetra,
            "brzina_vetra": brzina_vetra,
            "opis_vremena": opis if opis else "Pretežno vedro",
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