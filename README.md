# Buscador: Restaurantes con Instagram pero sin página web — Medellín

Usa la librería [Scrapling](https://github.com/D4Vinci/Scrapling) para encontrar restaurantes y locales en Medellín, Colombia que tienen perfil de Instagram pero **no tienen página web propia**.

## Instalación

```bash
pip install -r requirements.txt
scrapling install   # descarga el navegador para modo stealth
```

## Uso

```bash
python scraper.py
```

Genera dos archivos de salida:
- `resultados.csv` — apto para Excel / Google Sheets
- `resultados.json` — formato estructurado

## Cómo funciona

| Fase | Fuente | Qué hace |
|------|--------|----------|
| 1 | Google Search | Busca consultas como "restaurantes Medellín instagram" y extrae URLs de Instagram de los resultados |
| 2 | Instagram Hashtags | Explora `#restaurantesmedellin`, `#foodmedellin`, etc. y recolecta handles |
| 2b | Bio de Instagram | Visita cada perfil y detecta si tiene enlace web externo en la bio |

## Agregar más búsquedas

Edita las listas en `scraper.py`:

```python
# Más consultas de Google
SEARCH_QUERIES = [
    "heladerias Medellín Colombia instagram",
    ...
]

# Más hashtags
hashtags = [
    'arepasdemedellin',
    ...
]
```

## Requisitos

- Python 3.10+
- Scrapling con soporte de fetchers (Playwright)
