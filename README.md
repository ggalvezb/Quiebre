# Quiebre

Sitio ciudadano que muestra, votación por votación, cuánto se aparta cada diputado de la posición
mayoritaria de su coalición en la Cámara de Diputadas y Diputados de Chile.

Sin backend: un script Python descarga los datos abiertos oficiales y deja cuatro JSON estáticos que
la página lee directo. Se puede publicar gratis en GitHub Pages y se actualiza solo todos los días.

## Estructura

```
etl/
  api.py                    cliente de los web services de camara.cl, con cache en disco
  build.py                  descarga, calcula los indices y escribe docs/data/*.json
  demo.py                   datos ficticios para revisar el diseño sin conexion
  config/coaliciones.json   mapa partido -> coalicion y parametros del calculo
docs/                       el sitio (esto es lo que publica GitHub Pages)
  index.html  styles.css  app.js
  data/       diputados.json  votaciones.json  coaliciones.json  meta.json
cache/                      XML crudo de la API, para no volver a pedir lo ya descargado
.github/workflows/actualizar.yml
```

## Correrlo localmente

```bash
python -m etl.demo                  # datos de ejemplo, para ver el sitio de inmediato
python -m etl.build --desde 2026    # datos reales
cd docs && python -m http.server 8000
```

Y abrir http://localhost:8000

`build.py` solo usa la biblioteca estándar, no hay dependencias que instalar.

## El cálculo

Para cada votación y cada coalición se toma la posición mayoritaria entre sus integrantes que
votaron a favor o en contra. Si hay empate, o si votaron menos de `min_votantes_coalicion`, esa
votación no cuenta para esa coalición porque no había línea que romper.

El **índice de quiebre** de un diputado es la proporción de votaciones en que se apartó de esa
posición. Una abstención frente a una coalición que sí fijó postura suma `peso_abstencion`
(0,5 por defecto). Ausencias y pareos no entran en el denominador.

La **cohesión** de una coalición es el índice de Rice: la diferencia entre bloque mayoritario y
minoritario dividida por el total de votantes, promediada sobre todas las votaciones con línea.

La **asistencia** de un diputado es la proporción de votaciones de la ventana en que emitió un
voto (a favor, en contra o abstención). El servicio de la Cámara distingue "No Vota" (ausencia
simple) de "Dispensado" (pareo formal, acordado de antemano); ninguno de los dos cuenta como
presente, y se reportan por separado en la ficha de cada diputado.

Ambos parámetros se editan en `etl/config/coaliciones.json`.

## Límites conocidos

- Todas las votaciones pesan igual, sean de fondo o de trámite. Ponderar por relevancia exige un
  criterio que hoy no está en los datos.
- Solo cubre votaciones de sala. Las de comisión no están en el mismo servicio.
- La asistencia se mide por presencia en el registro de voto, no por un servicio de asistencia a
  sesiones (la Cámara no publica uno). Un diputado que llega y no alcanza a votar igual cuenta
  como ausente en esa votación.
- Apartarse de la coalición no es en sí mismo bueno ni malo. El sitio lo dice explícitamente.

