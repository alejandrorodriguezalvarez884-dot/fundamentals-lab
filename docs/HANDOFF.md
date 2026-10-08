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

> 2026-10-08: **Playground en la barra de My Hub** (desplegado como `fundamentals-lab-00015-x65`).
> "Tools" de la barra lateral lleva una herramienta más, **Playground**
> (https://playground.themarkethub.app, repo `market-hub-playground`): un tablero de gráficos y
> tablas que se compone pidiéndolo por chat. `PLAYGROUND_URL` y el enlace en `HubNav.astro`.
> Desplegado desde una copia limpia del commit, con la configuración del servicio idéntica a la de
> antes. El subdominio estaba esperando su certificado de Google al desplegar: hasta que se emita,
> el enlace no abre.

> 2026-10-08: **Peers ya no vive aquí: es una herramienta propia, Peer Map**
> (`market-hub-peers-map`, https://peers.themarkethub.app). Ese mismo día, unas horas antes, se había
> hecho como sección de Fundamentals Lab (página `/peers/`, bloque "Similar businesses" en la
> ficha, botones en el comparador; commit `4c24569`, desplegado como `fundamentals-lab-00014-kbr`)
> y después el usuario pidió sacarlo a un despliegue aparte y **quitarlo todo de aquí**. El
> commit se revirtió entero: Fundamentals Lab queda como estaba, sin página, sin bloque, sin
> botones, sin `/api/peers` y sin el grupo de dependencias del batch. Lo único nuevo es el enlace
> `Peers` en `HubNav.astro` (Tools), que lleva a la herramienta nueva. El código, el mapa
> (`peers.json`) y el trabajo del batch (`data/peers/`) están en el otro repo.
> **Sin desplegar todavía**: producción sigue en `fundamentals-lab-00014-kbr`, con la página Peers
> dentro, hasta que `peers.themarkethub.app` resuelva (falta el CNAME `peers` →
> `ghs.googlehosted.com` en Cloudflare, que pone el usuario). Así no hay un rato sin Peers ni un
> enlace roto en la navegación.

> 2026-10-07: **los datos salen de Yahoo Finance (`yfinance`), no de FMP** (desplegado ese día como
> `fundamentals-lab-00012-c98`, con el histórico largo de la SEC; topes y configuración como estaban).
> Decisión del usuario: FMP no contestó a su petición de licencia y la cuota gratuita (250 llamadas
> al día) tumbaba la ficha; pidió "los últimos datos disponibles gratis". `src/fundamentals/yahoo.py`
> (`YahooClient`) da las mismas cuatro respuestas que `FmpClient` con los nombres propios del
> proyecto: perfil, estados (anuales y trimestrales), precios ajustados y consenso. `MARKET_DATA`
> elige: `yahoo` (por defecto) o `fmp` (como antes); `make deploy` ya no exige la clave de FMP.
> Con ello se cierra de paso el fallo del 429 de FMP de la nota siguiente.
> - **Lo que cambia en la ficha**: Yahoo da **4 años fiscales y 5 trimestres**. El consenso es solo
>   de **ventas y BPA, para el año fiscal en curso y el siguiente**: no hay EV/EBITDA futuro.
> - **Histórico anual largo, con la SEC** (`src/fundamentals/backfill.py`, pedido por el usuario el
>   mismo día): los años anteriores a los de Yahoo salen de los 10-K (XBRL), hasta 11 en total, para
>   que el crecimiento a 5 y 10 años tenga datos. Dos condiciones: los años que tienen las dos
>   fuentes deben cuadrar (ventas, beneficio neto y BPA, con un 3 % de margen; si no, no se añade
>   nada y la ficha se queda en 4 años con su nota), y lo que es por acción se pasa a acciones de
>   hoy (`sec.py` guarda cuándo se presentó cada cifra, `per_share_filed`, y se aplican los splits
>   posteriores, que da Yahoo). El histórico se corta en el primer año que falte o no traiga ventas,
>   porque el crecimiento cuenta filas hacia atrás. La fuente lo dice en la ficha ("Yahoo Finance;
>   SEC EDGAR (XBRL) before fiscal 2022") y la página Method lo explica.
>   Comprobado con datos reales: Apple, NVIDIA, Alphabet, Tesla, Microsoft, Walmart y Coca-Cola se
>   alargan y sus BPA antiguos cuadran con los splits; JPMorgan y Berkshire no (las dos fuentes no
>   cuentan igual los ingresos de un banco o una aseguradora) y se quedan en 4 años. Los años de la
>   SEC traen menos líneas (sin coste de ventas ni existencias, por ejemplo). **Los trimestres
>   siguen siendo los 5 de Yahoo**: sacarlos de los 10-Q es el paso siguiente, sin hacer.
> - **Avisado al usuario, que decidió seguir**: yfinance no es una API oficial, las condiciones de
>   Yahoo son de uso personal, y Yahoo puede rechazar las IP de un centro de datos. Desde Cloud Run Yahoo
>   responde en el portal; aquí **falta verlo con una sesión real** (el servicio pide login). Si
>   falla, `MARKET_DATA=fmp` y redesplegar.
> - Comprobado contra Yahoo desde el equipo Windows: Apple (9,7 s en frío, con la carga de pandas),
>   NVIDIA y JPMorgan (2 s cada una); trimestres colocados en su año fiscal (NVIDIA cierra en enero).
>   60 tests en verde (`tests/test_yahoo.py` y `tests/test_backfill.py`, sin red). La página Method nombra la fuente nueva.

> 2026-10-07: **visitas con Cloudflare Web Analytics** (sin cookies). `site/src/layouts/Layout.astro`
> carga su script solo en `themarkethub.app` y sus subdominios, con el token del sitio de Market Hub
> (uno para todo el dominio; va en el HTML, no es un secreto). La página de privacidad del portal
> lo dice. Desplegado el 2026-10-07 como `fundamentals-lab-00011-kmr` (variables, topes y secretos
> iguales que antes; comprobado: responde, pide sesión y el HTML lleva el script). Se mira en
> Cloudflare: Analytics & Logs → Web Analytics.

> 2026-10-06: **la ficha da "A data source did not answer" cuando FMP agota la cuota.** Comprobado
> ese día: FMP responde 429 ("Limit Reach") a `profile` con la clave de `.env`, que es la misma
> del servicio desplegado; en los logs, cinco `upstream failure for AAPL: UpstreamError`. Vuelve
> sola cuando FMP renueva la cuota diaria (250 llamadas en el plan gratuito). **Sin arreglar, dos
> cambios propuestos y no hechos:** que un 429 o un 5xx de FMP en perfil, trimestrales, precios y
> estimaciones se trate como `FmpUnavailable` (`report.py` solo captura esa excepción ahí, así
> que hoy tumba la ficha en vez de seguir con una nota), y que `_failure` en `api.py` registre la
> fuente y el código, sin el cuerpo. Sobre los datos: el usuario estudia pasar a FMP Starter
> (22 $/mes con pago anual, tiempo real, 300 llamadas/min) y ha redactado una petición a FMP de
> un acuerdo de licencia para mostrar datos; no ha decidido nada todavía.

> 2026-10-06: `scripts/deploy-cloudrun.sh` ya solo escribe un permiso cuando falta (`grant`): antes cada
> despliegue reescribía la política IAM del proyecto y dos a la vez chocaban ("concurrent policy
> changes"). Ahora los despliegues de los tres servicios pueden lanzarse en paralelo. Comprobado
> contra el proyecto sin escribir nada; aún no se ha hecho un despliegue en paralelo de verdad.

> 2026-10-06: `site/src/components/HubNav.astro` lleva dos enlaces más de My Hub, `Analysis` y
> `Community` (páginas nuevas del portal), igual que `App.astro` de `market-hub-landing`. Desplegado el mismo día.
>
> 2026-10-07: y uno más, `Watchlist`, entre `Analysis` y `Community` (la página nueva del portal,
> `/watchlist/`). Desplegado ese día como `fundamentals-lab-00013-56v` (variables, topes y secretos como estaban).

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

### Primera prueba con datos reales (2026-10-05, en local)

`uv run fundamentals report AAPL` con la clave real (plan gratuito de FMP): perfil, precios y
consenso salen de FMP y el informe se completa (múltiplos, márgenes, técnico y múltiplos futuros
de FY2026 a FY2028). **Los estados no salen de FMP:** el plan gratuito responde 402 cuando
`limit` pasa de 5, y el informe pide 10 años y 12 trimestres (`ANNUAL_YEARS`, `QUARTERS`). Con
`limit=5` responde 200, tanto anual como trimestral. Hoy los anuales caen a la SEC y no hay
trimestres, así que el TTM sale de los anuales. Sin probar todavía: el comparador, la web con
login y la lectura con IA.

**Hecho después (en `main`, desplegado como `fundamentals-lab-00003-pvc` el 2026-10-05):** `FmpClient.statements` pide 5 periodos
cuando el plan rechaza más (`BASIC_PLAN_PERIODS`, `period_cap`) y el informe lo dice en una nota.
47 tests en verde; con la clave real solo se comprobó `income-statement` con `limit=5`.

### Diseño del portal y cabecera compartida (2026-10-05, noche; desplegado como `fundamentals-lab-00004-zkt`)

La herramienta pasa a ser una sección de Market Hub. `site/src/styles/global.css` es el del portal
(más los estilos propios al final), con su tipografía y su regla de color: verde y rojo solo para
subidas y bajadas; las series de los gráficos usan colores que nombran la serie (`SERIES` en
`lib/charts.ts`). `components/Page.astro` lleva la cabecera del portal (`Markets · Fundamentals ·
Earnings`, buscador, cuenta) y debajo las páginas de la herramienta. La ficha de empresa tiene
las pestañas `Price · Fundamentals · Results release` (`companyTabs` en `lib/dom.ts`), que llevan
a la misma empresa en el portal y en el radar (`HUB_URL`, `RADAR_URL` en `lib/site.ts`). Las
secciones ya no son cajas (`card()` dibuja una regla y un título). 47 tests y `astro check` en
verde; revisado en local con el informe de AAPL guardado. El gráfico técnico se puede ver en velas o
en línea. Sin revisar: el comparador con datos y la web con sesión iniciada.

### Dentro de My Hub (2026-10-06; última revisión desplegada: `fundamentals-lab-00008-q2k`)

El usuario pidió que la herramienta quede integrada en el área privada del portal, porque solo se
consulta desde ahí. La cabecera pública del portal ya no la nombra.

- `components/HubNav.astro` sustituye a `HubBar.astro`: es la navegación de My Hub (la misma que
  `App.astro` en `market-hub-landing`): barra lateral en pantallas anchas con "Your space", "Tools"
  (esta marcada) y "Explore", el aviso de área privada y el usuario abajo; en pantallas estrechas,
  una barra arriba. Sigue redirigiendo al login del portal si la sesión caduca. Cerrar sesión se
  hace en el portal.
- `Page.astro`: encima de cada página queda la barra propia de la herramienta (nombre, `Company ·
  Compare · Method` y el buscador). Un cambio en la navegación de My Hub se hace en los tres repos.

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
