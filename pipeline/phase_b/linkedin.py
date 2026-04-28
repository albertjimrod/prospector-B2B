import os
import time
import random
import sqlite3
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from pipeline.config import DB_PATH, RAW_DIR, LINKEDIN_EMAIL, LINKEDIN_PASSWORD

CARGOS_DECISOR = [
    'ceo', 'cto', 'coo', 'cfo', 'director', 'gerente', 'fundador', 'cofundador',
    'head of', 'responsable', 'socio', 'partner', 'presidente', 'propietario',
    'owner', 'founder', 'co-founder', 'managing', 'general manager',
]


def init_driver():
    opts = Options()
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-blink-features=AutomationControlled')
    opts.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
    opts.add_experimental_option('excludeSwitches', ['enable-automation'])
    opts.add_experimental_option('useAutomationExtension', False)
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=opts)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver


def login(driver):
    driver.get('https://www.linkedin.com/login')
    time.sleep(random.uniform(2, 4))
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, 'username')))
    except Exception:
        print(f'  ⚠ Página de login no cargó correctamente. URL actual: {driver.current_url}')
        print('  Comprueba la conexión o si LinkedIn está mostrando una página de bloqueo.')
        raise
    driver.find_element(By.ID, 'username').send_keys(LINKEDIN_EMAIL)
    time.sleep(random.uniform(0.5, 1.5))
    driver.find_element(By.ID, 'password').send_keys(LINKEDIN_PASSWORD)
    time.sleep(random.uniform(0.5, 1.0))
    driver.find_element(By.CSS_SELECTOR, '[type="submit"]').click()
    time.sleep(random.uniform(4, 6))

    # Si LinkedIn pide verificación, esperar a que el usuario la complete
    url = driver.current_url
    if any(kw in url for kw in ('checkpoint', 'challenge', 'verification', 'pin')):
        print('\n⚠ LinkedIn ha pedido verificación.')
        print('  Completa el proceso en el navegador (código por email/SMS, captcha, etc.)')
        input('  Pulsa Enter aquí cuando hayas completado la verificación... ')
        time.sleep(2)


def scrape_company(driver, linkedin_url):
    driver.get(linkedin_url)
    time.sleep(random.uniform(3, 5))

    bloques = []

    # Resumen / descripción de la empresa
    for selector in [
        'p.break-words.white-space-pre-wrap.t-black--light.text-body-medium',
        'p.break-words.t-black--light',
        '.org-about-us-organization-description__text',
        'p.break-words',
    ]:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, selector)
            texto = elem.text.strip()
            if texto:
                bloques.append(f'# Descripción\n{texto}')
                break
        except Exception:
            pass

    # Datos de empresa: sector, tamaño, sede, fundación, especialidades
    try:
        items = driver.find_elements(By.CSS_SELECTOR, 'dd.t-black--light.text-body-medium')
        for item in items[:8]:
            texto = item.text.strip()
            if texto:
                bloques.append(texto)
    except Exception:
        pass

    # Scroll para cargar posts
    driver.execute_script('window.scrollTo(0, 800)')
    time.sleep(random.uniform(1.5, 2.5))

    # Posts recientes (hasta 5)
    for selector in [
        '.feed-shared-update-v2__description-wrapper',
        '.attributed-text-segment-list__content',
        '[data-test-id="main-feed-activity-card"] span',
    ]:
        try:
            posts = driver.find_elements(By.CSS_SELECTOR, selector)[:5]
            if posts:
                bloques.append('# Posts recientes')
                for post in posts:
                    texto = post.text.strip()
                    if texto:
                        bloques.append(f'- {texto[:400]}')
                break
        except Exception:
            pass

    return '\n\n'.join(bloques)


def extraer_decisores(driver, linkedin_url):
    """Navega a /people/ y extrae decisores por cargo."""
    people_url = linkedin_url.rstrip('/') + '/people/'
    try:
        driver.get(people_url)
        time.sleep(random.uniform(3, 5))
        decisores = []
        cards = driver.find_elements(By.CSS_SELECTOR, '.org-people-profile-card__profile-info')[:12]
        for card in cards:
            try:
                nombre = card.find_element(By.CSS_SELECTOR, '.artdeco-entity-lockup__title .lt-line-clamp--single-line').text.strip()
                cargo = card.find_element(By.CSS_SELECTOR, '.artdeco-entity-lockup__subtitle .lt-line-clamp--multi-line').text.strip()
                try:
                    link = card.find_element(By.CSS_SELECTOR, 'a[href*="/in/"]')
                    profile_url = link.get_attribute('href')
                except Exception:
                    profile_url = None
                if nombre in ('Miembro de LinkedIn', 'LinkedIn Member', ''):
                    continue
                if any(c in cargo.lower() for c in CARGOS_DECISOR):
                    decisores.append({
                        'nombre': nombre,
                        'cargo': cargo,
                        'linkedin_profile_url': profile_url,
                        'is_decision_maker': 1,
                    })
            except Exception:
                continue
        return decisores[:3]
    except Exception:
        return []


def guardar_contactos(lead_id, contactos):
    if not contactos:
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        for c in contactos:
            conn.execute('''
                INSERT OR IGNORE INTO contactos
                (lead_id, nombre, cargo, linkedin_profile_url, is_decision_maker)
                VALUES (?,?,?,?,?)
            ''', (lead_id, c['nombre'], c['cargo'],
                  c.get('linkedin_profile_url'), c.get('is_decision_maker', 0)))
        conn.commit()
    finally:
        conn.close()


def guardar_raw(lead_id, contenido):
    path = os.path.join(RAW_DIR, str(lead_id), 'linkedin.txt')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(contenido)
    return path


def registrar_run(phase, status, message):
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            'INSERT INTO run_log (phase, status, message, finished_at) VALUES (?,?,?,?)',
            (phase, status, message, datetime.now().isoformat())
        )
        conn.commit()
    finally:
        conn.close()


def run(lead_id=None):
    conn = sqlite3.connect(DB_PATH)
    if lead_id:
        leads = conn.execute('''
            SELECT l.id, l.empresa, r.linkedin_url
            FROM leads l JOIN rrss r ON l.id=r.lead_id
            WHERE l.id=? AND r.linkedin_url IS NOT NULL
        ''', (lead_id,)).fetchall()
    else:
        leads = conn.execute('''
            SELECT l.id, l.empresa, r.linkedin_url
            FROM leads l JOIN rrss r ON l.id=r.lead_id
            WHERE r.linkedin_url IS NOT NULL AND l.status IN ("pending","enriching")
        ''').fetchall()
    conn.close()

    if not leads:
        print('[Fase B · linkedin] Sin leads con LinkedIn URL. Saltando.')
        return

    print(f'[Fase B · linkedin] {len(leads)} empresas a scrape')
    driver = None
    ok = err = 0

    try:
        driver = init_driver()
        login(driver)

        for lid, empresa, linkedin_url in leads:
            print(f'  Scrapeando: {empresa} ({linkedin_url})')
            try:
                contenido = scrape_company(driver, linkedin_url)
                if contenido.strip():
                    guardar_raw(lid, contenido)
                ok += 1

                decisores = extraer_decisores(driver, linkedin_url)
                if decisores:
                    guardar_contactos(lid, decisores)
                    nombres = ', '.join(d['nombre'] for d in decisores)
                    print(f'  ✓ {empresa} — {len(contenido)} chars | Decisores: {nombres}')
                else:
                    print(f'  ✓ {empresa} — {len(contenido)} chars | Sin decisores detectados')

                time.sleep(random.uniform(6, 12))
            except Exception as e:
                print(f'  ✗ Error en {empresa}: {e}')
                err += 1
    finally:
        if driver:
            driver.quit()

    registrar_run('B_linkedin', 'ok', f'{ok} scrapeados, {err} errores')
    print(f'\n[linkedin completado] {ok} ok, {err} errores')
