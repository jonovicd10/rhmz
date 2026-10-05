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

    # 1. Pronalaženje i mapiranje zaglavlja (Header Mapping)
    header_map = {}
    header_row = table.find('tr')

    if header_row:
        headers = header_row.find_all(['th', 'td'])
        for idx, h in enumerate(headers):
            txt = h.text.strip().lower()
            if 'стан' in txt or 'grad' in txt or 'mesto' in txt:
                header_map['grad'] = idx
            elif 'темп' in txt:
                header_map['temp'] = idx
            elif 'притис' in txt or 'pritisak' in txt:
                header_map['pritisak'] = idx
            elif 'ветар' in txt or 'вет' in txt or 'vetar' in txt:
                header_map['vetar'] = idx
            elif 'влаж' in txt or 'vlaznost' in txt:
                header_map['vlaznost'] = idx
            elif 'опис' in txt or 'појав' in txt or 'vreme' in txt:
                header_map['opis'] = idx

    data = []
    rows = table.find_all('tr')[1:]  # preskačemo red sa zaglavljem
    vreme_sada = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 3:
            continue

        # Dohvatanje grada
        grad_idx = header_map.get('grad', 0)
        grad = cols[grad_idx].text.strip() if len(cols) > grad_idx else ""

        if not grad or grad.lower() in ['stanica', 'станција', 'град', 'mesto']:
            continue

        # Dohvatanje Opisa (prvo traži sliku u celom redu ili iz određene kolone)
        opis = ""
        opis_idx = header_map.get('opis')
        if opis_idx is not None and len(cols) > opis_idx:
            img = cols[opis_idx].find('img')
            if img:
                opis = img.get('title') or img.get('alt') or ""
                if not opis and img.get('src'):
                    src_filename = os.path.basename(img['src'])
                    opis = os.path.splitext(src_filename)[0].replace('_', ' ').strip()
            if not opis:
                opis = cols[opis_idx].text.strip()

        # Fallback za opis ako nije pronađen preko zaglavlja
        if not opis:
            for col in cols:
                img = col.find('img')
                if img:
                    opis = img.get('title') or img.get('alt') or ""
                    break

        # Dohvatanje ostalih vrednosti na osnovu mapiranih indeksa
        def get_col_text(key):
            idx = header_map.get(key)
            if idx is not None and len(cols) > idx:
                return cols[idx].text.strip()
            return ""

        temp_txt = get_col_text('temp')
        pritisak_txt = get_col_text('pritisak')
        vetar_txt = get_col_text('vetar')
        vlaznost_txt = get_col_text('vlaznost')

        # Fallback na stare pozicije ako zaglavlje nije uspešno mapirano
        if not header_map:
            temp_txt = cols[2].text.strip() if len(cols) > 2 else ""
            pritisak_txt = cols[3].text.strip() if len(cols) > 3 else ""
            vetar_txt = cols[4].text.strip() if len(cols) > 4 else ""
            vlaznost_txt = cols[5].text.strip() if len(cols) > 5 else ""

        # Parsiranje dobijenih tekstualnih vrednosti
        temp = parse_number(temp_txt)
        pritisak = parse_number(pritisak_txt)

        vlaznost_num = parse_number(vlaznost_txt)
        vlaznost = int(vlaznost_num) if vlaznost_num is not None else None

        pravac_vetra = None
        brzina_vetra = None
        if vetar_txt:
            parts = vetar_txt.split()
            if len(parts) >= 2:
                pravac_vetra = parts[0]
                brzina_vetra = parse_number(parts[1])
            elif len(parts) == 1:
                if parts[0].isdigit():
                    brzina_vetra = parse_number(parts[0])
                else:
                    pravac_vetra = parts[0]
                    brzina_vetra = 0.0

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