import streamlit as st
import os
import copy
import openpyxl
from agente_condensador import CASO_EJEMPLO, disenar, notas_criticas, escribir_hoja_tema

st.set_page_config(page_title="Diseño de Condensador TEMA", layout="wide")

st.title("⚡ Agente de Diseño de Condensadores de Casco y Tubos")
st.markdown("Plataforma interactiva de cálculo y dimensionamiento térmico e hidráulico.")

# Sidebar - Inputs
st.sidebar.header("📥 Parámetros de Entrada")
caso = copy.deepcopy(CASO_EJEMPLO)

with st.sidebar.expander("Corriente Caliente (Vapor / Casco)", expanded=False):
    caso["caliente"]["W"] = st.number_input("Caudal másico vapor [kg/s]", value=caso["caliente"]["W"], step=0.05)
    caso["caliente"]["Tsat"] = st.number_input("T sat [°C]", value=caso["caliente"]["Tsat"])
    caso["caliente"]["T1"] = st.number_input("T entrada [°C]", value=caso["caliente"]["T1"])
    caso["caliente"]["T2"] = st.number_input("T salida [°C]", value=caso["caliente"]["T2"])
    caso["caliente"]["dP_adm"] = st.number_input("ΔP admisible casco [Pa]", value=caso["caliente"]["dP_adm"], step=1000.0)

with st.sidebar.expander("Corriente Fría (Refrigerante / Tubos)", expanded=False):
    caso["fria"]["t1"] = st.number_input("t entrada agua [°C]", value=caso["fria"]["t1"])
    caso["fria"]["t2"] = st.number_input("t salida agua [°C]", value=caso["fria"]["t2"])
    caso["fria"]["dP_adm"] = st.number_input("ΔP admisible tubos [Pa]", value=caso["fria"]["dP_adm"], step=5000.0)

with st.sidebar.expander("Restricciones Constructivas", expanded=False):
    caso["constructivo"]["Do"] = st.number_input("Diámetro ext. tubo [m]", value=caso["constructivo"]["Do"], format="%.5f")
    caso["constructivo"]["Di"] = st.number_input("Diámetro int. tubo [m]", value=caso["constructivo"]["Di"], format="%.5f")
    caso["constructivo"]["L_max"] = st.number_input("Longitud máx. tubo [m]", value=caso["constructivo"]["L_max"])
    caso["constructivo"]["arreglo"] = st.selectbox("Arreglo de tubos", ["triangular", "cuadrado"])

if st.button("🚀 Ejecutar Algoritmo de Diseño", type="primary"):
    log = []
    try:
        bal, r = disenar(caso, log)
        notas = notas_criticas(caso, r)

        if r["cumple"]:
            st.success("✅ **¡DISEÑO FACTIBLE!** Cumple todas las restricciones operativas y TEMA.")
        else:
            st.warning("⚠️ **ATENCIÓN:** No cumple el 100% de las restricciones. Se muestra la solución de menor violación.")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Carcasas en serie", f"{r['Ns']}")
        col2.metric("Diámetro Casco (Ds)", f"{r['Ds']*1000:.0f} mm")
        col3.metric("Número de Tubos", f"{r['Nt']}")
        col4.metric("Superficie Total", f"{r['A_total']:.2f} m²")

        col5, col6, col7, col8 = st.columns(4)
        col5.metric("Coeficiente Uc", f"{r['Uc']:,.0f} W/m²K")
        col6.metric("Coeficiente Ud", f"{r['Ud']:,.0f} W/m²K")
        col7.metric("ΔP Casco (calc/adm)", f"{r['dP_casco']/1e3:.2f} kPa", f"Máx {caso['caliente']['dP_adm']/1e3:.1f} kPa")
        col8.metric("ΔP Tubos (calc/adm)", f"{r['dP_tubos']/1e3:.2f} kPa", f"Máx {caso['fria']['dP_adm']/1e3:.1f} kPa")

        tab1, tab2, tab3 = st.tabs(["📊 Desempeño y Geometría", "💡 Criterio de Ingeniería", "📝 Registro de Iteraciones"])

        with tab1:
            st.subheader("Resultados Geométricos e Hidráulicos")
            col_a, col_b = st.columns(2)
            with col_a:
                st.write(f"**Longitud de tubos:** {r['L']:.2f} m")
                st.write(f"**Pasos por tubo:** {r['n']}")
                st.write(f"**Espaciado de deflectores (B):** {r['B']*1000:.0f} mm ({r['n_deflectores']} deflectores)")
                st.write(f"**Velocidad en tubos:** {r['v_tubos']:.2f} m/s")
            with col_b:
                st.write(f"**Factor Ft:** {r['Ft']:.3f}")
                st.write(f"**Modelo ho empleado:** {r['modelo_ho']}")
                st.write(f"**Rd calculado:** {r['Rd_calc']:.6f} m²K/W (Req: {r['Rd_req']:.6f})")
                st.write(f"**Exceso de área:** {r['exceso']:.1f}%")

        with tab2:
            st.subheader("Observaciones TÉCNICAS")
            for n in notas:
                st.info(f"• {n}")

        with tab3:
            st.subheader("Paso a Paso del Algoritmo Iterativo")
            st.code("\n".join(log), language="text")

        ruta_excel = "Hoja_TEMA_generada.xlsx"
        escribir_hoja_tema(caso, bal, r, notas, log, ruta_excel)
        
        with open(ruta_excel, "rb") as file:
            st.download_button(
                label="📥 Descargar Hoja de Especificaciones TEMA (.xlsx)",
                data=file,
                file_name="Hoja_TEMA_Condensador.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    except Exception as e:
        st.error(f"Error durante el cálculo: {str(e)}")
