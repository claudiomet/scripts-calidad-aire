#!/usr/bin/env python3
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
CONTAMINANTE = "SO2"  # Editable, ej: "MP10", "MP2.5", "SO2"
AÑO_INICIO = 2023
AÑO_FIN = 2025
UNIDADES = "µg/m³N"  # Puede cambiar según el contaminante
FORMATO_TITULO = "Percentil Diario de {contaminante} - Estación {estacion}"
COLOR_TITULO = "white"  # 'white' para ocultar, 'black' para mostrar
NORMA_PRIMARIA = 130  
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

# Configuración normativa por contaminante (Percentil Diario de 24h)
CONFIGURACION_PERCENTILES_DIARIOS = {
    'mp10': [{'nombre': 'mp10', 'percentil': 98}],
    'mp2.5': [{'nombre': 'mp25', 'percentil': 98}],
    'mp25': [{'nombre': 'mp25', 'percentil': 98}],
    'no2': [{'nombre': 'no2', 'percentil': 99}],
    'so2': [
        {'nombre': 'so2pri', 'percentil': 99},
        {'nombre': 'so2sec', 'percentil': 99.7}
    ],
    'default': [{'nombre': 'default', 'percentil': 98}]
}
# ==============================================================================

def calcular_percentil_normativa(serie, q=98):
    """
    Calcula el percentil aplicando estrictamente la fórmula de la normativa chilena:
    k = round(q * n)
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

def calcular_valor_diario(df, col_objetivo, is_hourly, is_o3_co):
    """
    Calcula el valor representativo del día para aplicar el percentil de 24h.
    """
    if not is_hourly:
        df_daily = pd.DataFrame({
            'Datetime': df['Datetime'],
            'valor_diario': df[col_objetivo],
            'valido': df[col_objetivo].notnull()
        })
        df_daily['Fecha'] = pd.to_datetime(df_daily['Datetime'].dt.date)
        return df_daily.dropna(subset=['valor_diario'])

    df_idx = df.set_index('Datetime')

    if is_o3_co:
        df_idx['movil_8h_todos'] = df_idx[col_objetivo].rolling('8h', min_periods=1).mean()
        df_idx['movil_8h_valido'] = df_idx[col_objetivo].rolling('8h', min_periods=6).mean()
        daily_todos = df_idx['movil_8h_todos'].resample('D').max()
        daily_valido = df_idx['movil_8h_valido'].resample('D').max()
        df_daily = pd.DataFrame({
            'valor_diario': daily_todos,
            'valor_valido': daily_valido
        }).reset_index()
        df_daily['valido'] = df_daily['valor_valido'].notnull()
    else:
        daily_mean = df_idx[col_objetivo].resample('D').mean()
        daily_count = df_idx[col_objetivo].resample('D').count()
        df_daily = pd.DataFrame({
            'valor_diario': daily_mean,
            'count': daily_count
        }).reset_index()
        df_daily['valido'] = df_daily['count'] >= 18

    df_daily['Fecha'] = pd.to_datetime(df_daily['Datetime'].dt.date)
    return df_daily.dropna(subset=['valor_diario'])

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
    if cont_str.startswith('so2'):
        return "output_so2_chart"
    return f"output_{cont_str}_chart"

def obtener_directorio_salida_texto(contaminante_sufijo):
    cont_str = contaminante_sufijo.lower().replace(",", "").replace(".", "")
    if cont_str.startswith('so2'):
        return "output_so2_text"
    return f"output_{cont_str}_text"

def procesar_fechas_dataframe(df):
    if 'Fecha' in df.columns:
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
        print(f"El contaminante {CONTAMINANTE} no posee norma de percentil diario. Omitiendo script.")
        return
        
    if cont_key in CONFIGURACION_PERCENTILES_DIARIOS:
        configs = CONFIGURACION_PERCENTILES_DIARIOS[cont_key]
    else:
        configs = CONFIGURACION_PERCENTILES_DIARIOS['default']
        configs[0]['nombre'] = cont_key

    archivos_csv = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    if not archivos_csv:
        print(f"No se encontraron archivos .csv en {INPUT_DIR}.")
        return

    is_o3_co = 'o3' in cont_key or 'ozono' in cont_key or 'co' in cont_key or 'monoxido' in cont_key or 'monóxido' in cont_key

    for config in configs:
        nombre_conf = config['nombre']
        q_target = config['percentil']

        out_dir_chart = obtener_directorio_salida_grafico(nombre_conf)
        out_dir_text = obtener_directorio_salida_texto(nombre_conf)
        os.makedirs(out_dir_chart, exist_ok=True)
        os.makedirs(out_dir_text, exist_ok=True)

        print(f"-> Procesando {nombre_conf.upper()} (Percentil Diario {q_target})...")
        
        # FASE 1: Buscar máximo global entre todas las estaciones para unificar la escala Y
        global_max = 0.0
        
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
                
            is_hourly = 'Hora' in df.columns and df['Hora'].notnull().any()
            df = procesar_fechas_dataframe(df)
            
            if df.empty or 'Datetime' not in df.columns:
                continue
                
            if df[col_objetivo].dtype == object:
                df[col_objetivo] = df[col_objetivo].astype(str).str.replace('"', '').str.replace(',', '.').astype(float)
                
            df_daily = calcular_valor_diario(df, col_objetivo, is_hourly, is_o3_co)
            
            for year in range(AÑO_INICIO, AÑO_FIN + 1):
                df_year = df_daily[df_daily['Fecha'].dt.year == year].copy()
                dias_validos = len(df_year[df_year['valido'] == True])
                min_validos = 274 if is_hourly else 91
                
                if dias_validos >= min_validos:
                    val_perc = calcular_percentil_normativa(df_year[df_year['valido'] == True]['valor_diario'], q_target)
                    if pd.notnull(val_perc) and val_perc > global_max:
                        global_max = val_perc

        # Determinamos límite superior del eje Y
        y_max_plot = global_max
        if NORMA_PRIMARIA is not None:
            y_max_plot = max(y_max_plot, NORMA_PRIMARIA)
        if NORMA_SECUNDARIA is not None:
            y_max_plot = max(y_max_plot, NORMA_SECUNDARIA)
            
        y_max_plot += 10.0
        
        print(f"   [INFO] Límite eje Y fijado en: {y_max_plot:.2f} (Percentil máximo o norma + 10)")

        # FASE 2: Generar gráficos y TXT por estación
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
            is_hourly = 'Hora' in df.columns and df['Hora'].notnull().any()
            df = procesar_fechas_dataframe(df)
            
            if df.empty or 'Datetime' not in df.columns:
                continue
                
            if df[col_objetivo].dtype == object:
                df[col_objetivo] = df[col_objetivo].astype(str).str.replace('"', '').str.replace(',', '.').astype(float)
                
            df_daily = calcular_valor_diario(df, col_objetivo, is_hourly, is_o3_co)
            
            texto_hallazgos = ""
            i_year = 1
            
            data_bars = []
            colors_bars = []
            labels_bars = []
            qaqc_bars = []
            
            for year in range(AÑO_INICIO, AÑO_FIN + 1):
                df_year = df_daily[df_daily['Fecha'].dt.year == year].copy()
                
                texto_hallazgos += f"anio{i_year}={year}\n"
                
                dias_validos = len(df_year[df_year['valido'] == True])
                total_esperados = 365.0 if is_hourly else 121.0
                min_validos = 274 if is_hourly else 91
                
                pct_validos = (dias_validos / total_esperados) * 100.0 if len(df_year) > 0 else 0.0
                es_valido = False
                percentil_val = np.nan
                
                if dias_validos >= min_validos:
                    es_valido = True
                    percentil_val = calcular_percentil_normativa(df_year[df_year['valido'] == True]['valor_diario'], q_target)
                else:
                    if len(df_year) > 0:
                        percentil_val = calcular_percentil_normativa(df_year['valor_diario'], q_target)
                
                if pd.notnull(percentil_val) and len(df_year) > 0:
                    texto_hallazgos += f"validos_anio{i_year}={pct_validos:.1f}\n"
                    texto_hallazgos += f"percentil_diario_anio{i_year}={int(round(percentil_val))}\n"
                else:
                    texto_hallazgos += f"validos_anio{i_year}=0.0\n"
                    texto_hallazgos += f"percentil_diario_anio{i_year}=\n"
                    
                if pd.notnull(percentil_val) and len(df_year) > 0:
                    data_bars.append(percentil_val)
                    labels_bars.append(str(year))
                    qaqc_bars.append((total_esperados, dias_validos, pct_validos))
                    if es_valido:
                        color_base = COLORES_POR_AÑO.get(year, '#555555')
                        colors_bars.append(color_base)
                    else:
                        colors_bars.append('#b0b0b0')
                
                i_year += 1

            if not data_bars:
                continue

            if texto_hallazgos:
                filename_txt = f"{estacion}-{nombre_conf}-percentil_diario-{AÑO_INICIO}-{AÑO_FIN}.txt"
                filepath_txt = os.path.join(out_dir_text, filename_txt)
                with open(filepath_txt, 'w', encoding='utf-8') as f:
                    f.write(texto_hallazgos)
                print(f"   Generado texto: {filepath_txt}")
                    
            fig_width = ANCHO_GRAFICO_PX / DPI_GRAFICO
            fig_height = ALTO_GRAFICO_PX / DPI_GRAFICO
            fig, ax = plt.subplots(figsize=(fig_width, fig_height), dpi=DPI_GRAFICO)
            
            
            bars = ax.bar(labels_bars, data_bars, color=colors_bars, width=0.6, edgecolor='black', linewidth=0.5)
            
            if MOSTRAR_INFO_QAQC:
                y_pos = y_max_plot * 0.02
                for idx, bar in enumerate(bars):
                    color_barra = colors_bars[idx]
                    color_oscuro = oscurecer_color(color_barra, 0.4)
                    tot, val, pct = qaqc_bars[idx]
                    texto_qa = f"tot:{int(tot)}\nval:{int(val)}\n%:{pct:.1f}"
                    ax.text(bar.get_x() + bar.get_width()/2, y_pos, texto_qa, color=color_oscuro, 
                            ha='center', va='bottom', fontsize=6)

            
            xlims = ax.get_xlim()
            if NORMA_PRIMARIA is not None and not nombre_conf.endswith('sec'):
                ax.axhline(y=NORMA_PRIMARIA, color='red', linestyle='-', linewidth=1.5)
                ax.text(xlims[1], NORMA_PRIMARIA, "Valor de la Norma Primaria ", 
                        color='black', fontsize=10, va='bottom', ha='right', fontweight='bold')
            if NORMA_SECUNDARIA is not None and not nombre_conf.endswith('pri'):
                ax.axhline(y=NORMA_SECUNDARIA, color='red', linestyle='--', linewidth=1.5)
                ax.text(xlims[1], NORMA_SECUNDARIA, "Valor de la Norma Secundaria ", 
                        color='black', fontsize=10, va='bottom', ha='right', fontweight='bold')
                        
            ax.set_ylim(0, y_max_plot)
            ax.set_ylabel(UNIDADES, fontsize=11)
            
            titulo_dinamico = FORMATO_TITULO.format(
                contaminante=CONTAMINANTE,
                estacion=estacion.replace("_", " ").title()
            )
            ax.set_title(titulo_dinamico, color=COLOR_TITULO, fontsize=14, pad=15)
            
            ax.grid(axis='y', linestyle=':', color='gray', alpha=0.7)
            ax.set_axisbelow(True)
            
            import matplotlib.patches as mpatches
            legend_patches = []
            for y_label, c_bar in zip(labels_bars, colors_bars):
                if c_bar != '#b0b0b0':
                    patch = mpatches.Patch(facecolor=c_bar, edgecolor='black', linewidth=0.5, label=f'Año {y_label}')
                    legend_patches.append(patch)
            
            if '#b0b0b0' in colors_bars:
                legend_patches.append(mpatches.Patch(facecolor='#b0b0b0', edgecolor='black', linewidth=0.5, label='Datos < 75% (No válido)'))
                
            if legend_patches:
                ax.legend(handles=legend_patches, loc='upper center', bbox_to_anchor=(0.5, -0.09),
                          ncol=min(len(legend_patches), 4), frameon=False, fontsize=10)
                          
            for bar in bars:
                height = bar.get_height()
                if pd.notnull(height) and height > 0:
                    ax.annotate(f'{int(round(height))}',
                                xy=(bar.get_x() + bar.get_width() / 2, height),
                                xytext=(0, 3),  
                                textcoords="offset points",
                                ha='center', va='bottom', fontsize=10, fontweight='bold')

            fig.subplots_adjust(bottom=0.15, top=0.92, left=0.06, right=0.98)
            
            filename_img = f"{estacion}-{nombre_conf}-percentil_diario-{AÑO_INICIO}-{AÑO_FIN}.png"
            filepath_img = os.path.join(out_dir_chart, filename_img)
            plt.savefig(filepath_img, dpi=DPI_GRAFICO)
            print(f"   Generado gráfico: {filepath_img}")
            plt.close(fig)

if __name__ == "__main__":
    main()
