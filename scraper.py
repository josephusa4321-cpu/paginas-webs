"""
Encuentra restaurantes y locales en Medellín que tienen Instagram pero NO tienen página web.
Fuente principal: Google Maps (via Patchright browser) + búsqueda de Instagram por nombre.
"""

import time
import json
import re
import csv

from patchright.sync_api import sync_playwright
from scrapling.fetchers import Fetcher

# ─── Configuración ────────────────────────────────────────────────────────────

SEARCH_QUERIES_MAPS = [
    "restaurantes medellin colombia",
    "cafeterias medellin colombia",
    "bares medellin colombia",
    "comida rapida medellin colombia",
    "pizzerias medellin colombia",
    "heladerias medellin colombia",
    "pastelerias medellin colombia",
]

SCROLL_ROUNDS = 12       # cuántas veces hacer scroll en el feed de Maps
DELAY_BETWEEN = 1.2      # segundos entre scrolls

OUTPUT_CSV  = "resultados.csv"
OUTPUT_JSON = "resultados.json"


# ─── Utilidades ───────────────────────────────────────────────────────────────

INSTAGRAM_RE = re.compile(r'instagram\.com/([A-Za-z0-9_.]{3,30})', re.I)
SOCIAL_DOMAINS = ('instagram.com', 'facebook.com', 'twitter.com',
                  'tiktok.com', 'youtube.com', 'linkedin.com', 'wa.me',
                  'whatsapp.com', 'linktr.ee', 't.me')


def _is_own_website(url: str) -> bool:
    """True si la URL parece ser un sitio web propio (no red social ni Google)."""
    lower = url.lower()
    if 'google.' in lower or not url.startswith('http'):
        return False
    return not any(s in lower for s in SOCIAL_DOMAINS)


def find_instagram(text: str) -> str:
    m = INSTAGRAM_RE.search(text)
    return f"https://www.instagram.com/{m.group(1)}/" if m else ""


# ─── Fase 1: Google Maps → lista de locales ───────────────────────────────────

def scrape_maps_listings(playwright_page, query: str) -> list[dict]:
    """
    Busca `query` en Google Maps, hace scroll para cargar resultados y
    visita cada listing para extraer website e Instagram.
    """
    url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
    playwright_page.goto(url, wait_until='domcontentloaded', timeout=25000)

    try:
        playwright_page.wait_for_selector('div[role="feed"]', timeout=12000)
    except Exception:
        print(f"  [!] Feed no encontrado para: {query}")
        return []

    feed = playwright_page.query_selector('div[role="feed"]')
    for _ in range(SCROLL_ROUNDS):
        feed.press('End')
        time.sleep(DELAY_BETWEEN)

    playwright_page.wait_for_timeout(2000)
    anchors = playwright_page.query_selector_all('div[role="feed"] > div > div > a')
    print(f"  -> {len(anchors)} locales encontrados en '{query}'")

    results = []
    for anchor in anchors:
        name  = anchor.get_attribute('aria-label') or ''
        href  = anchor.get_attribute('href') or ''
        if not name:
            continue
        results.append({'nombre': name.strip(), 'maps_url': href})

    return results


def get_place_details(playwright_page, place: dict) -> dict:
    """
    Abre el panel de detalle de un local en Maps y extrae website e Instagram.
    """
    place_url = place.get('maps_url', '')
    if not place_url:
        return place

    playwright_page.goto(place_url, wait_until='domcontentloaded', timeout=20000)
    playwright_page.wait_for_timeout(3000)

    # Website propio
    website = ''
    web_link = playwright_page.query_selector('a[data-item-id="authority"]')
    if web_link:
        website = web_link.get_attribute('href') or ''

    # Instagram: a veces aparece en el panel de detalle como link externo
    instagram = ''
    all_links = playwright_page.query_selector_all('a[href*="instagram.com"]')
    if all_links:
        instagram = all_links[0].get_attribute('href') or ''

    # Texto completo de la página para buscar menciones de Instagram
    if not instagram:
        page_text = playwright_page.inner_text('body')
        instagram = find_instagram(page_text)

    place.update({
        'website': website,
        'instagram': instagram,
        'tiene_pagina_web': bool(website and _is_own_website(website)),
    })
    return place


# ─── Fase 2: Verificar Instagram por nombre vía búsqueda web ─────────────────

def search_instagram_by_name(name: str) -> str:
    """
    Busca el Instagram de un local usando la API de DuckDuckGo JSON.
    Menos bloqueada que el HTML de DDG.
    """
    import urllib.parse, urllib.request

    query = urllib.parse.quote(f'site:instagram.com "{name}" medellin')
    url = f"https://api.duckduckgo.com/?q={query}&format=json&no_html=1&skip_disambig=1"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        # AbstractURL puede contener el perfil
        abstract_url = data.get('AbstractURL', '')
        if 'instagram.com' in abstract_url:
            return abstract_url
        # Buscar en los RelatedTopics
        for topic in data.get('RelatedTopics', []):
            text = topic.get('Text', '') + ' ' + topic.get('FirstURL', '')
            ig = find_instagram(text)
            if ig:
                return ig
    except Exception:
        pass

    # Fallback: buscar con Scrapling en Bing (sin SSL proxy issues)
    try:
        query2 = urllib.parse.quote(f'instagram.com {name} medellin')
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; Scrapling)'}
        page = Fetcher.get(
            f'https://www.bing.com/search?q={query2}',
            headers=headers
        )
        return find_instagram(page.html_content)
    except Exception:
        pass

    return ''


# ─── Pipeline principal ───────────────────────────────────────────────────────

def main():
    print("=" * 65)
    print("  Buscador: Instagram SIN página web — Medellín, Colombia")
    print("=" * 65)

    todos_locales: list[dict] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(ignore_https_errors=True)
        page = ctx.new_page()

        # ── Fase 1a: listar locales desde Maps ──────────────────────────
        print("\n[1/3] Recopilando locales desde Google Maps...")
        seen_names: set[str] = set()
        raw_listings: list[dict] = []

        for query in SEARCH_QUERIES_MAPS:
            listings = scrape_maps_listings(page, query)
            for loc in listings:
                key = loc['nombre'].lower().strip()
                if key not in seen_names:
                    seen_names.add(key)
                    raw_listings.append(loc)

        print(f"\n  Total únicos en Maps: {len(raw_listings)}")

        # ── Fase 1b: obtener detalles (website / Instagram) ───────────────
        print("\n[2/3] Revisando website e Instagram en Maps...")
        for i, loc in enumerate(raw_listings, 1):
            try:
                loc = get_place_details(page, loc)
            except Exception as e:
                print(f"  [!] Error en '{loc['nombre']}': {e}")
                loc.setdefault('website', '')
                loc.setdefault('instagram', '')
                loc.setdefault('tiene_pagina_web', False)

            if i % 10 == 0:
                print(f"  ... {i}/{len(raw_listings)} procesados")

            todos_locales.append(loc)

        browser.close()

    # ── Fase 2: para los sin web, buscar Instagram si aún no lo tiene ──
    print("\n[3/3] Buscando Instagram de locales sin web...")
    sin_web = [r for r in todos_locales if not r.get('tiene_pagina_web')]
    print(f"  Locales sin web: {len(sin_web)}")

    for loc in sin_web:
        if loc.get('instagram'):
            continue
        ig = search_instagram_by_name(loc['nombre'])
        if ig:
            loc['instagram'] = ig
        time.sleep(0.8)

    # ── Resultado final: sin web Y CON Instagram ──────────────────────
    resultado_final = [
        r for r in sin_web
        if r.get('instagram') and 'instagram.com' in r.get('instagram', '')
    ]

    print(f"\n{'=' * 65}")
    print(f"  TOTAL: locales con Instagram pero SIN página web: {len(resultado_final)}")
    print(f"{'=' * 65}\n")

    for i, r in enumerate(resultado_final, 1):
        print(f"  {i:3}. {r['nombre']:<40} {r['instagram']}")

    guardar_csv(resultado_final)
    guardar_json(resultado_final)

    # Resumen adicional: los que tienen web (para contexto)
    con_web = [r for r in todos_locales if r.get('tiene_pagina_web')]
    print(f"\n  (Para referencia: {len(con_web)} locales SÍ tienen página web propia)")


# ─── Guardado ─────────────────────────────────────────────────────────────────

def guardar_csv(datos: list[dict]):
    if not datos:
        print("  [!] Sin datos para guardar en CSV")
        return
    keys = ['nombre', 'instagram', 'website', 'maps_url']
    with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(datos)
    print(f"\n[+] CSV guardado: {OUTPUT_CSV}  ({len(datos)} registros)")


def guardar_json(datos: list[dict]):
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print(f"[+] JSON guardado: {OUTPUT_JSON}  ({len(datos)} registros)")


if __name__ == '__main__':
    main()
