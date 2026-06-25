import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
import os
import re
import glob

# ==============================================================================
# 1. PARÁMETROS CONFIGURABLES
# ==============================================================================
INPUT_DIR = "input"
CONTAMINANTE = "MP10"  # Para Material Particulado Sedimentable usar "MPS"
AÑO_INICIO = 2023
AÑO_FIN = 2025
UNIDADES = "µg/m³N"  # Para MPS podría ser "mg/m²-dia"
FORMATO_TITULO = "Concentraciones anuales de {contaminante} - Estación {estacion}"
COLOR_TITULO = "white"  # 'white' para ocultar, 'black' para mostrar
NORMA_PRIMARIA = 50.0  # Norma Anual MP10 (ejemplo), editable
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
    is_native_monthly = False
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
            is_native_monthly = True
        else:
            return pd.DataFrame(), False
            
    return df, is_native_monthly

def calcular_valor_diario(df, col_objetivo, is_hourly, is_o3_co):
    if not is_hourly:
        df_daily = df.copy()
        df_daily['Datetime'] = pd.to_datetime(df_daily['Fecha'].dt.date)
        df_daily['valor_diario'] = df_daily[col_objetivo]
        df_daily['valido'] = True
        df_daily = df_daily.drop_duplicates(subset=['Datetime'], keep='last')
        return df_daily[['Datetime', 'valor_diario', 'Fecha', 'valido']].dropna(subset=['valor_diario'])

    df = df.dropna(subset=['Datetime', col_objetivo])
    df = df.sort_values('Datetime')
    df = df.drop_duplicates(subset=['Datetime'])
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

def calcular_valor_mensual(df, col_objetivo, is_hourly, is_o3_co, is_native_monthly):
    if is_native_monthly:
        df_month = df.copy()
        df_month['Datetime'] = pd.to_datetime(df_month['Fecha'].dt.to_period('M').dt.to_timestamp())
        df_month['valor_mensual'] = df_month[col_objetivo]
        df_month['valido'] = True
        df_month['days_in_month'] = df_month['Datetime'].dt.daysinmonth
        df_month['porcentaje_validos'] = 100.0
        df_month = df_month.drop_duplicates(subset=['Datetime'], keep='last')
        return df_month[['Datetime', 'valor_mensual', 'valido', 'days_in_month', 'porcentaje_validos']].dropna(subset=['valor_mensual'])

    df_daily = calcular_valor_diario(df, col_objetivo, is_hourly, is_o3_co)
    if df_daily.empty:
        return pd.DataFrame()
        
    df_daily['Mes_Inicio'] = df_daily['Fecha'].dt.to_period('M').dt.to_timestamp()
    df_daily['days_in_month'] = df_daily['Mes_Inicio'].dt.daysinmonth
    
    def agg_func(x):
        valid_days = x[x['valido']]
        if len(valid_days) == 0:
            mean_val = x['valor_diario'].mean()
            count_valid = 0
        else:
            mean_val = valid_days['valor_diario'].mean()
            count_valid = len(valid_days)
        return pd.Series({'valor_mensual': mean_val, 'valid_count': count_valid})
        
    month_agg = df_daily.groupby(['Mes_Inicio', 'days_in_month']).apply(agg_func, include_groups=False).reset_index()
    
    if is_hourly:
        month_agg['valido'] = month_agg['valid_count'] >= (0.75 * month_agg['days_in_month'])
        month_agg['porcentaje_validos'] = (month_agg['valid_count'] / month_agg['days_in_month']) * 100.0
    else:
        month_agg['valido'] = month_agg['valid_count'] >= 7
        month_agg['porcentaje_validos'] = (month_agg['valid_count'] / 10.0) * 100.0
        month_agg['porcentaje_validos'] = month_agg['porcentaje_validos'].clip(upper=100.0)
        
    month_agg = month_agg.rename(columns={'Mes_Inicio': 'Datetime'})
    return month_agg[['Datetime', 'valor_mensual', 'valido', 'days_in_month', 'porcentaje_validos']].dropna(subset=['valor_mensual'])

def calcular_valor_anual(df_month):
    if df_month.empty:
        return pd.DataFrame(columns=['Year', 'valor_anual', 'meses_validos', 'valido'])
        
    df_month['Year'] = df_month['Datetime'].dt.year
    
    def agg_year(x):
        valid_months = x[x['valido']]
        if len(valid_months) == 0:
            mean_val = x['valor_mensual'].mean()
            count_valid = 0
        else:
            mean_val = valid_months['valor_mensual'].mean()
            count_valid = len(valid_months)
            
        return pd.Series({
            'valor_anual': mean_val, 
            'meses_validos': count_valid
        })
        
    year_agg = df_month.groupby('Year').apply(agg_year, include_groups=False).reset_index()
    
    # Validez del año: al menos 9 meses válidos (75% de 12)
    year_agg['valido'] = year_agg['meses_validos'] >= 9
    return year_agg.dropna(subset=['valor_anual'])


def main():
    print(f"-> Analizando todos los archivos para generar promedios anuales de {CONTAMINANTE} ({AÑO_INICIO}-{AÑO_FIN})...")
    
    contaminante_lower = CONTAMINANTE.lower()
    is_o3_co = 'o3' in contaminante_lower or 'ozono' in contaminante_lower or 'co' in contaminante_lower or 'monoxido' in contaminante_lower or 'monóxido' in contaminante_lower
        
    global_max = 0.0
    global_max_all = 0.0
    estacion_max = "Ninguna"
    fecha_max_str = "Desconocida"
    
    archivos_csv = glob.glob(os.path.join(INPUT_DIR, "*.csv"))
    
    # FASE 1: Buscar máximo global
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
            
        df, is_native_monthly = procesar_fechas_dataframe(df)
        if df.empty:
            continue
            
        if df[col_objetivo].dtype == object:
            df[col_objetivo] = df[col_objetivo].astype(str).str.replace('"', '').str.replace(',', '.').astype(float)
                
        df_month = calcular_valor_mensual(df, col_objetivo, is_hourly, is_o3_co, is_native_monthly)
        df_year = calcular_valor_anual(df_month)
        if df_year.empty:
            continue
            
        df_year = df_year[(df_year['Year'] >= AÑO_INICIO) & (df_year['Year'] <= AÑO_FIN)]
        
        if not df_year.empty:
            max_all = df_year['valor_anual'].max()
            if pd.notnull(max_all) and max_all > global_max_all:
                global_max_all = max_all
                
            df_valid = df_year[df_year['valido']]
            if not df_valid.empty:
                max_val = df_valid['valor_anual'].max()
                if pd.notnull(max_val) and max_val > global_max:
                    global_max = max_val
                    idx_max = df_valid['valor_anual'].idxmax()
                    estacion_max = extraer_nombre_estacion(filepath)
                    year_max = df_valid.loc[idx_max, 'Year']
                    fecha_max_str = str(int(year_max))

    y_max_plot = max(global_max, global_max_all)
    if NORMA_PRIMARIA is not None:
        y_max_plot = max(y_max_plot, NORMA_PRIMARIA)
    if NORMA_SECUNDARIA is not None:
        y_max_plot = max(y_max_plot, NORMA_SECUNDARIA)
        
    print(f"   [INFO] Valor máximo anual detectado: {global_max:.2f} (Estación: '{estacion_max}', Año: {fecha_max_str})")
    print(f"   [INFO] Escala del eje Y fijada en: {y_max_plot:.2f}\n")

    # FASE 2: Generar gráficos y extraer variables de texto
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
        df, is_native_monthly = procesar_fechas_dataframe(df)
        if df.empty:
            continue
            
        if df[col_objetivo].dtype == object:
            df[col_objetivo] = df[col_objetivo].astype(str).str.replace('"', '').str.replace(',', '.').astype(float)
            
        df_month = calcular_valor_mensual(df, col_objetivo, is_hourly, is_o3_co, is_native_monthly)
        df_year = calcular_valor_anual(df_month)
        if df_year.empty:
            continue
            
        fig, ax = plt.subplots(figsize=(10, 6))
        datos_ploteados = False
        
        texto_hallazgos = ""
        i_year = 1
        
        years_plot = []
        vals_plot = []
        colors_plot = []
        
        for year in range(AÑO_INICIO, AÑO_FIN + 1):
            df_y = df_year[df_year['Year'] == year].copy()
            
            texto_hallazgos += f"anio{i_year}={year}\n"
            
            if not df_y.empty and df_y.iloc[0]['valido']:
                valor_anual = df_y.iloc[0]['valor_anual']
                meses_validos = int(df_y.iloc[0]['meses_validos'])
                porcentaje_meses = (meses_validos / 12.0) * 100.0
                texto_hallazgos += f"promedio_anual_anio{i_year}={int(round(valor_anual))}\n"
                texto_hallazgos += f"meses_validos_anio{i_year}={meses_validos}\n"
                texto_hallazgos += f"validos_anio{i_year}={porcentaje_meses:.1f}\n"
            else:
                texto_hallazgos += f"promedio_anual_anio{i_year}=\n"
                texto_hallazgos += f"meses_validos_anio{i_year}=\n"
                texto_hallazgos += f"validos_anio{i_year}=\n"
                
            i_year += 1
            
            if df_y.empty:
                continue
                
            # Recolectar datos para gráfico
            valor_anual_plot = df_y.iloc[0]['valor_anual']
            valido_plot = df_y.iloc[0]['valido']
            years_plot.append(year)
            vals_plot.append(valor_anual_plot)
            color_bar_base = COLORES_POR_AÑO.get(year, '#555555')
            colors_plot.append(color_bar_base if valido_plot else '#b0b0b0')
            datos_ploteados = True
            
        if not datos_ploteados:
            plt.close(fig)
            continue
            
        if texto_hallazgos:
            filename_txt = f"{estacion}-{cont_str}-anual-{AÑO_INICIO}-{AÑO_FIN}.txt"
            filepath_txt = os.path.join(out_dir_text, filename_txt)
            with open(filepath_txt, 'w', encoding='utf-8') as f:
                f.write(texto_hallazgos.strip() + "\n")
            print(f"   Generado texto: {filepath_txt}")
            
        ax.bar(years_plot, vals_plot, color=colors_plot, width=0.8, align='center', edgecolor='black', linewidth=0.5)
            
        ax.set_ylim(0, y_max_plot * 1.05 + 10)
        
        # Establecer el límite en X dando un margen a las barras
        ax.set_xlim(AÑO_INICIO - 0.6, AÑO_FIN + 0.6)
        
        xlims = ax.get_xlim()
        if NORMA_PRIMARIA is not None:
            ax.axhline(y=NORMA_PRIMARIA, color='red', linestyle='-', linewidth=1.5)
            ax.text(xlims[1], NORMA_PRIMARIA, "Valor de la Norma Primaria ", 
                    color='black', fontsize=10, va='bottom', ha='right', fontweight='bold')
                    
        if NORMA_SECUNDARIA is not None:
            ax.axhline(y=NORMA_SECUNDARIA, color='red', linestyle='--', linewidth=1.5)
            ax.text(xlims[1], NORMA_SECUNDARIA, "Valor de la Norma Secundaria ", 
                    color='black', fontsize=10, va='bottom', ha='right', fontweight='bold')

        # Eje X: mostrar solo años enteros
        ax.xaxis.set_major_locator(ticker.MultipleLocator(1))
        ax.xaxis.set_major_formatter(ticker.FormatStrFormatter('%d'))
        
        ax.tick_params(axis='x', labelsize=10)
        
        ax.set_ylabel(UNIDADES, fontsize=11)
        
        titulo_dinamico = FORMATO_TITULO.format(
            contaminante=CONTAMINANTE,
            estacion=estacion.replace("_", " ").title()
        )
        ax.set_title(titulo_dinamico, color=COLOR_TITULO, fontsize=14, pad=15)
        
        ax.set_axisbelow(True)
        ax.grid(True, axis='y', linestyle=':', alpha=0.7) 
        
        handles = []
        for y in years_plot:
            color = COLORES_POR_AÑO.get(y, '#555555')
            # Evitar leyenda duplicada por año
            if not any(h.get_label() == str(y) for h in handles):
                handles.append(mpatches.Patch(color=color, label=str(y)))
            
        if '#b0b0b0' in colors_plot:
            handles.append(mpatches.Patch(color='#b0b0b0', label='Datos < 75% (No válido)'))
            
        ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.15), 
                  ncol=len(handles), frameon=False)
        
        filename_img = f"{estacion}-{cont_str}-anual-{AÑO_INICIO}-{AÑO_FIN}.png"
        filepath_img = os.path.join(out_dir_chart, filename_img)
        plt.savefig(filepath_img, dpi=300, bbox_inches='tight')
        plt.close(fig)
        
        print(f"   Generado gráfico: {filepath_img}")

if __name__ == "__main__":
    main()
    print("\n¡Proceso completado con éxito!")
