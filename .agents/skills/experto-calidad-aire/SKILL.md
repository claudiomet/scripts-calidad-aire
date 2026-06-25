---
name: experto-calidad-aire
description: Provee contexto sobre el proyecto de calidad del aire en Chile, incluyendo reglas normativas, scripts completados y tareas pendientes para continuar el desarrollo.
---

# Contexto del Proyecto: Reportes de Calidad del Aire (Chile)

El usuario está desarrollando un sistema de automatización en Python para generar gráficas y reportes de calidad del aire basados en datos de estaciones monitoras, siguiendo la normativa chilena.

## Reglas de Negocio Implementadas y a Respetar:
1. **Suficiencia de Datos (75%)**: 
   - Para promedios diarios estándar (MP10, MP2.5, SO2, NO2), se requieren al menos 18 horas válidas por día.
2. **Excepción O3 y CO**: 
   - Para Ozono y Monóxido de Carbono, la métrica diaria NO es el promedio de 24h, sino el **Máximo del Promedio Móvil de 8 horas**. Se requiere un mínimo de 6 horas válidas para calcular el promedio móvil.
3. **Agregación en Cascada (Anual)**:
   - El promedio anual se calcula a partir de los mensuales válidos. Exige al menos 9 meses válidos (>=75% de 12).
4. **Exportación de Textos (Estandarización)**:
   - El loop de extracción de textos (`.txt`) siempre itera sobre todo el set esperado (ej. `AÑO_INICIO` a `AÑO_FIN`).
   - Las variables como `anio1`, `anio2` deben corresponder cronológicamente independientemente de la validez de los datos. Si un periodo es inválido, las variables se escriben vacías (ej: `valor_max_dia_anio1=`).
5. **Formatos Visuales**:
   - Gráficos de barras sin separación (`width=1.0` en diarios).
   - Eje Y fijo al máximo global (o a la norma primaria/secundaria si existen y son mayores).
   - Títulos dinámicos (`FORMATO_TITULO`).
   - Grilla punteada de fondo (`ax.set_axisbelow(True)` y `linestyle=':'`).
   - Barras de datos insuficientes (<75%) se colorean de gris (`#b0b0b0`).
6. **Búsqueda Robusta de Columnas**:
   - Los archivos CSV de entrada pueden tener subíndices (ej. `SO₂`). El código ya posee un método universal (`str.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()`) para buscar las columnas omitiendo mayúsculas/minúsculas y convirtiendo subíndices a números normales.

## Reglas Normativas Específicas por Contaminante:
1. **Dióxido de Azufre (SO2)**: 
   - *Primaria (D.S. 104/2018)*: Límite anual = 60 µg/m³. Exige 3 trimestres válidos (cada uno con 75% de datos) para validar un año. Límite diario = 150 µg/m³ (percentil 99). Límite horario = 350 µg/m³ (percentil 99).
   - *Secundaria (D.S. 22/2009)*: Límite anual = 80 µg/m³ (aritmético estricto de 24 meses). No usa regla trimestral. Límite diario = 365 µg/m³ (percentil 99.7). Límite horario = 1000 µg/m³ (percentil 99.73).

2. **Principio Precautorio (Imputación de 11 meses)**:
   Aplica a **NO2, MP10, MP2.5, Arsénico (AS) y Benceno (COV)**. Si un año tiene entre 9 y 10 meses válidos, los meses faltantes se imputan buscando el mes máximo del año anterior.
   - *AS, NO2, MP, COV*: Distingue entre semestre cálido (Ene-Mar, Oct-Dic) y frío (Abr-Sep). Busca el máximo del respectivo semestre.
   - *Plomo (Pb)*: No distingue semestres. Busca el máximo global de los 12 meses del año anterior.

3. **Ausencia de Normas Cortas**:
   - **Arsénico (AS), Plomo (Pb) y Benceno (COV)** carecen de percentiles horarios y diarios. Su única norma es de exposición crónica anual (AS: 23 ng/m³, Pb: 0.5 µg/m³, COV: 3 µg/m³).
   - Los scripts `script-percentil-diario-chart.py` y `script-percentil-horario-chart.py` abortarán silenciosamente la ejecución si se intenta correr para estos contaminantes.

4. **Archivos Modificados**:
   Todos los scripts base ya están adaptados para manejar el enrutamiento dinámico, aislar el dibujo de límites primarios/secundarios y abortar limpiamente si el contaminante no aplica.

## Estado del Trabajo (Progreso):
Se han creado y ajustado exitosamente bajo la nueva lógica normativa los siguientes scripts base:
- `script-horario-chart.py`
- `script-diario-chart.py`
- `script-mensual-chart.py`
- `script-trimestral-chart.py`
- `script-anual-chart.py`
- `script-percentil-diario-chart.py`
- `script-percentil-horario-chart.py`

## Próximos Pasos (Tareas Pendientes):
- **Reporte Consolidado**: Un script final que recolecte todos los hallazgos `.txt` exportados por los scripts individuales (ej. `fecha_max_dia_anioX=...`) y ensamble un documento unificado tabular.

## Instrucción de Comportamiento:
Asume el rol de una ingeniera de desarrollo de software especializada en normativas técnicas de calidad del aire para Chile. Mantén el código limpio, sin comentarios redundantes y sin sobrecomplicar las lógicas ya establecidas.
