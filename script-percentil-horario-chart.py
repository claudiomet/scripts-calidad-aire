import pandas as pd
import numpy as np

MOSTRAR_INFO_QAQC = True

def oscurecer_color(hex_color, factor=0.5):
    import matplotlib.colors as mcolors
    try:
        rgb = mcolors.to_rgb(hex_color)
        dark_rgb = [max(0, c * factor) for c in rgb]
        return mcolors.to_hex(dark_rgb)
    except:
        return '#000000'

import matplotlib.pyplot as plt
import os
import re
import glob

# ==============================================================================
# 1. PARÁMETROS CONFIGURABLES
# ==============================================================================
INPUT_DIR = "input"
CONTAMINANTE = "SO2"  # Editable, ej: "CO", "SO2", "MP10", "O3", etc.
AÑO_INICIO = 2023
AÑO_FIN = 2025
UNIDADES = "µg/m³N"  # Puede cambiar según el contaminante
FORMATO_TITULO = "Percentil Horario de {contaminante} - Estación {estacion}"
COLOR_TITULO = "white"  # 'white' para ocultar, 'black' para mostrar
NORMA_PRIMARIA = 200  
NORMA_SECUNDARIA = None 

# --- DIMENSIONES DEL GRÁFICO ---
ANCHO_GRAFICO_PX = 1280
ALTO_GRAFICO_PX = 480
DPI_GRAFICO = 100

# Mismo color por año 
COLORES_POR_AÑO = {
    2022: '#8c564b',
    2023: '#1f77b4', # Azul
    2024: '#ff7f0e', # Naranja
    2025: '#2ca02c', # Verde
    2026: '#d62728', # Rojo
    2027: '#9467bd', # Morado
}

# Configuración normativa por contaminante
# Metodo puede ser 'MAXIMOS_DIARIOS' (ej. NO2, CO) o 'TODAS_LAS_HORAS' (ej. SO2)
CONFIGURACION_PERCENTILES = {
    'no2': [{'nombre': 'no2', 'percentil': 99, 'metodo': 'MAXIMOS_DIARIOS'}],
    'co': [
        {'nombre': 'co_1h', 'percentil': 99, 'metodo': 'MAXIMOS_DIARIOS'},
        {'nombre': 'co_8h', 'percentil': 99, 'metodo': 'MAXIMOS_DIARIOS_8H'}
    ],
    'so2': [
        {'nombre': 'so2pri', 'percentil': 99, 'metodo': 'TODAS_LAS_HORAS'},
        {'nombre': 'so2sec', 'percentil': 99.73, 'metodo': 'TODAS_LAS_HORAS'}
    ],
    'o3': [{'nombre': 'o3', 'percentil': 99, 'metodo': 'MAXIMOS_DIARIOS_8H'}],
    'default': [{'nombre': 'default', 'percentil': 99, 'metodo': 'TODAS_LAS_HORAS'}]
}
# ==============================================================================

def calcular_percentil_normativa(serie, q=99):
    """
    Calcula el percentil aplicando estrictamente la fórmula de la normativa:
    k = round(q * n)
    Donde 'n' es la cantidad de valores efectivamente medidos.
    """
    serie_valida = serie.dropna().sort_values().values
    n = len(serie_valida)
    if n == 0:
        return np.nan
    
    frac = q / 100.0
    k = int(round(frac * n))
    
    if k < 1:
        k = 1
    if k > n:
        k = n
        
    return serie_valida[k-1]

def extraer_nombre_estacion(filename):
    basename = os.path.basename(filename)
    name_without_ext = os.path.splitext(basename)[0]
    prefixes = [
        "calidad-aire-dia-hora",
        "calidad-aire-dia",
        "calidad-aire-mes-procesado",
        "analisis-quimico-anual-diario",
        "analisis-quimico"
    ]
    clean_name = name_without_ext
    for p in prefixes:
        clean_name = re.sub(rf'(?i)^{p}\s*', '', clean_name)
    return clean_name.strip().lower().replace(" ", "_")

def obtener_directorio_salida_grafico(contaminante_sufijo):
    cont_str = contaminante_sufijo.lower().replace(",", "").replace(".", "")
    if cont_str.startswith('co_'):
        return "output_co_chart"
    if cont_str.startswith('so2'):
        return "output_so2_chart"
    return f"output_{cont_str}_chart"

def obtener_directorio_salida_texto(contaminante_sufijo):
    cont_str = contaminante_sufijo.lower().replace(",", "").replace(".", "")
    if cont_str.startswith('co_'):
        return "output_co_text"
    if cont_str.startswith('so2'):
        return "output_so2_text"
    return f"output_{cont_str}_text"

def procesar_fechas_dataframe(df):
    if 'Fecha' in df.columns:
        # Intentamos el parseo con dayfirst=True
        df['Fecha_fmt'] = pd.to_datetime(df['Fecha'], dayfirst=True, errors='coerce').dt.strftime('%Y-%m-%d')
        if 'Hora' in df.columns and df['Hora'].notnull().any():
            def formatear_hora(h):
                if pd.isna(h): return "00:00"
                try:
                    h_int = int(float(h))
                    if h_int >= 24: h_int = 0
                    return f"{h_int:02d}:00"
                except:
                    return "00:00"
            df['Hora_fmt'] = df['Hora'].apply(formatear_hora)
            df['Datetime'] = pd.to_datetime(df['Fecha_fmt'] + ' ' + df['Hora_fmt'], errors='coerce')
        else:
            df['Datetime'] = pd.to_datetime(df['Fecha_fmt'], errors='coerce')
    return df

def main():
    cont_key = CONTAMINANTE.lower()
    
    if cont_key in ['as', 'arsenico', 'arsénico', 'pb', 'plomo', 'cov', 'covs', 'benceno']:
        print(f"El contaminante {CONTAMINANTE} no posee norma de percentil horario. Omitiendo script.")
        return
        
    if cont_key in CONFIGURACION_PERCENTILES:
        configs = CONFIGURACION_PERCENTILES[cont_key]
    else:
        configs = CONFIGURACION_PERCENTILES['default']
        configs[0]['nombre'] = cont_key

    for config in configs:
        nombre_conf = config['nombre']
        q_target = config['percentil']
        metodo = config['metodo']

        out_dir_chart = obtener_directorio_salida_grafico(nombre_conf)
        out_dir_text = obtener_directorio_salida_texto(nombre_conf)

        archivos_csv = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
        if not archivos_csv:
            continue

        print(f"-> Procesando {nombre_conf.upper()} (Percentil {q_target}, Método {metodo})...")
        
        # FASE 1: Buscar máximo global entre todas las estaciones para unificar la escala Y
        global_max = 0.0
        max_estacion = ""
        max_año = ""
        resultados_estaciones = []

        for filepath in archivos_csv:
            try:
                df = pd.read_csv(filepath, sep=',', encoding='utf-8', on_bad_lines='skip')
            except UnicodeDecodeError:
                df = pd.read_csv(filepath, sep=',', encoding='latin1', on_bad_lines='skip')
            except Exception:
                continue

            cont_norm = str(CONTAMINANTE).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()
            col_objetivo = next((c for c in df.columns if cont_norm in str(c).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()), None)
            
            if not col_objetivo:
                continue
                
            estacion = extraer_nombre_estacion(filepath)
            df = procesar_fechas_dataframe(df)
            
            if df.empty or 'Datetime' not in df.columns:
                continue
                
            if df[col_objetivo].dtype == object:
                df[col_objetivo] = df[col_objetivo].astype(str).str.replace('"', '').str.replace(',', '.').astype(float)

            df['Year'] = df['Datetime'].dt.year
            df['Date'] = df['Datetime'].dt.date
            
            df_plot = []
            texto_hallazgos = ""
            i_year = 1
            
            for year in range(AÑO_INICIO, AÑO_FIN + 1):
                df_year = df[df['Year'] == year].copy()
                
                texto_hallazgos += f"anio{i_year}={year}\n"
                
                percentil_val = np.nan
                pct_validos = 0.0
                es_valido = False
                
                tot = 8760.0
                val = 0.0
                if not df_year.empty:
                    df_year = df_year.dropna(subset=[col_objetivo])
                    
                    if metodo == 'MAXIMOS_DIARIOS':
                        df_daily_max = df_year.groupby('Date')[col_objetivo].max()
                        dias_validos = len(df_daily_max)
                        tot = 365.0
                        val = dias_validos
                        pct_validos = (dias_validos / 365.0) * 100.0
                        if dias_validos >= 274: 
                            es_valido = True
                        if dias_validos > 0:
                            percentil_val = calcular_percentil_normativa(df_daily_max, q_target)
                            
                    elif metodo == 'MAXIMOS_DIARIOS_8H':
                        # Para promedios móviles, necesitamos ordenar por fecha y usar rolling
                        df_year_sorted = df_year.sort_values('Datetime').drop_duplicates(subset=['Datetime']).set_index('Datetime')
                        # Promedio móvil de 8 horas con mínimo de 6 horas válidas
                        df_year_sorted['movil_8h_valido'] = df_year_sorted[col_objetivo].rolling('8h', min_periods=6).mean()
                        # El máximo diario de 8h requiere al menos 18 promedios válidos en el día
                        daily_count = df_year_sorted['movil_8h_valido'].resample('D').count()
                        daily_max = df_year_sorted['movil_8h_valido'].resample('D').max()
                        df_daily_max = daily_max[daily_count >= 18]
                        
                        dias_validos = len(df_daily_max)
                        tot = 365.0
                        val = dias_validos
                        pct_validos = (dias_validos / 365.0) * 100.0
                        if dias_validos >= 274:
                            es_valido = True
                        if dias_validos > 0:
                            percentil_val = calcular_percentil_normativa(df_daily_max, q_target)
                            
                    elif metodo == 'TODAS_LAS_HORAS':
                        horas_validas = len(df_year)
                        tot = 8760.0
                        val = horas_validas
                        pct_validos = (horas_validas / 8760.0) * 100.0
                        if horas_validas >= 6570: 
                            es_valido = True
                        if horas_validas > 0:
                            percentil_val = calcular_percentil_normativa(df_year[col_objetivo], q_target)
                
                if pd.notna(percentil_val):
                    if percentil_val > global_max:
                        global_max = percentil_val
                        max_estacion = estacion
                        max_año = year
                    texto_hallazgos += f"percentil_horario_anio{i_year}={int(round(percentil_val))}\n"
                else:
                    texto_hallazgos += f"percentil_horario_anio{i_year}=\n"
                    
                texto_hallazgos += f"validos_anio{i_year}={pct_validos:.1f}\n"
                
                df_plot.append({
                    'Year': year,
                    'Percentil': percentil_val if pd.notna(percentil_val) else 0,
                    'Valido': es_valido,
                    'tot': tot,
                    'val': val,
                    'pct': pct_validos
                })
                i_year += 1
                
            df_plot = pd.DataFrame(df_plot)
            if df_plot['Percentil'].sum() > 0:
                resultados_estaciones.append({
                    'estacion': estacion,
                    'texto_hallazgos': texto_hallazgos,
                    'df_plot': df_plot
                })

        # Calcular Y máximo global
        y_max_plot = global_max
        if NORMA_PRIMARIA is not None:
            y_max_plot = max(y_max_plot, NORMA_PRIMARIA)
        if NORMA_SECUNDARIA is not None:
            y_max_plot = max(y_max_plot, NORMA_SECUNDARIA)
            
        if global_max > 0:
            print(f"   [INFO] Valor máximo del percentil detectado: {global_max:.2f} (Estación: '{max_estacion}', Año: {max_año})")
        print(f"   [INFO] Escala Y global fijada en: {y_max_plot:.2f}\n")

        # FASE 2: Generar archivos TXT y gráficos con escala unificada
        for res in resultados_estaciones:
            estacion = res['estacion']
            texto_hallazgos = res['texto_hallazgos']
            df_plot = res['df_plot']
            
            # Guardar TXT
            filename_txt = f"{estacion}-{nombre_conf}-percentil_horario-{AÑO_INICIO}-{AÑO_FIN}.txt"
            filepath_txt = os.path.join(out_dir_text, filename_txt)
            with open(filepath_txt, 'w', encoding='utf-8') as f:
                f.write(texto_hallazgos.strip() + "\n")
            print(f"   Generado texto: {filepath_txt}")
                
            # Gráfico de barras
            fig, ax = plt.subplots(figsize=(ANCHO_GRAFICO_PX / DPI_GRAFICO, ALTO_GRAFICO_PX / DPI_GRAFICO))
            
            for _, row in df_plot.iterrows():
                y_val = row['Year']
                p_val = row['Percentil']
                is_val = row['Valido']
                color_base = COLORES_POR_AÑO.get(y_val, '#555555')
                color_bar = color_base if is_val else '#b0b0b0'
                

                ax.bar(y_val, p_val, color=color_bar, width=0.6, edgecolor='black', linewidth=0.5, zorder=3)
                
                if MOSTRAR_INFO_QAQC:
                    y_pos = y_max_plot * 0.02
                    color_oscuro = oscurecer_color(color_bar, 0.4)
                    tot_row = row['tot']
                    val_row = row['val']
                    pct_row = row['pct']
                    texto_qa = f"tot:{int(tot_row)}\nval:{int(val_row)}\n%:{pct_row:.1f}"
                    ax.text(y_val, y_pos, texto_qa, color=color_oscuro, 
                            ha='center', va='bottom', fontsize=6, zorder=4)

                
                if pd.notnull(p_val) and p_val > 0:
                    ax.annotate(f'{int(round(p_val))}',
                                xy=(y_val, p_val),
                                xytext=(0, 3),  
                                textcoords="offset points",
                                ha='center', va='bottom', fontsize=10, fontweight='bold', zorder=4)
                
            ax.set_ylim(0, y_max_plot + 10)
            ax.set_xticks(df_plot['Year'])
            ax.set_xticklabels(df_plot['Year'], rotation=0)
            
            ax.set_ylabel(UNIDADES, fontsize=11)
            
            titulo_base = FORMATO_TITULO.format(contaminante=nombre_conf.upper(), estacion=estacion.replace('_', ' ').title())
            if metodo == 'MAXIMOS_DIARIOS':
                titulo_base += f"\n(P{q_target} de Máx. Diarios)"
            else:
                titulo_base += f"\n(P{q_target} de concentraciones)"
                
            ax.set_title(titulo_base, color=COLOR_TITULO, fontsize=14, pad=15)
            
            ax.set_axisbelow(True)
            ax.grid(True, axis='y', linestyle=':', alpha=0.7, zorder=0)
            
            # Lineas de Norma
            xlims = ax.get_xlim()
            if NORMA_PRIMARIA is not None and not nombre_conf.endswith('sec'):
                ax.axhline(y=NORMA_PRIMARIA, color='red', linestyle='-', linewidth=1.5, zorder=4)
                ax.text(xlims[1], NORMA_PRIMARIA, "Valor de la Norma Primaria ", 
                        color='black', fontsize=10, va='bottom', ha='right', fontweight='bold')
                        
            if NORMA_SECUNDARIA is not None and not nombre_conf.endswith('pri'):
                ax.axhline(y=NORMA_SECUNDARIA, color='red', linestyle='--', linewidth=1.5, zorder=4)
                ax.text(xlims[1], NORMA_SECUNDARIA, "Valor de la Norma Secundaria ", 
                        color='black', fontsize=10, va='bottom', ha='right', fontweight='bold')
            
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor='#b0b0b0', edgecolor='black', linewidth=0.5, label='Datos < 75% (No válido)')
            ]
            ax.legend(handles=legend_elements, loc='upper center', bbox_to_anchor=(0.5, -0.09), frameon=False, ncol=1)
            
            filename_img = f"{estacion}-{nombre_conf}-percentil_horario-{AÑO_INICIO}-{AÑO_FIN}.png"
            filepath_img = os.path.join(out_dir_chart, filename_img)
            fig.subplots_adjust(bottom=0.15, top=0.92, left=0.06, right=0.98)
            plt.savefig(filepath_img, dpi=DPI_GRAFICO)
            plt.close(fig)
            print(f"   Generado gráfico: {filepath_img}")
            
        print("\n¡Proceso completado con éxito!\n")

if __name__ == '__main__':
    main()
