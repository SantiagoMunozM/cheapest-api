# TODO — Lab 2: Pruebas de Carga al Monolito de Cheapest

Leyenda de esfuerzo: `[low]` `[medium]` `[high]`

## Etapa 1 — Contexto experimental

- [X] `[low]` Leer y entender ASR1 (GET, p99 < 1000ms, 500 req/min) y ASR2 (POST, error% ≤ 2%, 5000 req/min)
- [X] `[low]` Identificar el criterio de "punto de inflexión" (basta con incumplir uno de los dos ASRs)

## Etapa 2 — Preparación del entorno

- [X] `[low]` Clonar/actualizar repo Cheapest-api y hacer `git checkout load_tests`
- [X] `[low]` Limpiar contenedor `cheapest-postgres` de labs anteriores si aplica (`docker stop` / `docker rm`)
- [X] `[low]` Levantar PostgreSQL (`docker compose up postgres -d`)
- [X] `[medium]` Instalar dependencias y levantar el backend (`npm install`, `npm run start:dev`); resolver errores de instalación/config
- [X] `[low]` Verificar `http://localhost:3000/health`
- [X] `[medium]` Instalar JMeter (y JDK 8+ si falta); verificar `java -version`
- [X] `[low]` Descargar `load_test.jmx` y explorarlo en JMeter (Thread Groups, samplers, listeners)

## Etapa 3 — Diseño de la prueba de carga

- [X] `[medium]` Revisar `producto.repository.ts` (GET, 3 `EXISTS`) y `pedido.service.ts` / `pedido.repository.ts` (POST) para identificar cuellos de botella (índices, pool `pg`=10)
- [X] `[high]` Diseñar `load-seed.yaml`: cantidades (tiendas, zonas, catálogos por zona, productos, promociones activas, pedidos históricos por tienda) con distribución tipo Pareto, justificadas con el contexto de Cheapest — usar warm-up (`lab_2_warmup.md`) como insumo
- [X] `[medium]` Crear variantes del `load-seed.yaml` por escenario (una para estresar GET, otra para estresar POST) y documentar a qué prueba corresponde cada una
- [X] `[medium]` Responder Pregunta 2 (sesgos de distribución uniforme + dos estrategias de distribución justificadas)
- [X] `[medium]` Responder Pregunta 1 (priorización GET vs. POST antes de un pico comercial)
- [X] `[medium]` Responder Pregunta 3 (diseño experimental alternativo con variables controladas: pool de conexiones vs. consultas ineficientes vs. límites de JMeter)

## Etapa 4 — Ejecución de pruebas

- [X] `[low]` Ejecutar smoke test, baja carga y carga media en JMeter (1 corrida cada uno)
- [X] `[medium]` Ejecutar operación normal en JMeter (5 corridas, 450 threads) — evalúa ASR1
- [ ] `[high]` Generar con IA el script Python para cargas > 450 threads (CLI args, CSV, p95/p99/throughput/error%, manejo de timeouts); guardar los prompts usados
- [X] `[medium]` Ejecutar alta carga, muy alta carga y estrés con el script Python (3 corridas cada uno)
- [X] `[high]` Ejecutar estrés fuerte / pico (5 corridas, 18000 users) — evalúa ASR2
- [X] `[high]` Gestionar limpieza entre campañas: `docker compose down -v` + re-seed entre campaña GET y campaña POST, y cada vez que cambie `load-seed.yaml`
- [X] `[medium]` Capturar evidencia por corrida (Summary Report, Aggregate Report/Percentiles de Latencia, configuración JMeter/script) — para el script Python: `load-testing/results/*/*/run*/console.log` + `results_{get,post}.csv`
- [X] `[medium]` Registrar resultados de cada corrida en la tabla (p99, p95, throughput, error%) a medida que se ejecutan — 28 corridas del script Python en `load-testing/results/summary_table.csv`; faltan las de JMeter
- [X] `[low]` Responder Pregunta 4 (técnicas para consistencia de código IA entre equipo)

## Etapa 5 — Entregables y conclusiones

- [ ] `[low]` Completar tabla de resultados final (sección 1) con las ~44 corridas
- [ ] `[high]` Redactar análisis de resultados (sección 2): punto de inflexión, cuello de botella y patrón de degradación (con evidencia de código), distribución de datos usada, reflexión de arquitectura
- [ ] `[medium]` Consolidar informe final en Word/PDF: tabla, capturas, prompts, respuestas Preguntas 1–4, análisis
- [ ] `[low]` Empaquetar entregable de código: `load-seed.yaml` (todas las variantes), script Python, `results_get.csv` / `results_post.csv`, gráficas
- [ ] `[low]` Comprimir todo en un único `.zip` y subir a Bloque Neón
