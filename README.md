# Fundamentals Lab

**Los números de cualquier empresa cotizada en EE. UU., en un sitio.** El visitante busca por
ticker o por nombre y ve:

- **Fundamentales:** 10 años de cuenta de resultados, balance y flujo de caja (y 12 trimestres),
  con márgenes, ROE, ROIC, deuda, crecimiento y uso de la caja.
- **Valoración:** PER, EV/EBITDA, EV/Ventas, P/FCF y rentabilidades por dividendo y recompra hoy,
  y cada múltiplo en el cierre de cada ejercicio pasado, con su mediana.
- **Múltiplos a futuro:** el consenso de analistas de los próximos ejercicios convertido en el
  múltiplo al que cotizaría la acción si se cumple y el precio no se mueve. Es el consenso, no una
  predicción nuestra, y no se calcula ningún precio objetivo.
- **Análisis técnico:** velas con medias de 50 y 200 sesiones, Bollinger, RSI, MACD, volumen,
  niveles de giro, volatilidad, caída máxima y beta frente al S&P 500. Se describe, no se dan
  señales.
- **Comparador:** de 2 a 5 empresas lado a lado, precios en base 100 y crecimiento frente a
  valoración.
- **Lectura con IA:** Claude lee los números ya calculados y explica lo que muestran. Solo
  describe: nada de recomendaciones, predicciones ni precios objetivo.

Es una pieza del portal de herramientas de IA para inversión del autor, junto al
[Earnings Radar](https://earningsradar.app/). Usa el mismo stack para poder unificarlas.

> No es un sistema de trading ni de asesoramiento. No hay código que envíe órdenes ni que se
> conecte a un broker.

## Fuentes

| Qué | De dónde |
|---|---|
| Perfil, estados financieros, precios diarios y consenso de analistas | Yahoo Finance (`yfinance`); FMP con `MARKET_DATA=fmp` |
| Lista de empresas del buscador; estados anuales de respaldo | SEC EDGAR (`company_tickers.json` y XBRL `companyfacts`) |
| Lectura de los números | Claude (API de Anthropic) |

Las fórmulas están en la página `/method/` del sitio y en `src/fundamentals/metrics.py`,
`forward.py` y `technical.py`.

## Puesta en marcha

```bash
uv sync                  # Python 3.12 y dependencias
cd site && npm ci && cd ..
cp .env.example .env     # ANTHROPIC_API_KEY, SEC_USER_AGENT (los datos salen de Yahoo Finance, sin clave)
make test                # tests en verde, sin red
make api                 # API en :8000
make dev                 # web en :4321 (en otra terminal)
```

Línea de comandos: `uv run fundamentals search apple`, `uv run fundamentals report AAPL`,
`uv run fundamentals compare AAPL MSFT`. La lectura con IA gasta y pide `--yes`.

## Despliegue

`make deploy` construye la imagen con Cloud Build y la despliega en Cloud Run (web y API en un
contenedor, escala a cero). Las claves van a Secret Manager y un bucket guarda informes, lecturas
y el registro de gasto. Nada está programado ni en GitHub Actions.

## Topes de gasto

| Límite | Valor por defecto | Dónde |
|---|---|---|
| Gasto de la lectura con IA por día (UTC) | $0.50 | `READING_DAILY_MAX_USD`, al desplegar |
| Gasto total de la lectura con IA | $5.00 | `READING_TOTAL_MAX_USD`, al desplegar |
| Peor caso por petición | $0.15 | `READING_REQUEST_MAX_USD` en `config.py` |
| Lecturas por IP y hora | 30 | `PER_IP_PER_HOUR` en `config.py` |
| Instancias simultáneas | 2 | `MAX_INSTANCES` al desplegar |

Una lectura se guarda para todo el día: cada empresa cuesta como mucho una llamada diaria, la
pida quien la pida. Abrir una página nunca gasta: la lectura solo se escribe al pulsar el botón.
