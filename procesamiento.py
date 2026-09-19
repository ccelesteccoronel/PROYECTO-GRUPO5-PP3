"""
Procesamiento de datos EPH-INDEC — Equipo 5
Dinámica de Ingresos y Medición de Desigualdad (Aglomerado Corrientes)

Este script sigue el pipeline definido en el plan de trabajo del proyecto:
  1. Vinculación de bases Hogar + Individual y depuración por calidad
  2. Configuración del ponderador de ingresos (PONDIH)
  3. Segmentación en deciles locales
  4. Coeficiente de Gini (método de los trapecios) y Curva de Lorenz
  5. Índice de Palma y brecha D10/D1
  6. Composición del ingreso en los deciles más vulnerables (1 a 3)

Al ejecutarlo, genera todos los archivos CSV que consume el dashboard de
Streamlit (carpeta `data_procesada/`).

Uso:
    python procesamiento.py
"""

import os
import numpy as np
import pandas as pd

# ------------------------------------------------------------------
# Configuración general
# ------------------------------------------------------------------
CARPETA_DATOS_CRUDOS = "data"
CARPETA_SALIDA = "data_procesada"
AGLOMERADO_OBJETIVO = 12  # Corrientes

PERIODOS = [
    {
        "nombre": "T4-2024",
        "hogar": os.path.join(CARPETA_DATOS_CRUDOS, "usu_hogar_T424.xlsx"),
        "individual": os.path.join(CARPETA_DATOS_CRUDOS, "usu_individual_T424.xlsx"),
        "anio": 2024,
        "trimestre": 4,
    },
    {
        "nombre": "T4-2025",
        "hogar": os.path.join(CARPETA_DATOS_CRUDOS, "usu_hogar_T425.xlsx"),
        "individual": os.path.join(CARPETA_DATOS_CRUDOS, "usu_individual_T425.xlsx"),
        "anio": 2025,
        "trimestre": 4,
    },
]


# ------------------------------------------------------------------
# Prioridad 1: Adquisición, filtrado y vinculación muestral
# ------------------------------------------------------------------
def cargar_y_depurar(periodo: dict) -> tuple[pd.DataFrame, dict]:
    """Carga Hogar + Individual, vincula por CODUSU+NRO_HOGAR, filtra por
    aglomerado y depura por calidad de ingreso (DECCFR distinto de 0 y 12).
    Devuelve el dataframe depurado y un diccionario con métricas de auditoría.
    """
    hogar = pd.read_excel(periodo["hogar"])
    individual = pd.read_excel(periodo["individual"])

    # Vinculación (linkage) por clave compuesta CODUSU + NRO_HOGAR
    merged = individual.merge(
        hogar[["CODUSU", "NRO_HOGAR", "AGLOMERADO"]],
        on=["CODUSU", "NRO_HOGAR"],
        how="left",
        suffixes=("", "_hogar"),
        indicator=True,
    )
    tasa_vinculacion = float((merged["_merge"] == "both").mean())
    merged = merged.drop(columns=["_merge"])

    # Filtro geográfico
    n_previo_aglo = len(merged)
    merged = merged[merged["AGLOMERADO"] == AGLOMERADO_OBJETIVO].copy()
    n_post_aglo = len(merged)

    # Depuración por calidad: excluir ingresos en cero (0) y no respuesta (12)
    n_previo_calidad = len(merged)
    merged = merged[~merged["DECCFR"].isin([0, 12])].copy()
    n_post_calidad = len(merged)

    merged["ANIO"] = periodo["anio"]
    merged["TRIMESTRE"] = periodo["trimestre"]
    merged["PERIODO"] = periodo["nombre"]

    auditoria = {
        "periodo": periodo["nombre"],
        "tasa_vinculacion_hogar_individual": round(tasa_vinculacion, 4),
        "registros_aglomerado": n_post_aglo,
        "registros_previos_a_aglomerado": n_previo_aglo,
        "registros_excluidos_por_calidad_ingreso": n_previo_calidad - n_post_calidad,
        "registros_finales": n_post_calidad,
    }
    return merged, auditoria


# ------------------------------------------------------------------
# Prioridad 3: Segmentación y recálculo de deciles locales
# ------------------------------------------------------------------
def mediana_ponderada(valores: pd.Series, pesos: pd.Series) -> float:
    df = pd.DataFrame({"v": valores, "w": pesos}).sort_values("v")
    acumulado = df["w"].cumsum()
    punto_medio = df["w"].sum() / 2
    return float(df["v"][acumulado >= punto_medio].iloc[0])


def calcular_deciles_locales(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ordena por IPCF, acumula población ponderada (PONDIH) y parte en
    10 tramos poblacionales iguales. Devuelve (tabla_resumen, df_con_decil)."""
    d = df.sort_values("IPCF").copy()
    poblacion_total = d["PONDIH"].sum()
    d["pond_acum"] = d["PONDIH"].cumsum()
    d["decil_local"] = np.ceil(d["pond_acum"] / poblacion_total * 10).clip(1, 10).astype(int)

    masa_total = (d["IPCF"] * d["PONDIH"]).sum()

    filas = []
    for decil, grupo in d.groupby("decil_local"):
        masa_decil = (grupo["IPCF"] * grupo["PONDIH"]).sum()
        filas.append(
            {
                "decil_local": decil,
                "ipcf_promedio": np.average(grupo["IPCF"], weights=grupo["PONDIH"]),
                "ipcf_mediana": mediana_ponderada(grupo["IPCF"], grupo["PONDIH"]),
                "poblacion_ponderada": grupo["PONDIH"].sum(),
                "masa_ingreso": masa_decil,
                "participacion_pct": masa_decil / masa_total * 100,
            }
        )
    tabla = pd.DataFrame(filas).sort_values("decil_local").reset_index(drop=True)
    return tabla, d


# ------------------------------------------------------------------
# Prioridad 4: Gini (método de los trapecios) y Curva de Lorenz
# ------------------------------------------------------------------
def calcular_gini_y_lorenz(df: pd.DataFrame) -> tuple[float, pd.DataFrame]:
    d = df[["IPCF", "PONDIH"]].sort_values("IPCF").copy()
    poblacion_total = d["PONDIH"].sum()
    masa_total = (d["IPCF"] * d["PONDIH"]).sum()

    d["pond_acum"] = d["PONDIH"].cumsum()
    d["x"] = d["pond_acum"] / poblacion_total  # proporción acumulada de población
    d["masa_acum"] = (d["IPCF"] * d["PONDIH"]).cumsum()
    d["y"] = d["masa_acum"] / masa_total  # proporción acumulada de ingreso

    x = np.concatenate([[0.0], d["x"].values])
    y = np.concatenate([[0.0], d["y"].values])
    area_bajo_curva = float(np.trapezoid(y, x))
    gini = 1 - 2 * area_bajo_curva

    curva_lorenz = pd.DataFrame({"poblacion_acumulada": x, "ingreso_acumulado": y})
    # Reducir la curva a 200 puntos para que el dashboard sea liviano
    if len(curva_lorenz) > 200:
        indices = np.linspace(0, len(curva_lorenz) - 1, 200).astype(int)
        curva_lorenz = curva_lorenz.iloc[indices].reset_index(drop=True)

    return gini, curva_lorenz


# ------------------------------------------------------------------
# Prioridad 5: Índice de Palma y brecha D10/D1
# ------------------------------------------------------------------
def calcular_polarizacion(tabla_deciles: pd.DataFrame) -> dict:
    t = tabla_deciles.set_index("decil_local")
    participacion_d10 = t.loc[10, "participacion_pct"]
    participacion_d1_a_d4 = t.loc[1:4, "participacion_pct"].sum()
    palma = participacion_d10 / participacion_d1_a_d4
    d10_d1 = t.loc[10, "ipcf_mediana"] / t.loc[1, "ipcf_mediana"]
    return {
        "indice_palma": palma,
        "brecha_d10_d1_medianas": d10_d1,
        "participacion_decil10_pct": participacion_d10,
        "participacion_decil1a4_pct": participacion_d1_a_d4,
    }


# ------------------------------------------------------------------
# Prioridad 6: Composición del ingreso en deciles vulnerables (1 a 3)
# ------------------------------------------------------------------
def calcular_composicion_vulnerables(df_con_decil: pd.DataFrame) -> dict:
    vulnerables = df_con_decil[df_con_decil["decil_local"] <= 3]
    masa_laboral = (vulnerables["P21"].clip(lower=0) * vulnerables["PONDIH"]).sum()
    masa_no_laboral = (vulnerables["T_VI"].clip(lower=0) * vulnerables["PONDIH"]).sum()
    total = masa_laboral + masa_no_laboral
    return {
        "ingreso_laboral_pct": masa_laboral / total * 100,
        "ingreso_no_laboral_pct": masa_no_laboral / total * 100,
    }


# ------------------------------------------------------------------
# Orquestación principal
# ------------------------------------------------------------------
def main():
    os.makedirs(CARPETA_SALIDA, exist_ok=True)

    resumen_general = []
    auditorias = []
    tablas_deciles = []
    curvas_lorenz = []
    composiciones = []

    for periodo in PERIODOS:
        df, auditoria = cargar_y_depurar(periodo)
        auditorias.append(auditoria)

        tabla_deciles, df_con_decil = calcular_deciles_locales(df)
        tabla_deciles["periodo"] = periodo["nombre"]
        tablas_deciles.append(tabla_deciles)

        gini, curva_lorenz = calcular_gini_y_lorenz(df)
        curva_lorenz["periodo"] = periodo["nombre"]
        curvas_lorenz.append(curva_lorenz)

        polarizacion = calcular_polarizacion(tabla_deciles)
        composicion = calcular_composicion_vulnerables(df_con_decil)
        composicion["periodo"] = periodo["nombre"]
        composiciones.append(composicion)

        resumen_general.append(
            {
                "periodo": periodo["nombre"],
                "anio": periodo["anio"],
                "trimestre": periodo["trimestre"],
                "gini": gini,
                "poblacion_ponderada_total": df["PONDIH"].sum(),
                "ipcf_promedio_general": np.average(df["IPCF"], weights=df["PONDIH"]),
                "ipcf_mediana_general": mediana_ponderada(df["IPCF"], df["PONDIH"]),
                **polarizacion,
            }
        )

        print(f"[{periodo['nombre']}] Gini = {gini:.4f}  |  registros = {len(df)}")

    pd.DataFrame(resumen_general).to_csv(
        os.path.join(CARPETA_SALIDA, "resumen_general.csv"), index=False
    )
    pd.DataFrame(auditorias).to_csv(
        os.path.join(CARPETA_SALIDA, "auditoria_depuracion.csv"), index=False
    )
    pd.concat(tablas_deciles, ignore_index=True).to_csv(
        os.path.join(CARPETA_SALIDA, "tabla_deciles.csv"), index=False
    )
    pd.concat(curvas_lorenz, ignore_index=True).to_csv(
        os.path.join(CARPETA_SALIDA, "curva_lorenz.csv"), index=False
    )
    pd.DataFrame(composiciones).to_csv(
        os.path.join(CARPETA_SALIDA, "composicion_vulnerables.csv"), index=False
    )

    print(f"\nArchivos generados en '{CARPETA_SALIDA}/':")
    for archivo in os.listdir(CARPETA_SALIDA):
        print(" -", archivo)


if __name__ == "__main__":
    main()
