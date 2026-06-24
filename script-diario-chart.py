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
FORMATO_TITULO = "Concentraciones diarias de {contaminante} - Estación {estacion}"
COLOR_TITULO = "white"  # 'white' para ocultar, 'black' para mostrar
NORMA_PRIMARIA = 130.0  # Asumido por defecto para la revisión, editable
NORMA_SECUNDARIA = None 

# Mismo color por año 
COLORES_POR_AÑO = {
    2022: '#8c564b',
    2023: '#1f77b4', # Azul
    2024: '#ff7f0e', # Naranja
    2025: '#2ca02c', # Verde
    2026: '#d62728', # Rojo
    2027: '#9467bd', # Morado
}

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

def calcular_valor_diario(df, col_objetivo, is_hourly, is_o3_co):
    """
    Consolida las métricas para convertirlas en un valor diario validado.
    Considera el 75% de suficiencia de datos normativo.
    """
    if not is_hourly:
        # La estación ya reporta de forma diaria. Usamos los datos tal cual.
        df_daily = df.copy()
        df_daily['Datetime'] = pd.to_datetime(df_daily['Fecha'].dt.date)
        df_daily['valor_diario'] = df_daily[col_objetivo]
        df_daily = df_daily.drop_duplicates(subset=['Datetime'], keep='last')
        return df_daily[['Datetime', 'valor_diario', 'Fecha']].dropna()

    # Si es horaria, procedemos a calcular los promedios normativos
    df = df.dropna(subset=['Datetime', col_objetivo])
    df = df.sort_values('Datetime')
    df = df.drop_duplicates(subset=['Datetime'])
    df_idx = df.set_index('Datetime')

    if is_o3_co:
        # Ozono o CO: Máximo del promedio móvil de 8 horas
        # rolling('8h') busca temporalmente 8 horas hacia atrás. Mínimo 6 horas válidas (75%).
        df_idx['movil_8h'] = df_idx[col_objetivo].rolling('8h', min_periods=6).mean()
        daily_series = df_idx['movil_8h'].resample('D').max()
    else:
        # Resto de contaminantes: Promedio aritmético de 24 horas.
        # Se requieren al menos 18 horas válidas (75% de 24 hrs).
        daily_series = df_idx[col_objetivo].resample('D').apply(lambda x: x.mean() if x.count() >= 18 else np.nan)

    df_daily = daily_series.reset_index()
    df_daily = df_daily.rename(columns={daily_series.name: 'valor_diario'})
    df_daily['Fecha'] = pd.to_datetime(df_daily['Datetime'].dt.date)
    return df_daily.dropna(subset=['valor_diario'])


def main():
    print(f"-> Analizando todos los archivos diarios para {CONTAMINANTE} entre {AÑO_INICIO} y {AÑO_FIN}...")
    
    # Determinar si es O3 o CO para aplicar lógica normativa de 8 horas
    contaminante_lower = CONTAMINANTE.lower()
    is_o3_co = 'o3' in contaminante_lower or 'ozono' in contaminante_lower or 'co' in contaminante_lower or 'monoxido' in contaminante_lower or 'monóxido' in contaminante_lower
    if is_o3_co:
        print("   [NORMATIVA] Contaminante detectado como O3/CO. Se aplicará máximo diario de media móvil de 8h (min 6h).")
    else:
        print("   [NORMATIVA] Se aplicará promedio aritmético diario (min 18h válidas).")
        
    global_max = 0.0
    estacion_max = "Ninguna"
    fecha_max_str = "Desconocida"
    
    archivos_csv = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    
    # FASE 1: Buscar máximo global considerando ambos tipos de estación
    for filepath in archivos_csv:
        try:
            df = pd.read_csv(filepath, sep=',', encoding='utf-8', on_bad_lines='skip')
        except UnicodeDecodeError:
            df = pd.read_csv(filepath, sep=',', encoding='latin1', on_bad_lines='skip')
            
        cont_norm = str(CONTAMINANTE).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()
        col_objetivo = next((c for c in df.columns if cont_norm in str(c).translate(str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")).lower()), None)
        if not col_objetivo:
            continue
            
        is_hourly = 'Hora' in df.columns and df['Hora'].notnull().any()
            
        df = procesar_fechas_dataframe(df)
        if df.empty:
            continue
            
        if df[col_objetivo].dtype == object:
            df[col_objetivo] = df[col_objetivo].astype(str).str.replace('"', '').str.replace(',', '.').astype(float)
                
        df_daily = calcular_valor_diario(df, col_objetivo, is_hourly, is_o3_co)
        df_daily = df_daily[(df_daily['Fecha'].dt.year >= AÑO_INICIO) & (df_daily['Fecha'].dt.year <= AÑO_FIN)]
        
        if not df_daily.empty:
            max_val = df_daily['valor_diario'].max()
            if pd.notnull(max_val) and max_val > global_max:
                global_max = max_val
                
                idx_max = df_daily['valor_diario'].idxmax()
                estacion_max = extraer_nombre_estacion(filepath)
                dt_max = df_daily.loc[idx_max, 'Datetime']
                fecha_max_str = dt_max.strftime('%d/%m/%Y') if pd.notnull(dt_max) else "Desconocida"

    y_max_plot = global_max
    if NORMA_PRIMARIA is not None:
        y_max_plot = max(y_max_plot, NORMA_PRIMARIA)
    if NORMA_SECUNDARIA is not None:
        y_max_plot = max(y_max_plot, NORMA_SECUNDARIA)
        
    print(f"   [INFO] Valor máximo diario detectado: {global_max:.2f} (Estación: '{estacion_max}', Fecha: {fecha_max_str})")
    print(f"   [INFO] Escala del eje Y fijada en: {y_max_plot:.2f}\n")

    # FASE 2: Generar gráficos y extraer variables de texto (Ambos tipos de estación)
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
            
        is_hourly = 'Hora' in df.columns and df['Hora'].notnull().any()
            
        estacion = extraer_nombre_estacion(filepath)
        df = procesar_fechas_dataframe(df)
        if df.empty:
            continue
            
        if df[col_objetivo].dtype == object:
            df[col_objetivo] = df[col_objetivo].astype(str).str.replace('"', '').str.replace(',', '.astype(float)')
            
        df_daily = calcular_valor_diario(df, col_objetivo, is_hourly, is_o3_co)
            
        fig, ax = plt.subplots(figsize=(16, 6))
        datos_ploteados = False
        
        texto_hallazgos = ""
        i_year = 1
        
        for year in range(AÑO_INICIO, AÑO_FIN + 1):
            df_year = df_daily[df_daily['Fecha'].dt.year == year].copy()
            
            if df_year.empty:
                continue
                
            idx_max_year = df_year['valor_diario'].idxmax()
            row_max = df_year.loc[idx_max_year]
            
            fecha_str = row_max['Datetime'].strftime('%d/%m/%Y')
            valor_max = row_max['valor_diario']
            
            texto_hallazgos += f"anio{i_year}={year}\n"
            texto_hallazgos += f"fecha_max_dia_anio{i_year}={fecha_str}\n"
            # Redondeado a número entero según instrucción
            texto_hallazgos += f"valor_max_dia_anio{i_year}={int(round(valor_max))}\n"
            i_year += 1
                
            df_year = df_year.drop_duplicates(subset=['Datetime']).sort_values('Datetime')
            
            # Al ser un valor representativo diario, el ancho de barra es exactamente 1 día (1.0)
            width_plot = 1.0
            color_bar = COLORES_POR_AÑO.get(year, '#555555')
            
            ax.bar(df_year['Datetime'], df_year['valor_diario'], color=color_bar, 
                   width=width_plot, label=str(year), align='center')
            datos_ploteados = True
            
        if not datos_ploteados:
            plt.close(fig)
            continue
            
        if texto_hallazgos:
            # Archivos txt etiquetados como "dia"
            filename_txt = f"{estacion}-{cont_str}-dia-{AÑO_INICIO}-{AÑO_FIN}.txt"
            filepath_txt = os.path.join(out_dir_text, filename_txt)
            with open(filepath_txt, 'w', encoding='utf-8') as f:
                f.write(texto_hallazgos.strip() + "\n")
            print(f"   Generado texto: {filepath_txt}")
            
        ax.set_ylim(0, y_max_plot * 1.1)
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
        ax.xaxis.set_minor_formatter(formatter)
        
        ax.tick_params(axis='x', which='both', labelsize=9)
        plt.setp(ax.get_xticklabels(which='both'), rotation=45, ha='right')
        
        ax.set_ylabel(UNIDADES, fontsize=11)
        
        titulo_dinamico = FORMATO_TITULO.format(
            contaminante=CONTAMINANTE,
            estacion=estacion.replace("_", " ").title()
        )
        ax.set_title(titulo_dinamico, color=COLOR_TITULO, fontsize=14, pad=15)
        
        ax.set_axisbelow(True)
        ax.grid(True, which='major', axis='both', linestyle=':', alpha=0.7)
        
        ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), 
                  ncol=AÑO_FIN - AÑO_INICIO + 1, frameon=False)
        
        # Archivos de imagen etiquetados como "dia"
        filename_img = f"{estacion}-{cont_str}-dia-{AÑO_INICIO}-{AÑO_FIN}.png"
        filepath_img = os.path.join(out_dir_chart, filename_img)
        plt.savefig(filepath_img, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        print(f"   Generado gráfico: {filepath_img}")

if __name__ == "__main__":
    main()
    print("\n¡Proceso completado con éxito!")
