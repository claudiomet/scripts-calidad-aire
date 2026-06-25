import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.patches as mpatches
import matplotlib.ticker as ticker
import os
import re

MOSTRAR_INFO_QAQC = True

def oscurecer_color(hex_color, factor=0.5):
    import matplotlib.colors as mcolors
    try:
        rgb = mcolors.to_rgb(hex_color)
        dark_rgb = [max(0, c * factor) for c in rgb]
        return mcolors.to_hex(dark_rgb)
    except:
        return '#000000'

import glob

# ==============================================================================
# 1. PARÁMETROS CONFIGURABLES
# ==============================================================================
INPUT_DIR = "input"
CONTAMINANTE = "SO2"  # Editable, ej: "MP10", "MP2.5", "O3", "SO2", "CO", "NO2"
AÑO_INICIO = 2023
AÑO_FIN = 2025
UNIDADES = "µg/m³N"  # Para MPS podría ser "mg/m²-dia"
FORMATO_TITULO = "Concentraciones anuales de {contaminante} - Estación {estacion}"
COLOR_TITULO = "white"  # 'white' para ocultar, 'black' para mostrar
NORMA_PRIMARIA = 50.0  # Norma Anual MP10 (ejemplo), editable
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
        month_agg['valido'] = month_agg['valid_count'] >= 15
        month_agg['porcentaje_validos'] = (month_agg['valid_count'] / month_agg['days_in_month']) * 100.0
    else:
        month_agg['valido'] = month_agg['valid_count'] >= 5
        month_agg['porcentaje_validos'] = (month_agg['valid_count'] / 10.0) * 100.0
        month_agg['porcentaje_validos'] = month_agg['porcentaje_validos'].clip(upper=100.0)
        
    month_agg = month_agg.rename(columns={'Mes_Inicio': 'Datetime'})
    return month_agg[['Datetime', 'valor_mensual', 'valido', 'days_in_month', 'porcentaje_validos']].dropna(subset=['valor_mensual'])

def calcular_valor_anual(df_month, df=None, col_objetivo=None, is_hourly=False):
    if df_month.empty:
        return pd.DataFrame(columns=['Year', 'valor_anual', 'meses_validos', 'valido', 'porcentaje_validos'])
        
    df_month['Year'] = df_month['Datetime'].dt.year
    df_month['Month'] = df_month['Datetime'].dt.month
    
    contaminante_eval = CONTAMINANTE.lower()
    is_no2 = 'no2' in contaminante_eval or 'nitrogeno' in contaminante_eval or 'nitrógeno' in contaminante_eval
    is_as = 'as' == contaminante_eval or 'arsenico' in contaminante_eval or 'arsénico' in contaminante_eval
    is_mp = 'mp10' in contaminante_eval or 'mp2,5' in contaminante_eval or 'mp2.5' in contaminante_eval
    is_pb = 'pb' == contaminante_eval or 'plomo' in contaminante_eval
    is_cov = 'cov' in contaminante_eval or 'benceno' in contaminante_eval
    
    requires_11_months = is_no2 or is_as or is_mp or is_cov
    
    is_so2_primario = ('so2' in contaminante_eval or 'azufre' in contaminante_eval) and 'sec' not in contaminante_eval

    if requires_11_months:
        years = sorted(df_month['Year'].unique())
        resultados = []
        
        for y in years:
            df_y = df_month[df_month['Year'] == y]
            valid_months_df = df_y[df_y['valido']]
            meses_validos_count = len(valid_months_df)
            
            if meses_validos_count == 0:
                mean_val = df_y['valor_mensual'].mean() if len(df_y) > 0 else np.nan
                resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': 0, 'valido': False, 'total_esperado': 12, 'porcentaje_validos': 0.0})
                continue
                
            if meses_validos_count >= 11:
                # Válido sin imputar
                mean_val = valid_months_df['valor_mensual'].mean()
                resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': meses_validos_count, 'valido': True, 'total_esperado': 12, 'porcentaje_validos': (meses_validos_count/12.0)*100})
            elif meses_validos_count <= 8:
                # Inválido
                mean_val = valid_months_df['valor_mensual'].mean()
                resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': meses_validos_count, 'valido': False, 'total_esperado': 12, 'porcentaje_validos': (meses_validos_count/12.0)*100})
            else:
                # 9 o 10 meses válidos: necesitamos imputar hasta llegar a 11
                meses_presentes = set(valid_months_df['Month'])
                meses_faltantes = set(range(1, 13)) - meses_presentes
                
                calidos = {1, 2, 3, 10, 11, 12}
                frios = {4, 5, 6, 7, 8, 9}
                
                df_y_prev = df_month[(df_month['Year'] == y - 1) & (df_month['valido'])]
                max_calido_prev = df_y_prev[df_y_prev['Month'].isin(calidos)]['valor_mensual'].max() if not df_y_prev.empty else np.nan
                max_frio_prev = df_y_prev[df_y_prev['Month'].isin(frios)]['valor_mensual'].max() if not df_y_prev.empty else np.nan
                
                valores_a_promediar = list(valid_months_df['valor_mensual'])
                meses_necesarios = 11 - meses_validos_count
                
                imputaciones_posibles = []
                for m in meses_faltantes:
                    if m in calidos and pd.notna(max_calido_prev):
                        imputaciones_posibles.append(max_calido_prev)
                    elif m in frios and pd.notna(max_frio_prev):
                        imputaciones_posibles.append(max_frio_prev)
                
                # Principio precautorio: Ordenamos de mayor a menor y tomamos las que maximicen el promedio
                imputaciones_posibles.sort(reverse=True)
                        
                if len(imputaciones_posibles) >= meses_necesarios:
                    valores_a_promediar.extend(imputaciones_posibles[:meses_necesarios])
                    mean_val = np.mean(valores_a_promediar)
                    resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': meses_validos_count, 'valido': True, 'total_esperado': 12, 'porcentaje_validos': (meses_validos_count/12.0)*100})
                else:
                    mean_val = valid_months_df['valor_mensual'].mean()
                    resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': meses_validos_count, 'valido': False, 'total_esperado': 12, 'porcentaje_validos': (meses_validos_count/12.0)*100})
                    
        year_agg = pd.DataFrame(resultados)
        return year_agg.dropna(subset=['valor_anual'])

    elif is_pb:
        years = sorted(df_month['Year'].unique())
        resultados = []
        
        for y in years:
            df_y = df_month[df_month['Year'] == y]
            valid_months_df = df_y[df_y['valido']]
            meses_validos_count = len(valid_months_df)
            
            if meses_validos_count == 0:
                mean_val = df_y['valor_mensual'].mean() if len(df_y) > 0 else np.nan
                resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': 0, 'valido': False, 'total_esperado': 12, 'porcentaje_validos': 0.0})
                continue
                
            if meses_validos_count >= 11:
                # Válido sin imputar
                mean_val = valid_months_df['valor_mensual'].mean()
                resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': meses_validos_count, 'valido': True, 'total_esperado': 12, 'porcentaje_validos': (meses_validos_count/12.0)*100})
            elif meses_validos_count <= 8:
                # Inválido
                mean_val = valid_months_df['valor_mensual'].mean()
                resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': meses_validos_count, 'valido': False, 'total_esperado': 12, 'porcentaje_validos': (meses_validos_count/12.0)*100})
            else:
                # 9 o 10 meses válidos: imputar hasta llegar a 11 con el máximo del año anterior
                df_y_prev = df_month[(df_month['Year'] == y - 1) & (df_month['valido'])]
                max_prev = df_y_prev['valor_mensual'].max() if not df_y_prev.empty else np.nan
                
                valores_a_promediar = list(valid_months_df['valor_mensual'])
                meses_necesarios = 11 - meses_validos_count
                
                if pd.notna(max_prev):
                    valores_a_promediar.extend([max_prev] * meses_necesarios)
                    mean_val = np.mean(valores_a_promediar)
                    resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': meses_validos_count, 'valido': True, 'total_esperado': 12, 'porcentaje_validos': (meses_validos_count/12.0)*100})
                else:
                    mean_val = valid_months_df['valor_mensual'].mean()
                    resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': meses_validos_count, 'valido': False, 'total_esperado': 12, 'porcentaje_validos': (meses_validos_count/12.0)*100})
                    
        year_agg = pd.DataFrame(resultados)
        return year_agg.dropna(subset=['valor_anual'])

    elif is_so2_primario:
        years = sorted(df_month['Year'].unique())
        resultados = []
        for y in years:
            df_y_month = df_month[df_month['Year'] == y]
            if df_y_month.empty:
                continue
                
            trimestres = {
                1: [1, 2, 3],
                2: [4, 5, 6],
                3: [7, 8, 9],
                4: [10, 11, 12]
            }
            
            valores_trimestrales = []
            trimestres_validos_count = 0
            
            import calendar
            for t_idx, meses_t in trimestres.items():
                df_t_month = df_y_month[df_y_month['Month'].isin(meses_t)]
                
                # Promedio de meses para el valor del trimestre (Art 2, h)
                valor_trimestral = df_t_month['valor_mensual'].mean() if not df_t_month.empty else np.nan
                    
                # Evaluar validez del trimestre: 75% de las horas (o días si fallback)
                es_valido = False
                if df is not None and col_objetivo:
                    df_t_raw = df[(df['Datetime'].dt.year == y) & (df['Datetime'].dt.month.isin(meses_t))]
                    datos_validos = df_t_raw[col_objetivo].count()
                    
                    dias_trimestre = sum(calendar.monthrange(y, m)[1] for m in meses_t)
                    if is_hourly:
                        datos_totales = dias_trimestre * 24
                    else:
                        datos_totales = dias_trimestre
                        
                    if datos_validos >= 0.75 * datos_totales:
                        es_valido = True
                
                if es_valido and pd.notna(valor_trimestral):
                    valores_trimestrales.append(valor_trimestral)
                    trimestres_validos_count += 1
            
            # Valor anual es el promedio de los trimestres (Art 2, i)
            if trimestres_validos_count >= 3:
                # Año válido si tiene >= 3 trimestres válidos
                mean_val = np.mean(valores_trimestrales)
                resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': trimestres_validos_count, 'valido': True, 'total_esperado': 4, 'porcentaje_validos': (trimestres_validos_count/4.0)*100})
            else:
                # Año inválido
                if len(valores_trimestrales) > 0:
                    mean_val = np.mean(valores_trimestrales)
                else:
                    mean_val = df_y_month['valor_mensual'].mean()
                resultados.append({'Year': y, 'valor_anual': mean_val, 'meses_validos': trimestres_validos_count, 'valido': False, 'total_esperado': 4, 'porcentaje_validos': (trimestres_validos_count/4.0)*100})
                
        year_agg = pd.DataFrame(resultados)
        return year_agg.dropna(subset=['valor_anual'])

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
    
    year_agg['total_esperado'] = 12
    year_agg['porcentaje_validos'] = (year_agg['meses_validos'] / 12.0) * 100.0
    
    if contaminante_eval in ['mp10', 'mp2,5', 'mp2.5']:
        year_agg['valido'] = year_agg['meses_validos'] >= 9
    else:
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
        df_year = calcular_valor_anual(df_month, df, col_objetivo, is_hourly)
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
        df_year = calcular_valor_anual(df_month, df, col_objetivo, is_hourly)
        if df_year.empty:
            continue
            
        fig, ax = plt.subplots(figsize=(ANCHO_GRAFICO_PX / DPI_GRAFICO, ALTO_GRAFICO_PX / DPI_GRAFICO))
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
            
        bars = ax.bar(years_plot, vals_plot, color=colors_plot, width=0.8, align='center', edgecolor='black', linewidth=0.5)

        if MOSTRAR_INFO_QAQC:
            y_pos = y_max_plot * 0.02
            for idx, year_p in enumerate(years_plot):
                color_barra = colors_plot[idx]
                color_oscuro = oscurecer_color(color_barra, 0.4)
                
                # Fetch info from df_year
                df_y = df_year[df_year['Year'] == year_p]
                if not df_y.empty:
                    tot = df_y.iloc[0]['total_esperado']
                    val = df_y.iloc[0]['meses_validos']
                    pct = df_y.iloc[0]['porcentaje_validos']
                    texto_qa = f"tot:{int(tot)}\nval:{int(val)}\n%:{pct:.1f}"
                    
                    x_center = year_p
                    ax.text(x_center, y_pos, texto_qa, color=color_oscuro, 
                            ha='center', va='bottom', fontsize=6)

            
        for bar in bars:
            height = bar.get_height()
            if pd.notnull(height) and height > 0:
                ax.annotate(f'{int(round(height))}',
                            xy=(bar.get_x() + bar.get_width() / 2, height),
                            xytext=(0, 3),  
                            textcoords="offset points",
                            ha='center', va='bottom', fontsize=10, fontweight='bold')
                            
        ax.set_ylim(0, y_max_plot + 10)
        
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
        for i, y in enumerate(years_plot):
            color = colors_plot[i]
            if color != '#b0b0b0':
                if not any(h.get_label() == str(y) for h in handles):
                    handles.append(mpatches.Patch(facecolor=color, edgecolor='black', linewidth=0.5, label=str(y)))
            
        if '#b0b0b0' in colors_plot:
            handles.append(mpatches.Patch(facecolor='#b0b0b0', edgecolor='black', linewidth=0.5, label='Datos < 75% (No válido)'))
            
        ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(0.5, -0.09), 
                  ncol=len(handles), frameon=False)
        
        filename_img = f"{estacion}-{cont_str}-anual-{AÑO_INICIO}-{AÑO_FIN}.png"
        filepath_img = os.path.join(out_dir_chart, filename_img)
        fig.subplots_adjust(bottom=0.15, top=0.92, left=0.06, right=0.98)
        plt.savefig(filepath_img, dpi=DPI_GRAFICO)
        plt.close(fig)
        
        print(f"   Generado gráfico: {filepath_img}")

if __name__ == "__main__":
    main()
    print("\n¡Proceso completado con éxito!")
