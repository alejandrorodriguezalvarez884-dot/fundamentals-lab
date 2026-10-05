# Instrucciones para agentes

Lee primero [docs/HANDOFF.md](docs/HANDOFF.md): estado, pendientes y siguientes pasos.

Reglas que no se negocian:
- **Nada de trading.** No se escribe código que envíe órdenes ni que se conecte a un broker, y
  no se usa ningún conector de broker (IBKR u otro), ni siquiera para descargar precios.
- **Describir, no recomendar.** La web y la lectura con IA no dicen comprar, vender ni mantener,
  no llaman barata o cara a una acción, no predicen precios ni calculan precios objetivo. Los
  múltiplos futuros son el consenso de analistas al precio de hoy y se rotulan así.
- **La IA no inventa números.** Todo número sale del código (`metrics.py`, `forward.py`,
  `technical.py`); el modelo solo recibe esos números (`report.compact`) y los comenta.
- **El servicio público gasta con las claves del usuario.** No se suben ni se quitan los topes
  (`READING_DAILY_MAX_USD`, `READING_TOTAL_MAX_USD`, `READING_REQUEST_MAX_USD`, límite por IP) sin
  preguntarle. Antes de una llamada real a Claude o de pasar a un plan de pago de FMP, se le pide
  permiso.
- **Nada programado y nada en GitHub Actions.** Todo se lanza a mano desde el `Makefile`.
- **Claves solo en `.env` o en el entorno.** Nunca en el repo, en logs ni en commits, y nunca
  el cuerpo de un error de un proveedor en lo que ve el visitante.

Convenciones:
- Hablar con el usuario en español. Código, comentarios y textos de la web en inglés.
- Python 3.12 con `uv`. Tests con `make test`; web con `make check`.
- Cada cambio en una fórmula lleva su test en `tests/`.
- Al terminar una tarea relevante, actualizar "Dónde estamos" en `docs/HANDOFF.md`.
