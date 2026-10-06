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
        print("Tabela nije pronađena na glavnoj RHMZ stranici.")
        return []

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
    rows = table.find_all('tr')[1:]
    vreme_sada = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for row in rows:
        cols = row.find_all('td')
        if len(cols) < 3:
            continue

        grad_idx = header_map.get('grad', 0)
        grad = cols[grad_idx].text.strip() if len(cols) > grad_idx else ""

        if not grad or grad.startswith('(') or any(x in grad.lower() for x in
                                                   ['stanica', 'станција', 'град', 'mesto', 'podaci', 'подаци', 'hpa',
                                                    'subjektivni']):
            continue

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

        if not opis:
            for col in cols:
                img = col.find('img')
                if img:
                    opis = img.get('title') or img.get('alt') or ""
                    break

        def get_col_text(key):
            idx = header_map.get(key)
            if idx is not None and len(cols) > idx:
                return cols[idx].text.strip()
            return ""

        temp = parse_number(get_col_text('temp'))
        pritisak = parse_number(get_col_text('pritisak'))
        vlaznost_num = parse_number(get_col_text('vlaznost'))
        vlaznost = int(vlaznost_num) if vlaznost_num is not None else None

        vetar_txt = get_col_text('vetar')
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


def fetch_automatic_stations():
    url = "https://www.hidmet.gov.rs/latin/osmotreni/automatske.php"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

    try:
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table')

        if not table:
            print("Tabela nije pronađena na automatske.php.")
            return []

        # Detekcija zaglavlja za automatske stanice
        header_map = {}
        header_row = table.find('tr')
        if header_row:
            headers_list = header_row.find_all(['th', 'td'])
            for idx, h in enumerate(headers_list):
                txt = h.text.strip().lower()
                if 'stanica' in txt or 'станица' in txt:
                    header_map['stanica'] = idx
                elif 'vreme' in txt or 'врем' in txt or 'datum' in txt:
                    header_map['vreme'] = idx
                elif 'temp' in txt or 'темп' in txt:
                    header_map['temp'] = idx
                elif 'vlaz' in txt or 'влаж' in txt:
                    header_map['vlaznost'] = idx
                elif 'pritis' in txt or 'притис' in txt:
                    header_map['pritisak'] = idx
                elif 'vetar' in txt or 'ветар' in txt or 'вет' in txt:
                    header_map['vetar'] = idx

        # Podrazumevani indeksi ako mapiranje po tekstu ne uspe
        idx_stanica = header_map.get('stanica', 0)
        idx_vreme = header_map.get('vreme', 1)
        idx_temp = header_map.get('temp', 2)
        idx_vlaznost = header_map.get('vlaznost', 3)
        idx_pritisak = header_map.get('pritisak', 4)
        idx_vetar = header_map.get('vetar', 5)

        data = []
        rows = table.find_all('tr')[1:]

        for row in rows:
            cols = [ele.text.strip() for ele in row.find_all(['td', 'th'])]
            if len(cols) < 4:
                continue

            stanica = cols[idx_stanica] if len(cols) > idx_stanica else ""
            if not stanica or stanica.startswith('(') or any(x in stanica.lower() for x in ['stanica', 'станица', 'mesto']):
                continue

            vreme_txt = cols[idx_vreme] if len(cols) > idx_vreme else ""
            temp = parse_number(cols[idx_temp]) if len(cols) > idx_temp else None

            vlaznost_num = parse_number(cols[idx_vlaznost]) if len(cols) > idx_vlaznost else None
            vlaznost = int(vlaznost_num) if vlaznost_num is not None else None

            pritisak = parse_number(cols[idx_pritisak]) if len(cols) > idx_pritisak else None
            vetar_txt = cols[idx_vetar] if len(cols) > idx_vetar else ""

            data.append({
                "stanica": stanica,
                "vreme": vreme_txt,
                "temperatura": temp,
                "vlaznost": vlaznost,
                "pritisak": pritisak,
                "vetar": vetar_txt
            })

        return data
    except Exception as e:
        print(f"Greška pri skrapovanju automatskih stanica: {e}")
        return []


def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Greška: Nisu podešene SUPABASE_URL i SUPABASE_KEY promenljive!")
        return

    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

    # 1. Glavne stanice
    print("Prikupljanje glavnih stanica...")
    records_glavne = scrape_rhmz()
    if records_glavne:
        supabase.table("merenja").upsert(records_glavne, on_conflict="grad,vreme_osmotreno").execute()
        print(f"Uspešno upisano {len(records_glavne)} glavnih stanica u bazu.")

    # 2. Automatske stanice
    print("Prikupljanje automatskih stanica...")
    records_automatske = fetch_automatic_stations()
    if records_automatske:
        supabase.table("automatske_stanice").insert(records_automatske).execute()
        print(f"Uspešno upisano {len(records_automatske)} automatskih stanica u bazu.")


if __name__ == "__main__":
    main()