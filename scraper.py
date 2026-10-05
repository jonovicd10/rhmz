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
    if not rows:
        return []

    # 1. Pronalaženje tačnih indeksa kolona iz zaglavlja tabele
    header_cols = [th.text.strip().lower() for th in rows[0].find_all(['th', 'td'])]

    # Podrazumevani indeksi ako zaglavlje ne uspeti da se mapira
    idx_grad = 0
    idx_opis = 1
    idx_temp = 2
    idx_pritisak = 3
    idx_vetar = 4
    idx_vlaznost = 5

    for i, h in enumerate(header_cols):
        if 'stanica' in h or 'град' in h or 'mesto' in h:
            idx_grad = i
        elif 'vreme' in h or 'појаве' in h or 'opis' in h:
            idx_opis = i
        elif 'temp' in h or 'т' in h:
            idx_temp = i
        elif 'prit' in h or 'притисак' in h:
            idx_pritisak = i
        elif 'vetar' in h or 'ветар' in h:
            idx_vetar = i
        elif 'vlaga' in h or 'влажност' in h:
            idx_vlaznost = i

    vreme_sada = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 2. Parsiranje redova sa dinamičkim indeksima
    for row in rows[1:]:
        cols = row.find_all(['td', 'th'])
        if len(cols) >= 6:
            grad = cols[idx_grad].text.strip() if len(cols) > idx_grad else None

            # Temperatura
            temp_text = cols[idx_temp].text.strip() if len(cols) > idx_temp else ''
            temp = parse_number(temp_text)

            # Pritisak
            press_text = cols[idx_pritisak].text.strip() if len(cols) > idx_pritisak else ''
            pritisak = parse_number(press_text)

            # Vlažnost
            hum_text = cols[idx_vlaznost].text.strip() if len(cols) > idx_vlaznost else ''
            vlaznost = parse_number(hum_text)

            # Vetar
            vetar_raw = cols[idx_vetar].text.strip() if len(cols) > idx_vetar else ''
            pravac_vetra = vetar_raw.split()[0] if vetar_raw else None
            brzina_vetra = parse_number(vetar_raw)

            # Opis vremena
            opis_td = cols[idx_opis] if len(cols) > idx_opis else None
            opis = ''
            if opis_td:
                img = opis_td.find('img')
                if img and img.get('title'):
                    opis = img.get('title').strip()
                elif img and img.get('alt'):
                    opis = img.get('alt').strip()
                elif opis_td.get('title'):
                    opis = opis_td.get('title').strip()
                else:
                    opis = opis_td.text.strip()

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