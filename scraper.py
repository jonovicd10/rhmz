import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from supabase import create_client, Client

# 1. Supabase Kredencijali (Preuzimaju se iz Environment Variable-a)
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def parse_number(text):
    """Pomoćna funkcija za čišćenje i pretvaranje teksta u broj."""
    if not text or text == '-' or text == '':
        return None
    # Izvlači prvi broj ili decimalni broj iz teksta
    match = re.search(r'[-+]?\d*\.?\d+', text.replace(',', '.'))
    return float(match.group()) if match else None


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

    for row in rows[1:]:  # Preskačemo zaglavlje
        cols = row.find_all(['td', 'th'])
        if len(cols) >= 6:
            grad = cols[0].text.strip()
            temp = parse_number(cols[1].text.strip())
            pritisak = parse_number(cols[2].text.strip())
            vlaznost = parse_number(cols[3].text.strip())
            vetar_raw = cols[4].text.strip()  # npr. "SE 2" ili "C"

            # --- IZVLAČENJE TEKSTUALNOG OPISA VREMENA ---
            opis_td = cols[5]
            img = opis_td.find('img')

            # Prvo tražimo title ili alt na slici (ikoni), pa u samoj ćeliji
            if img and img.get('title'):
                opis = img.get('title').strip()
            elif img and img.get('alt'):
                opis = img.get('alt').strip()
            elif opis_td.get('title'):
                opis = opis_td.get('title').strip()
            else:
                opis = opis_td.text.strip()

            # Razdvajanje pravca i brzine vetra
            pravac_vetra = vetar_raw.split()[0] if vetar_raw else None
            brzina_vetra = parse_number(vetar_raw)

            # Podaci se osvežavaju na svakih 20 min (orijentaciono vreme)
            vreme_sada = datetime.now().isoformat()

            if grad:
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