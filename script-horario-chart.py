import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os
import re
import glob

# Parámetros configurables
INPUT_DIR = "input"
CONTAMINANTE = "MP10"  
AÑO_INICIO = 2023
AÑO_FIN = 2025
UNIDADES = "µg/m³N"
FORMATO_TITULO = "Concentraciones horarias de {contaminante} - Estación {estacion}"
COLOR_TITULO = "white"  # 'white' para ocultar, 'black' para mostrar
NORMA_PRIMARIA = None  
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
# ==============================================================================

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

def obtener_directorio_salida_grafico(contaminante):
    cont_str = contaminante.lower().replace(",", "").replace(".", "")
    return f"output_{cont_str}_chart"

def obtener_directorio_salida_texto(contaminante):
    cont_str = contaminante.lower().replace(",", "").replace(".", "")
    return f"output_{cont_str}_text"

def procesar_fechas_dataframe(df):
    if 'Fecha' in df.columns:
        df['Fecha'] = pd.to_datetime(df['Fecha'], format='%d/%m/%Y', errors='coerce')
        if 'Hora' in df.columns and df['Hora'].notnull().any():
            df['Hora'] = pd.to_numeric(df['Hora'], errors='coerce').fillna(0).astype(int)
            df['Datetime'] = df['Fecha'] + pd.to_timedelta(df['Hora'], unit='h')
        else:
            df['Datetime'] = df['Fecha']
    else:
        col_anio = next((c for c in df.columns if c.lower() in ['año', 'ano', 'ao', 'aã±o']), None)
        col_mes = next((c for c in df.columns if c.lower() == 'mes'), None)
        
        if col_anio and col_mes:
            fechas_str = df[col_anio].astype(str).str.replace('.0', '', regex=False) + '-' + df[col_mes].astype(str).str.zfill(2) + '-01'
            df['Fecha'] = pd.to_datetime(fechas_str, format='%Y-%m-%d', errors='coerce')
            df['Datetime'] = df['Fecha']
        else:
            return pd.DataFrame()
    return df

def main():
    print(f"-> Analizando todos los archivos para {CONTAMINANTE} entre {AÑO_INICIO} y {AÑO_FIN}...")
    global_max = 0.0
    estacion_max = "Ninguna"
    fecha_max_str = "Desconocida"
    
    archivos_csv = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    
    # FASE 1: Buscar máximo global solo en estaciones HORARIAS
    for filepath in archivos_csv:
        try:
            df = pd.read_csv(filepath, sep=',', encoding='utf-8', on_bad_lines='skip')
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, sep=',', encoding='latin1', on_bad_lines='skip')
            
        cont_norm = str(CONTAMINANTE).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()
        col_objetivo = next((c for c in df.columns if cont_norm in str(c).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()), None)
        if not col_objetivo:
            continue
            
        # Descartar archivos que no tienen mediciones horarias
        if 'Hora' not in df.columns or not df['Hora'].notnull().any():
            continue
            
        df = procesar_fechas_dataframe(df)
        if df.empty:
            continue
            
        df = df[(df['Fecha'].dt.year >= AÑO_INICIO) & (df['Fecha'].dt.year <= AÑO_FIN)]
        
        if not df.empty:
            if df[col_objetivo].dtype == object:
                df[col_objetivo] = df[col_objetivo].astype(str).str.replace('"', '').str.replace(',', '.').astype(float)
                
            max_val = df[col_objetivo].max()
            if pd.notnull(max_val) and max_val > global_max:
                global_max = max_val
                
                idx_max = df[col_objetivo].idxmax()
                estacion_max = extraer_nombre_estacion(filepath)
                dt_max = df.loc[idx_max, 'Datetime']
                fecha_max_str = dt_max.strftime('%d/%m/%Y %H:%M') if pd.notnull(dt_max) else "Desconocida"

    y_max_plot = global_max
    if NORMA_PRIMARIA is not None:
        y_max_plot = max(y_max_plot, NORMA_PRIMARIA)
    if NORMA_SECUNDARIA is not None:
        y_max_plot = max(y_max_plot, NORMA_SECUNDARIA)
        
    print(f"   [INFO] Valor máximo real detectado: {global_max:.2f} (Estación: '{estacion_max}', Fecha/Hora: {fecha_max_str})")
    print(f"   [INFO] Escala del eje Y fijada en: {y_max_plot:.2f}\n")

    # FASE 2: Generar gráficos y extraer variables de texto (Exclusivo estaciones HORARIAS)
    out_dir_chart = obtener_directorio_salida_grafico(CONTAMINANTE)
    out_dir_text = obtener_directorio_salida_texto(CONTAMINANTE)
    os.makedirs(out_dir_chart, exist_ok=True)
    os.makedirs(out_dir_text, exist_ok=True)
    
    cont_str = CONTAMINANTE.lower().replace(",", "").replace(".", "")

    for filepath in archivos_csv:
        try:
            df = pd.read_csv(filepath, sep=',', encoding='utf-8', on_bad_lines='skip')
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, sep=',', encoding='latin1', on_bad_lines='skip')
        
        cont_norm = str(CONTAMINANTE).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()
        col_objetivo = next((c for c in df.columns if cont_norm in str(c).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()), None)
        if not col_objetivo:
            continue
            
        if 'Hora' not in df.columns or not df['Hora'].notnull().any():
            continue
            
        estacion = extraer_nombre_estacion(filepath)
        df = procesar_fechas_dataframe(df)
        if df.empty:
            continue
            
        if df[col_objetivo].dtype == object:
            df[col_objetivo] = df[col_objetivo].astype(str).str.replace('"', '').str.replace(',', '.').astype(float)
            
        fig, ax = plt.subplots(figsize=(ANCHO_GRAFICO_PX / DPI_GRAFICO, ALTO_GRAFICO_PX / DPI_GRAFICO))
        datos_ploteados = False
        
        texto_hallazgos = ""
        i_year = 1
        
        for year in range(AÑO_INICIO, AÑO_FIN + 1):
            df_year = df[df['Fecha'].dt.year == year].copy()
            
            texto_hallazgos += f"anio{i_year}={year}\n"
            
            df_year_valid = df_year.dropna(subset=['Datetime', col_objetivo])
            
            if not df_year_valid.empty:
                idx_max_year = df_year_valid[col_objetivo].idxmax()
                row_max = df_year_valid.loc[idx_max_year]
                
                fecha_str = row_max['Fecha'].strftime('%Y-%m-%d') if pd.notnull(row_max['Fecha']) else ""
                hora_val = int(row_max['Hora']) if 'Hora' in row_max and pd.notnull(row_max['Hora']) else 0
                hora_str = f"{hora_val:02d}:00"
                valor_max = row_max[col_objetivo]
                
                texto_hallazgos += f"fecha_max_hora_anio{i_year}={fecha_str}\n"
                texto_hallazgos += f"hora_max_hora_anio{i_year}={hora_str}\n"
                texto_hallazgos += f"valor_max_hora_anio{i_year}={valor_max:.2f}\n"
            else:
                texto_hallazgos += f"fecha_max_hora_anio{i_year}=\n"
                texto_hallazgos += f"hora_max_hora_anio{i_year}=\n"
                texto_hallazgos += f"valor_max_hora_anio{i_year}=\n"
                
            i_year += 1
            
            df_year = df_year.drop_duplicates(subset=['Datetime']).sort_values('Datetime')
            
            bar_width = 1.0  
            if len(df_year) > 1:
                modo_freq = df_year['Datetime'].diff().mode()
                if not modo_freq.empty:
                    freq = modo_freq.iloc[0]
                    if pd.notnull(freq) and freq > pd.Timedelta(0):
                        bar_width = freq.total_seconds() / (24 * 3600)
            
            width_plot = bar_width
            color_bar = COLORES_POR_AÑO.get(year, '#555555')
            
            ax.bar(df_year['Datetime'], df_year[col_objetivo], color=color_bar, 
                   width=width_plot, label=str(year), align='center')
            datos_ploteados = True
            
        if not datos_ploteados:
            plt.close(fig)
            continue
            
        if texto_hallazgos:
            filename_txt = f"{estacion}-{cont_str}-horario-{AÑO_INICIO}-{AÑO_FIN}.txt"
            filepath_txt = os.path.join(out_dir_text, filename_txt)
            with open(filepath_txt, 'w', encoding='utf-8') as f:
                f.write(texto_hallazgos.strip() + "\n")
            print(f"   Generado texto: {filepath_txt}")
            
        ax.set_ylim(0, y_max_plot + 10)
        ax.set_xlim(pd.Timestamp(AÑO_INICIO, 1, 1), pd.Timestamp(AÑO_FIN, 12, 31))
        
        xlims = ax.get_xlim()
        if NORMA_PRIMARIA is not None:
            ax.axhline(y=NORMA_PRIMARIA, color='red', linestyle='-', linewidth=1.5)
            ax.text(xlims[1], NORMA_PRIMARIA, "Valor de la Norma Primaria ", 
                    color='black', fontsize=10, va='bottom', ha='right', fontweight='bold')
                    
        if NORMA_SECUNDARIA is not None:
            ax.axhline(y=NORMA_SECUNDARIA, color='red', linestyle='--', linewidth=1.5)
            ax.text(xlims[1], NORMA_SECUNDARIA, "Valor de la Norma Secundaria ", 
                    color='black', fontsize=10, va='bottom', ha='right', fontweight='bold')

        major_locator = mdates.DayLocator(bymonthday=[1])
        minor_locator = mdates.DayLocator(bymonthday=[15])
        ax.xaxis.set_major_locator(major_locator)
        ax.xaxis.set_minor_locator(minor_locator)
        
        meses_es = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
        
        def format_date(x, pos=None):
            dt = mdates.num2date(x)
            return f"{meses_es[dt.month - 1]}-{dt.day:02d}"
            
        formatter = plt.FuncFormatter(format_date)
        ax.xaxis.set_major_formatter(formatter)
        ax.xaxis.set_minor_formatter(plt.NullFormatter())
        
        ax.tick_params(axis='x', which='both', labelsize=9)
        plt.setp(ax.get_xticklabels(which='major'), rotation=45, ha='right')
        
        ax.set_ylabel(UNIDADES, fontsize=11)
        
        titulo_dinamico = FORMATO_TITULO.format(
            contaminante=CONTAMINANTE,
            estacion=estacion.replace("_", " ").title()
        )
        ax.set_title(titulo_dinamico, color=COLOR_TITULO, fontsize=14, pad=15)
        
        ax.set_axisbelow(True)
        ax.grid(True, which='major', axis='both', linestyle=':', alpha=0.7)
        
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.20), 
                  ncol=AÑO_FIN - AÑO_INICIO + 1, frameon=False)
        
        filename_img = f"{estacion}-{cont_str}-horario-{AÑO_INICIO}-{AÑO_FIN}.png"
        filepath_img = os.path.join(out_dir_chart, filename_img)
        fig.subplots_adjust(bottom=0.22, top=0.92, left=0.06, right=0.98)
        plt.savefig(filepath_img, dpi=DPI_GRAFICO)
        plt.close(fig)
        
        print(f"   Generado gráfico: {filepath_img}")

if __name__ == "__main__":
    main()
    print("\n¡Proceso completado con éxito!")