# Estado del proyecto y cómo continuar

Última actualización: 2026-10-05. Este documento basta para retomar el trabajo en otra sesión,
sin el historial de la conversación.

## Qué se pidió

El usuario quiere montar un portal (una marca) con varias herramientas de IA para inversión y
bolsa. La primera es el Earnings Radar (`decision-signal-lab`, en https://earningsradar.app/).
Esta es la segunda, en un repo aparte; más adelante el usuario las unificará.

Encargo del 2026-10-05: una herramienta que saque los números de una empresa:
- todos los fundamentales;
- análisis técnico;
- cómo se espera que vayan los múltiplos a futuro;
- comparación de varias acciones;
- búsqueda por ticker o por nombre.

Decisiones del usuario ese día:
- Datos: **FMP + SEC** (plan gratuito de FMP para desarrollar; Starter, unos $22/mes, al publicar).
- Mercado: **solo EE. UU.** en la primera versión.
- Destino: **web pública en Cloud Run**, con el mismo patrón que el radar.
- **Lectura con IA desde el MVP**, con **Claude**.
- Repo `fundamentals-lab`, **público**.

## Dónde estamos

| Hecho | Pendiente |
|---|---|
| Backend en `src/fundamentals/`: FMP (`fmp.py`), SEC (`sec.py`, buscador y estados anuales de respaldo), ratios y múltiplos (`metrics.py`), múltiplos futuros (`forward.py`), técnico (`technical.py`), informe (`report.py`), comparador (`compare.py`), lectura con Claude (`reading.py`), topes (`budget.py`), API (`api.py`), CLI (`cli.py`) | **Nada se ha probado contra las APIs reales**: la red del entorno donde se escribió bloqueaba FMP y la SEC |
| 45 tests en verde, sin red (datos sintéticos y respuestas con la forma de FMP y de la SEC) | Confirmar con respuestas reales los nombres de campo de FMP (`fmp.py` acepta varios nombres por campo, pero no se han visto respuestas reales) |
| Web Astro (`site/`): portada con buscador, ficha de acción con 4 pestañas (Overview con lectura IA, Fundamentals, Valuation & forward, Technical), comparador y Method. Revisada en Chromium a 1280 y 390 px con datos sintéticos: sin desbordes, sin errores de consola | Revisarla con datos reales |
| Lectura con IA: `claude-opus-5-5`, esfuerzo `low`, salida JSON con esquema, `fallbacks: "default"`. Se guarda por día y por empresa; abrir una página nunca gasta | **Ninguna llamada real a Claude todavía.** La clave de Anthropic está en `.env` y responde (listado de modelos, gratis) |
| `Makefile`, `Dockerfile`, `scripts/deploy-cloudrun.sh` (secretos, bucket, topes por variable de entorno). La clave de Anthropic sale del secreto `ANTHROPIC_API_KEY` de Secret Manager (`ANTHROPIC_SECRET`); sin clave, la lectura responde que está apagada | **Desplegado el 2026-10-05** como servicio `fundamentals-lab` (europe-west1), para `fundamentals.themarkethub.app` |
| Repo público en GitHub: `alejandrorodriguezalvarez884-dot/fundamentals-lab`, creado por el usuario el 2026-10-05; código subido a `main` | |
| | Que el usuario confirme los topes por defecto ($0.50 al día, $5 en total, $0.15 por petición) y el modelo |
| **Dentro de Market Hub (2026-10-05)**: estilo nuevo (tema oscuro de Market Hub, `HubBar.astro` en la cabecera) y login obligatorio a través del hub: con `HUB_URL` y `HUB_SESSION_SECRET`, `src/fundamentals/hubauth.py` solo deja pasar a quien tenga la cookie `mh_session` del hub firmada con su secreto; sin sesión, las páginas van al login del hub y la API responde 401. Sin límite por IP detrás del login (decisión del usuario); los topes de la lectura siguen | Probar con datos reales de FMP y la primera lectura real con Claude |

### Coste estimado de la lectura con IA

Medido sobre los datos sintéticos: el documento de una empresa ocupa unos 4.400 caracteres (unos
1.500–2.000 tokens) y el de una comparación de 5 empresas unos 14.500 (unos 5.000 tokens).

| Lectura | Opus 5.5 ($4/$20 por millón) | Sonnet 5.5 ($2/$10) |
|---|---|---|
| Una empresa (≈2k de entrada, ≈1,5k de salida con el razonamiento) | ≈ $0.04 | ≈ $0.02 |
| Comparación de 5 (≈5k de entrada, ≈2k de salida) | ≈ $0.06 | ≈ $0.03 |

Con el tope diario de $0.50 salen unas 10–12 lecturas nuevas al día con Opus; las repetidas del
mismo día son gratis. Cambiar a Sonnet: `READING_MODEL=claude-sonnet-5-5 make deploy`.

## Cómo está hecho

- **Los números los calcula el código, siempre.** `report.build()` junta perfil, estados (anuales
  y trimestrales), precios de la empresa y de SPY, y consenso; calcula TTM, ratios por periodo,
  múltiplos actuales, múltiplos históricos (precio al cierre de cada ejercicio), múltiplos futuros
  y técnico. El informe se guarda 12 horas en el store (carpeta `data/store` en local, bucket en
  Cloud Run), para no gastar la cuota de FMP (unas 9 llamadas por empresa).
- **Si FMP falla**, los estados anuales salen de la SEC (XBRL de los 10-K) y la web avisa con una
  nota. Sin FMP no hay precios ni consenso.
- **Múltiplos futuros:** precio de hoy ÷ consenso de cada ejercicio futuro. El rango del PER usa
  el BPA alto y bajo. No hay precio objetivo.
- **Técnico:** solo describe ("RSI 74, por encima de 70"). Ningún texto dice comprar o vender;
  hay un test que lo comprueba.
- **Lectura con IA:** recibe `report.compact()` (sin series de gráficos). El prompt prohíbe
  recomendar, predecir y calificar de barata o cara. El `max_tokens` se ajusta para que el peor
  caso quepa en el tope por petición; el gasto real se apunta en `ledger/reading`.
- **API:** `/api/search`, `/api/stock/{t}`, `/api/stock/{t}/stream` (pasos en vivo, NDJSON),
  `/api/stock/{t}/reading` (con `cached_only=1` no gasta), `/api/compare?tickers=`,
  `/api/compare/reading`, `/api/budget`.

## Siguientes pasos, en orden

1. Abrir la red del entorno a `financialmodelingprep.com`, `www.sec.gov` y `data.sec.gov`, o
   trabajar en local.
2. Poner `FMP_API_KEY` y `SEC_USER_AGENT` en `.env` y ejecutar `uv run fundamentals report AAPL`.
   Comparar unas cifras con la web de la empresa o con FMP y corregir los nombres de campo.
3. Con permiso del usuario, una lectura real: `uv run fundamentals reading AAPL --yes` (≈ $0.04).
4. `make serve` y revisar la web con datos reales.
5. `make deploy` y, si el usuario quiere, un dominio.
