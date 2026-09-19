"""
Dashboard interactivo — Dinámica de Ingresos y Medición de Desigualdad
Aglomerado Corrientes | EPH-INDEC | T4-2024 vs T4-2025
Equipo 5

Este dashboard consume los CSV generados por `procesamiento.py` (carpeta
`data_procesada/`) y presenta los resultados de forma visual e interactiva,
pensado para un público con formación en economía pero sin asumir que quien
lo presenta es especialista en el tema.
"""

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ------------------------------------------------------------------
# Configuración de página
# ------------------------------------------------------------------
st.set_page_config(
    page_title="Desigualdad de Ingresos — Corrientes",
    page_icon="📊",
    layout="wide",
)

CARPETA_DATOS = "data_procesada"
COLOR_2024 = "#4C78A8"
COLOR_2025 = "#E45756"


@st.cache_data
def cargar_datos():
    resumen = pd.read_csv(os.path.join(CARPETA_DATOS, "resumen_general.csv"))
    deciles = pd.read_csv(os.path.join(CARPETA_DATOS, "tabla_deciles.csv"))
    lorenz = pd.read_csv(os.path.join(CARPETA_DATOS, "curva_lorenz.csv"))
    composicion = pd.read_csv(os.path.join(CARPETA_DATOS, "composicion_vulnerables.csv"))
    auditoria = pd.read_csv(os.path.join(CARPETA_DATOS, "auditoria_depuracion.csv"))
    return resumen, deciles, lorenz, composicion, auditoria


try:
    resumen, deciles, lorenz, composicion, auditoria = cargar_datos()
except FileNotFoundError:
    st.error(
        "No se encontraron los archivos de `data_procesada/`. "
        "Ejecutá primero `python procesamiento.py` para generarlos."
    )
    st.stop()

fmt_money = lambda v: f"${v:,.0f}".replace(",", ".")

# ------------------------------------------------------------------
# Encabezado
# ------------------------------------------------------------------
st.title("📊 Dinámica de Ingresos y Medición de Desigualdad")
st.subheader("Aglomerado Corrientes — Comparación T4-2024 vs T4-2025 (EPH-INDEC)")

with st.expander("ℹ️ Cómo leer este dashboard (metodología en criollo)"):
    st.markdown(
        """
        - **Fuente:** Encuesta Permanente de Hogares (EPH) del INDEC, bases de
          usuario de Hogar e Individual.
        - **Variable de bienestar:** Ingreso Per Cápita Familiar (**IPCF**),
          ponderado con **PONDIH** (el ponderador que corrige la falta de
          respuesta de ingresos).
        - **Depuración:** se excluyen los hogares con ingreso en cero o sin
          respuesta (decil nacional 0 y 12) para no distorsionar la
          desigualdad real.
        - **Deciles locales:** en vez de usar el decil nacional, se
          recalculan 10 grupos de igual tamaño poblacional *dentro* del
          aglomerado de Corrientes, para que reflejen la estructura local.
        - **Coeficiente de Gini:** mide la desigualdad entre 0 (todos ganan
          lo mismo) y 1 (una sola persona concentra todo el ingreso).
        """
    )

# ------------------------------------------------------------------
# KPIs principales
# ------------------------------------------------------------------
r24 = resumen[resumen["periodo"] == "T4-2024"].iloc[0]
r25 = resumen[resumen["periodo"] == "T4-2025"].iloc[0]

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Coeficiente de Gini",
    f"{r25['gini']:.4f}",
    delta=f"{r25['gini'] - r24['gini']:+.4f} vs T4-2024",
    delta_color="inverse",
)
col2.metric(
    "IPCF mediano",
    fmt_money(r25["ipcf_mediana_general"]),
    delta=f"{fmt_money(r25['ipcf_mediana_general'] - r24['ipcf_mediana_general'])} vs T4-2024",
)
col3.metric(
    "Índice de Palma",
    f"{r25['indice_palma']:.2f}",
    delta=f"{r25['indice_palma'] - r24['indice_palma']:+.2f} vs T4-2024",
    delta_color="inverse",
)
col4.metric(
    "Brecha D10/D1 (medianas)",
    f"{r25['brecha_d10_d1_medianas']:.1f}x",
    delta=f"{r25['brecha_d10_d1_medianas'] - r24['brecha_d10_d1_medianas']:+.1f}x vs T4-2024",
    delta_color="inverse",
)

st.caption(
    f"El Gini subió de **{r24['gini']:.4f}** en T4-2024 a **{r25['gini']:.4f}** en "
    f"T4-2025, lo que indica un leve aumento de la concentración del ingreso "
    f"en el aglomerado de Corrientes."
)

st.divider()

# ------------------------------------------------------------------
# Tabs de contenido
# ------------------------------------------------------------------
tab_lorenz, tab_deciles, tab_polarizacion, tab_composicion, tab_metodologia = st.tabs(
    [
        "Curva de Lorenz",
        "Deciles de ingreso",
        "Polarización",
        "Composición del ingreso",
        "Metodología y auditoría",
    ]
)

# --- Curva de Lorenz ---
with tab_lorenz:
    st.markdown("#### Curva de Lorenz — distribución acumulada del ingreso")
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Igualdad perfecta",
                    line=dict(dash="dash", color="gray"))
    )
    for periodo, color in [("T4-2024", COLOR_2024), ("T4-2025", COLOR_2025)]:
        sub = lorenz[lorenz["periodo"] == periodo]
        fig.add_trace(
            go.Scatter(
                x=sub["poblacion_acumulada"],
                y=sub["ingreso_acumulado"],
                mode="lines",
                name=periodo,
                line=dict(color=color, width=3),
            )
        )
    fig.update_layout(
        xaxis_title="Proporción acumulada de población",
        yaxis_title="Proporción acumulada de ingreso",
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)
    st.info(
        "Cuanto más se aleja la curva de la diagonal (línea de igualdad "
        "perfecta), mayor es la desigualdad. El área entre ambas líneas es "
        "la base del cálculo del coeficiente de Gini."
    )

# --- Deciles ---
with tab_deciles:
    st.markdown("#### IPCF promedio y mediana por decil local")
    metrica = st.radio(
        "Métrica a graficar", ["ipcf_promedio", "ipcf_mediana"], horizontal=True,
        format_func=lambda v: "IPCF promedio" if v == "ipcf_promedio" else "IPCF mediana",
    )
    fig = go.Figure()
    for periodo, color in [("T4-2024", COLOR_2024), ("T4-2025", COLOR_2025)]:
        sub = deciles[deciles["periodo"] == periodo]
        fig.add_trace(
            go.Bar(x=sub["decil_local"], y=sub[metrica], name=periodo, marker_color=color)
        )
    fig.update_layout(
        barmode="group",
        xaxis_title="Decil local (1 = más pobre, 10 = más rico)",
        yaxis_title="Pesos ($)",
        xaxis=dict(tickmode="linear"),
        height=450,
    )
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### Participación de cada decil en la masa total de ingresos")
    fig2 = go.Figure()
    for periodo, color in [("T4-2024", COLOR_2024), ("T4-2025", COLOR_2025)]:
        sub = deciles[deciles["periodo"] == periodo]
        fig2.add_trace(
            go.Bar(x=sub["decil_local"], y=sub["participacion_pct"], name=periodo, marker_color=color)
        )
    fig2.update_layout(
        barmode="group",
        xaxis_title="Decil local",
        yaxis_title="% de la masa total de ingresos",
        xaxis=dict(tickmode="linear"),
        height=450,
    )
    st.plotly_chart(fig2, use_container_width=True)

    with st.expander("Ver tabla completa de deciles"):
        st.dataframe(
            deciles.pivot(index="decil_local", columns="periodo",
                           values=["ipcf_promedio", "ipcf_mediana", "participacion_pct"])
            .round(1),
            use_container_width=True,
        )

# --- Polarización ---
with tab_polarizacion:
    st.markdown("#### Índice de Palma y brecha D10/D1")
    st.write(
        "El **Índice de Palma** compara lo que se lleva el 10% más rico "
        "contra lo que se lleva el 40% más pobre. Un valor de 1 significa "
        "que ambos grupos tienen la misma porción del ingreso total."
    )
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure(
            data=[
                go.Bar(
                    x=["T4-2024", "T4-2025"],
                    y=[r24["indice_palma"], r25["indice_palma"]],
                    marker_color=[COLOR_2024, COLOR_2025],
                    text=[f"{r24['indice_palma']:.2f}", f"{r25['indice_palma']:.2f}"],
                    textposition="outside",
                )
            ]
        )
        fig.update_layout(title="Índice de Palma", yaxis_title="Palma (D10 / D1–D4)", height=400)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = go.Figure(
            data=[
                go.Bar(
                    x=["T4-2024", "T4-2025"],
                    y=[r24["brecha_d10_d1_medianas"], r25["brecha_d10_d1_medianas"]],
                    marker_color=[COLOR_2024, COLOR_2025],
                    text=[f"{r24['brecha_d10_d1_medianas']:.1f}x", f"{r25['brecha_d10_d1_medianas']:.1f}x"],
                    textposition="outside",
                )
            ]
        )
        fig.update_layout(title="Brecha D10 / D1 (medianas)", yaxis_title="Veces", height=400)
        st.plotly_chart(fig, use_container_width=True)
    st.info(
        f"La brecha entre el decil más rico y el más pobre pasó de "
        f"{r24['brecha_d10_d1_medianas']:.1f} a {r25['brecha_d10_d1_medianas']:.1f} veces: "
        f"el ingreso mediano del decil 10 creció más rápido que el del decil 1."
    )

# --- Composición del ingreso ---
with tab_composicion:
    st.markdown("#### Composición del ingreso en los hogares más vulnerables (deciles 1 a 3)")
    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=composicion["periodo"],
            y=composicion["ingreso_laboral_pct"],
            name="Ingresos laborales (P21)",
            marker_color="#4C78A8",
        )
    )
    fig.add_trace(
        go.Bar(
            x=composicion["periodo"],
            y=composicion["ingreso_no_laboral_pct"],
            name="Ingresos no laborales (jubilaciones, planes, asignaciones)",
            marker_color="#F58518",
        )
    )
    fig.update_layout(
        barmode="stack",
        yaxis_title="% del ingreso total del grupo",
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    st.plotly_chart(fig, use_container_width=True)
    fila25 = composicion[composicion["periodo"] == "T4-2025"].iloc[0]
    st.info(
        f"En T4-2025, el {fila25['ingreso_no_laboral_pct']:.1f}% del ingreso de los "
        f"hogares más vulnerables (deciles 1 a 3) proviene de fuentes no "
        f"laborales (jubilaciones, pensiones, asignaciones y otras "
        f"transferencias), lo que muestra su dependencia de la protección social."
    )

# --- Metodología y auditoría ---
with tab_metodologia:
    st.markdown("#### Trazabilidad de la depuración de datos")
    st.dataframe(auditoria, use_container_width=True)
    st.markdown(
        """
        **Resumen del pipeline aplicado:**
        1. Vinculación de las bases Hogar e Individual por `CODUSU` + `NRO_HOGAR`.
        2. Filtro geográfico: `AGLOMERADO == 12` (Corrientes).
        3. Depuración de calidad: exclusión de `DECCFR` igual a 0 (ingreso
           cero) o 12 (no respuesta).
        4. Ponderación con `PONDIH` (corrige la no respuesta de ingresos).
        5. Deciles locales recalculados sobre la población depurada, ordenando
           por `IPCF` y acumulando población ponderada.
        6. Gini calculado con el método de los trapecios sobre la Curva de Lorenz.
        """
    )
    st.markdown("#### Tabla resumen general")
    st.dataframe(resumen.round(4), use_container_width=True)

st.divider()
st.caption(
    "Proyecto final — Equipo 5 · Tecnicatura Superior en Ciencias de Datos e "
    "Inteligencia Artificial · Fuente: EPH-INDEC."
)
