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
    # Zamena zareza tačkom i traženje prvog brojčanog zapisa (celog ili sa decimalom)
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
        # Uzimamo samo redove koji imaju bar 6 kolona
        if len(cols) >= 6:
            grad = cols[0].text.strip()
            if not grad or grad.lower() in ['stanica', 'станција', 'град']:
                continue  # Preskačemo zaglavlja

            # 1. Opis vremena (kolona 1)
            opis_td = cols[1]
            opis = ""
            img = opis_td.find('img')
            if img:
                opis = img.get('title') or img.get('alt') or ""
            if not opis:
                opis = opis_td.get('title') or opis_td.text.strip()

            # Ako je opis ostao samo broj (npr. id ikone), postavi ga na prazno
            if opis.isdigit():
                opis = ""

            # 2. Temperatura (kolona 2)
            temp = parse_number(cols[2].text.strip())

            # 3. Pritisak (kolona 3)
            pritisak_raw = cols[3].text.strip()
            pritisak = parse_number(pritisak_raw)

            # 4. Vetar (kolona 4) - primer: "NW 2", "SE 11", "mirno"
            vetar_raw = cols[4].text.strip()
            pravac_vetra = None
            brzina_vetra = None

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

            # 5. Vlažnost (kolona 5)
            vlaznost_raw = cols[5].text.strip()
            vlaznost = parse_number(vlaznost_raw)

            data.append({
                "grad": grad,
                "temperatura": temp,
                "pritisak": pritisak,
                "vlaznost": int(vlaznost) if vlaznost is not None else None,
                "pravac_vetra": pravac_vetra,
                "brzina_vetra": brzina_vetra,
                "opis_vremena": opis,
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