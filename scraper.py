"""
Encuentra restaurantes y locales en Medellín que tienen Instagram pero NO tienen página web.
Fuente: Google Maps (búsqueda web scraping)
"""

import time
import json
import re
import csv
from scrapling.fetchers import Fetcher, StealthyFetcher

SEARCH_QUERIES = [
    "restaurantes Medellín Colombia instagram",
    "cafeterias Medellín Colombia instagram",
    "bares Medellín Colombia instagram",
    "comidas rapidas Medellín Colombia instagram",
    "pizzerias Medellín Colombia instagram",
]

INSTAGRAM_PATTERN = re.compile(r'instagram\.com/([A-Za-z0-9_.]+)', re.IGNORECASE)
WEBSITE_KEYWORDS = ['.com', '.co', '.net', '.org', '.io', '.co.co']


def has_instagram(text: str) -> str | None:
    """Retorna el handle de Instagram si existe en el texto."""
    match = INSTAGRAM_PATTERN.search(text)
    if match:
        return match.group(0)
    return None


def has_website(text: str) -> bool:
    """Detecta si el texto menciona una página web propia (no instagram/facebook)."""
    social_domains = ('instagram.com', 'facebook.com', 'twitter.com', 'tiktok.com',
                      'youtube.com', 'linkedin.com', 'whatsapp.com')
    urls = re.findall(r'https?://[^\s"\'<>]+', text, re.IGNORECASE)
    for url in urls:
        lower = url.lower()
        if not any(s in lower for s in social_domains):
            return True
    return False


def scrape_google_maps_search(query: str) -> list[dict]:
    """Extrae resultados de búsqueda de Google para locales con Instagram."""
    results = []
    search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}&num=20"

    try:
        page = StealthyFetcher.fetch(search_url, headless=True, network_idle=True)
    except Exception:
        # Fallback a Fetcher básico si StealthyFetcher falla
        page = Fetcher.get(search_url)

    # Extraer bloques de resultados orgánicos
    for result in page.css('div.g, div[data-ved]'):
        text = result.get_text(separator=' ')
        link_tags = result.css('a[href]')
        href = ''
        for a in link_tags:
            h = a.attrib.get('href', '')
            if h.startswith('http') and 'google.com' not in h:
                href = h
                break

        instagram_url = has_instagram(text) or has_instagram(href)
        if not instagram_url:
            continue

        # Buscar nombre del negocio (etiqueta h3 dentro del bloque)
        name_tag = result.css('h3')
        name = name_tag[0].get_text() if name_tag else 'Sin nombre'

        # Buscar descripción
        desc_tags = result.css('span, div')
        description = ''
        for d in desc_tags:
            t = d.get_text(separator=' ').strip()
            if len(t) > 30:
                description = t[:200]
                break

        website = has_website(text) or has_website(href)

        results.append({
            'nombre': name,
            'instagram': f"https://{instagram_url}",
            'tiene_pagina_web': website,
            'descripcion': description[:200],
            'fuente': href,
        })

    return results


def scrape_instagram_search_medellin() -> list[dict]:
    """
    Busca directamente en Instagram hashtags de restaurantes de Medellín.
    Extrae perfiles que aparezcan en los resultados.
    """
    results = []
    hashtags = [
        'restaurantesmedellin',
        'foodmedellin',
        'cafeteriamedellin',
        'comidamedellin',
        'baresdemedellin',
    ]

    for tag in hashtags:
        url = f"https://www.instagram.com/explore/tags/{tag}/"
        try:
            page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
            # Extraer handles de Instagram del contenido
            page_text = page.get_text(separator=' ')
            handles = set(re.findall(r'@([A-Za-z0-9_.]{3,30})', page_text))

            for handle in handles:
                results.append({
                    'nombre': handle,
                    'instagram': f"https://www.instagram.com/{handle}/",
                    'hashtag_origen': tag,
                    'tiene_pagina_web': None,  # Se verifica después
                })
        except Exception as e:
            print(f"[!] Error en hashtag #{tag}: {e}")
        time.sleep(2)

    return results


def verify_instagram_profile(handle: str) -> dict:
    """
    Visita el perfil de Instagram y verifica si tiene link de web externo.
    """
    url = f"https://www.instagram.com/{handle}/"
    result = {'instagram': url, 'website_en_bio': False, 'website_url': ''}
    try:
        page = StealthyFetcher.fetch(url, headless=True, network_idle=True)
        page_text = page.get_text(separator=' ')

        # Buscar link externo en la bio (suele aparecer como texto de enlace)
        external_links = page.css('a[href*="http"]:not([href*="instagram.com"])')
        for link in external_links:
            href = link.attrib.get('href', '')
            social_domains = ('facebook.', 'twitter.', 'tiktok.', 'youtube.', 'linktr.ee')
            if href and not any(s in href.lower() for s in social_domains):
                result['website_en_bio'] = True
                result['website_url'] = href
                break

        # Buscar linktree (cuenta como "tiene web")
        if 'linktr.ee' in page_text or 'linktree' in page_text.lower():
            result['website_en_bio'] = True
            result['website_url'] = 'linktr.ee (intermediario)'

    except Exception as e:
        print(f"[!] Error verificando {handle}: {e}")

    return result


def guardar_csv(datos: list[dict], archivo: str = 'resultados.csv'):
    if not datos:
        return
    keys = datos[0].keys()
    with open(archivo, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(datos)
    print(f"[+] Guardado: {archivo} ({len(datos)} registros)")


def guardar_json(datos: list[dict], archivo: str = 'resultados.json'):
    with open(archivo, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    print(f"[+] Guardado: {archivo} ({len(datos)} registros)")


def main():
    print("=" * 60)
    print("  Buscador: Instagram SIN página web — Medellín, Colombia")
    print("=" * 60)

    todos = []

    # --- Fase 1: Búsqueda en Google ---
    print("\n[1/2] Buscando en Google Maps/Search...")
    for query in SEARCH_QUERIES:
        print(f"  -> '{query}'")
        try:
            r = scrape_google_maps_search(query)
            todos.extend(r)
            print(f"     {len(r)} resultados encontrados")
        except Exception as e:
            print(f"     Error: {e}")
        time.sleep(3)

    # --- Fase 2: Hashtags de Instagram ---
    print("\n[2/2] Buscando por hashtags en Instagram...")
    ig_results = scrape_instagram_search_medellin()
    print(f"  -> {len(ig_results)} handles encontrados")

    # Verificar si cada perfil tiene web en su bio
    sin_web = []
    print("  -> Verificando bios de Instagram...")
    seen = set()
    for item in ig_results:
        handle = item['nombre']
        if handle in seen:
            continue
        seen.add(handle)

        verificacion = verify_instagram_profile(handle)
        if not verificacion['website_en_bio']:
            sin_web.append({
                'nombre': handle,
                'instagram': item['instagram'],
                'tiene_pagina_web': False,
                'hashtag_origen': item['hashtag_origen'],
                'descripcion': '',
            })
        time.sleep(1.5)

    todos.extend(sin_web)

    # --- Filtrar: solo los que NO tienen web ---
    solo_instagram = [r for r in todos if not r.get('tiene_pagina_web')]

    # Deduplicar por instagram URL
    vistos = set()
    unicos = []
    for r in solo_instagram:
        key = r.get('instagram', '').lower().strip('/')
        if key and key not in vistos:
            vistos.add(key)
            unicos.append(r)

    print(f"\n{'=' * 60}")
    print(f"  TOTAL locales con Instagram pero SIN web: {len(unicos)}")
    print(f"{'=' * 60}\n")

    for i, r in enumerate(unicos[:20], 1):
        print(f"  {i:2}. {r.get('nombre', 'N/A'):<30} {r.get('instagram', '')}")

    if len(unicos) > 20:
        print(f"  ... y {len(unicos) - 20} más (ver archivos de salida)")

    guardar_csv(unicos, 'resultados.csv')
    guardar_json(unicos, 'resultados.json')


if __name__ == '__main__':
    main()
