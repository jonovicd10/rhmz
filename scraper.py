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
        if not cols:
            continue

        # Prva kolona je uvek naziv grada
        grad = cols[0].text.strip()
        if not grad or grad.lower() in ['stanica', 'станција', 'град', 'станница']:
            continue

        # Prikupljamo tekstualni sadržaj ostalih ćelija u redu
        cell_texts = [c.text.strip() for c in cols[1:]]

        opis = ""
        temp = None
        pritisak = None
        vlaznost = None
        pravac_vetra = None
        brzina_vetra = None

        # 1. Opis (tražimo img ili title u drugoj ćeliji)
        if len(cols) > 1:
            img = cols[1].find('img')
            if img:
                opis = img.get('title') or img.get('alt') or ""
            if not opis:
                txt = cols[1].text.strip()
                if not txt.isdigit():  # Ako nije samo ID ikone
                    opis = txt

        # 2. Inteligentno mapiranje numeričkih i tekstualnih polja po vrednostima
        numeric_values = []
        for text in cell_texts:
            num = parse_number(text)
            numeric_values.append((text, num))

        # Analiza preostalih kolona
        for text, num in numeric_values:
            if num is None:
                # Moguće da je pravac vetra (npr. "SE", "NW", "mirno")
                if text and len(text) <= 5 and not opis:
                    pravac_vetra = text
                continue

            # Pritisak: vrednosti su obično preko 800 hPa
            if num > 800 and num < 1100:
                pritisak = num
            # Vlažnost: procenat 0-100% (obično celobrojna vrednost bez decimale)
            elif '%' in text or (num >= 0 and num <= 100 and '.' not in text and vlaznost is None and temp is not None):
                vlaznost = int(num)
            # Temperatura: razumni opseg za našu klimu (-40 do +50 °C)
            elif temp is None and -40 <= num <= 50:
                temp = num
            # Vetar (brzina)
            elif brzina_vetra is None and 0 <= num <= 60:
                brzina_vetra = num
                if not pravac_vetra and ' ' in text:
                    pravac_vetra = text.split()[0]

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