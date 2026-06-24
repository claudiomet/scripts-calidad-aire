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
3. **Formatos Visuales**:
   - Gráficos de barras sin separación (`width=1.0` en diarios).
   - Eje Y fijo al máximo global (o a la norma primaria/secundaria si existen y son mayores).
   - Títulos dinámicos (`FORMATO_TITULO`).
   - Grilla punteada de fondo (`ax.set_axisbelow(True)` y `linestyle=':'`).
4. **Búsqueda Robusta de Columnas**:
   - Los archivos CSV de entrada pueden tener subíndices (ej. `SO₂`). El código ya posee un método universal (`str.translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()`) para buscar las columnas omitiendo mayúsculas/minúsculas y convirtiendo subíndices a números normales.

## Estado del Trabajo (Progreso):
Se han creado exitosamente dos scripts en el directorio base:
- `script-horario-chart.py`
- `script-diario-chart.py`

## Próximos Pasos (Tareas Pendientes):
El usuario solicitará continuar con alguna de las siguientes tareas. Cuando lo haga, actúa directamente aplicando las mismas reglas de negocio y estética visual:
1. Gráficas de promedios **mensuales** y **anuales**.
2. **Ciclos horarios y diarios** (Boxplots).
3. **Reporte Consolidado**: Un script final que recolecte todos los hallazgos `.txt` exportados por los scripts individuales (ej. `fecha_max_dia_anioX=...`) y ensamble un documento unificado.

## Instrucción de Comportamiento:
Asume el rol de una ingeniera de desarrollo de software especializada en normativas técnicas de calidad del aire para Chile. Mantén el código limpio, sin comentarios redundantes y sin sobrecomplicar las lógicas ya establecidas.
