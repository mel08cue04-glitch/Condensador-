# -*- coding: utf-8 -*-
"""
Aplicación web para el diseño de condensadores de casco y tubos.
Usa el motor de cálculo de agente_condensador.py (deben estar en la misma carpeta).

Ejecutar:   streamlit run app_condensador.py
"""
import copy
from io import BytesIO

import pandas as pd
import streamlit as st

from agente_condensador import CASO_EJEMPLO, disenar, notas_criticas, escribir_hoja_tema, bwg_de

# -----------------------------------------------------------------------------
# Configuración de la página y estilo
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Diseño de condensadores", page_icon="🌡️", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem; max-width: 1200px;}
      .veredicto {border-radius: 14px; padding: 1.1rem 1.4rem; margin: .6rem 0 1.2rem 0;
                  font-size: 1.15rem; font-weight: 600;}
      .veredicto small {display:block; font-weight: 400; font-size: .92rem; margin-top: .25rem;}
      .ok  {background:#e8f6ee; color:#14532d; border:1px solid #86d3a3;}
      .mal {background:#fdeceb; color:#7f1d1d; border:1px solid #f1a5a0;}
      div[data-testid="stMetric"] {background:#f6f8fb; border:1px solid #e3e8ef; border-radius:12px;
                                   padding:.8rem 1rem;}
      div[data-testid="stForm"] {border:none; padding:0;}
    </style>
    """,
    unsafe_allow_html=True,
)

BASE = CASO_EJEMPLO


# -----------------------------------------------------------------------------
# Funciones auxiliares (sin interfaz, fáciles de probar)
# -----------------------------------------------------------------------------
def construir_caso(v):
    """Convierte los valores del formulario (unidades de uso cómodo) al diccionario SI del motor."""
    caso = copy.deepcopy(BASE)
    idn, h, f, k, d = caso["identificacion"], caso["caliente"], caso["fria"], caso["constructivo"], caso["diseno"]

    idn.update(cliente=v["cliente"], item=v["item"], servicio=v["servicio"], tipo_TEMA=v["tipo_TEMA"])

    h.update(fluido=v["h_fluido"], W=v["h_W"] / 3600.0, T1=v["h_T1"], T2=v["h_T2"], Tsat=v["h_Tsat"],
             P_oper=v["h_P"] * 1e3, lam=v["h_lam"] * 1e3,
             rho_v=v["v_rho"], mu_v=v["v_mu"] * 1e-3, k_v=v["v_k"], cp_v=v["v_cp"] * 1e3,
             rho_l=v["l_rho"], mu_l=v["l_mu"] * 1e-3, k_l=v["l_k"], cp_l=v["l_cp"] * 1e3,
             T_film_ref=v["l_Tref"], Rd=v["h_Rd"], dP_adm=v["h_dP"] * 1e3)

    f.update(fluido=v["c_fluido"], t1=v["c_t1"], Rd=v["c_Rd"], dP_adm=v["c_dP"] * 1e3, props="agua")
    if v["c_modo"] == "Conozco la temperatura de salida":
        f.update(t2=v["c_t2"], W=None)
    else:
        f.update(t2=None, W=v["c_W"] / 3600.0)

    k.update(Do=v["Do"] / 1000.0, Di=v["Di"] / 1000.0, L_max=v["L_max"], arreglo=v["arreglo"],
             Pt=v["Pt"] / 1000.0, k_pared=v["k_pared"], v_min=v["v_min"], v_max=v["v_max"])
    d.update(Ud_est=v["Ud_est"], Ft_min=v["Ft_min"])
    return caso


def validar(v):
    """Devuelve una lista de errores de carga (vacía si todo está bien)."""
    e = []
    if v["h_T1"] < v["h_Tsat"] - 1e-9:
        e.append("La temperatura de entrada del vapor no puede ser menor que la de saturación.")
    if v["h_T2"] > v["h_Tsat"] + 1e-9:
        e.append("La temperatura de salida del condensado no puede ser mayor que la de saturación.")
    if v["h_W"] <= 0:
        e.append("El caudal de vapor debe ser mayor que cero.")
    if v["c_modo"] == "Conozco la temperatura de salida" and v["c_t2"] <= v["c_t1"]:
        e.append("La temperatura de salida del agua debe ser mayor que la de entrada.")
    if v["c_modo"] != "Conozco la temperatura de salida" and v["c_W"] <= 0:
        e.append("El caudal de agua debe ser mayor que cero.")
    if v["c_t1"] >= v["h_Tsat"]:
        e.append("El agua de enfriamiento debe entrar más fría que la temperatura de saturación del vapor.")
    if v["Di"] >= v["Do"]:
        e.append("El diámetro interno del tubo debe ser menor que el externo.")
    if v["Pt"] <= v["Do"]:
        e.append("El paso entre tubos debe ser mayor que el diámetro externo.")
    if v["v_min"] >= v["v_max"]:
        e.append("La velocidad mínima por tubos debe ser menor que la máxima.")
    return e


def tabla_verificaciones(caso, r):
    h, f, d = caso["caliente"], caso["fria"], caso["diseno"]
    k = caso["constructivo"]
    filas = [
        ("Factor de corrección Ft", f"{r['Ft']:.3f}", f"≥ {d['Ft_min']:.2f}", r["viol"]["Ft"] == 0),
        ("Factor de ensuciamiento calculado", f"{r['Rd_calc']:.6f} m²K/W", f"≥ {r['Rd_req']:.6f} m²K/W",
         r["viol"]["Rd"] == 0),
        ("Velocidad del agua en tubos", f"{r['v_tubos']:.2f} m/s", f"{k['v_min']:.1f} a {k['v_max']:.1f} m/s",
         r["viol"]["v_tubos"] == 0),
        ("Pérdida de carga en tubos", f"{r['dP_tubos']/1e3:.2f} kPa", f"≤ {f['dP_adm']/1e3:.1f} kPa",
         r["viol"]["dP_tubos"] == 0),
        ("Pérdida de carga en casco", f"{r['dP_casco']/1e3:.2f} kPa", f"≤ {h['dP_adm']/1e3:.1f} kPa",
         r["viol"]["dP_casco"] == 0),
    ]
    return pd.DataFrame({"Verificación": [x[0] for x in filas],
                         "Resultado": [x[1] for x in filas],
                         "Límite": [x[2] for x in filas],
                         "Estado": ["✅ Cumple" if x[3] else "❌ No cumple" for x in filas]})


def excel_en_memoria(caso, bal, r, notas, log):
    buf = BytesIO()
    escribir_hoja_tema(caso, bal, r, notas, log, buf)
    return buf.getvalue()


# -----------------------------------------------------------------------------
# Encabezado
# -----------------------------------------------------------------------------
st.title("🌡️ Diseño de condensadores de casco y tubos")
st.caption("Completá los datos del proceso, presioná **Calcular diseño** y obtené el equipo dimensionado "
           "junto con la hoja de especificaciones TEMA.")

# -----------------------------------------------------------------------------
# Formulario de entrada (todo en la página principal)
# -----------------------------------------------------------------------------
H, F, K, D, I = BASE["caliente"], BASE["fria"], BASE["constructivo"], BASE["diseno"], BASE["identificacion"]

with st.form("formulario"):
    st.subheader("1. Datos de entrada")
    t_id, t_vap, t_agua, t_tubo = st.tabs(["Equipo", "Vapor (lado casco)", "Agua de enfriamiento (lado tubos)",
                                            "Tubos y diseño"])
    v = {}

    with t_id:
        c1, c2, c3 = st.columns(3)
        v["cliente"] = c1.text_input("Cliente / Cátedra", I["cliente"])
        v["item"] = c2.text_input("Identificación del equipo", I["item"])
        v["servicio"] = c3.text_input("Servicio", I["servicio"])
        tipos = ["BEM", "AEL", "AES", "AET", "BEU", "AEU"]
        v["tipo_TEMA"] = c1.selectbox("Tipo de equipo (TEMA)", tipos, index=tipos.index(I["tipo_TEMA"]),
                                      help="BEM y AEL: cabezal fijo. AES y AET: cabezal flotante. "
                                           "BEU y AEU: tubos en U.")

    with t_vap:
        st.markdown("**Condiciones del vapor**")
        c1, c2, c3, c4 = st.columns(4)
        v["h_fluido"] = c1.text_input("Fluido que condensa", H["fluido"])
        v["h_W"] = c2.number_input("Caudal de vapor [kg/h]", value=float(H["W"] * 3600), min_value=0.0, step=10.0)
        v["h_P"] = c3.number_input("Presión de operación [kPa abs]", value=float(H["P_oper"] / 1e3), step=10.0)
        v["h_lam"] = c4.number_input("Calor latente [kJ/kg]", value=float(H["lam"] / 1e3), step=10.0)
        c1, c2, c3 = st.columns(3)
        v["h_Tsat"] = c1.number_input("Temperatura de saturación [°C]", value=float(H["Tsat"]), step=0.5)
        v["h_T1"] = c2.number_input("Temperatura de entrada [°C]", value=float(H["T1"]), step=0.5,
                                    help="Mayor que la de saturación si el vapor entra sobrecalentado.")
        v["h_T2"] = c3.number_input("Temperatura de salida del condensado [°C]", value=float(H["T2"]), step=0.5,
                                    help="Menor que la de saturación si el condensado sale subenfriado.")
        c1, c2, c3 = st.columns(3)
        v["h_Rd"] = c1.number_input("Factor de ensuciamiento requerido [m²K/W]", value=float(H["Rd"]),
                                    format="%.6f", step=0.00001)
        v["h_dP"] = c2.number_input("Pérdida de carga admisible [kPa]", value=float(H["dP_adm"] / 1e3), step=1.0)

        st.markdown("**Propiedades del vapor**")
        c1, c2, c3, c4 = st.columns(4)
        v["v_rho"] = c1.number_input("Densidad [kg/m³]", value=float(H["rho_v"]), format="%.4f", key="v_rho")
        v["v_mu"] = c2.number_input("Viscosidad [mPa·s]", value=float(H["mu_v"] * 1e3), format="%.5f", key="v_mu")
        v["v_k"] = c3.number_input("Conductividad térmica [W/m·K]", value=float(H["k_v"]), format="%.4f", key="v_k")
        v["v_cp"] = c4.number_input("Calor específico [kJ/kg·K]", value=float(H["cp_v"] / 1e3), format="%.3f",
                                    key="v_cp")
        st.markdown("**Propiedades del condensado**")
        c1, c2, c3, c4, c5 = st.columns(5)
        v["l_rho"] = c1.number_input("Densidad [kg/m³]", value=float(H["rho_l"]), format="%.2f", key="l_rho")
        v["l_mu"] = c2.number_input("Viscosidad [mPa·s]", value=float(H["mu_l"] * 1e3), format="%.4f", key="l_mu")
        v["l_k"] = c3.number_input("Conductividad térmica [W/m·K]", value=float(H["k_l"]), format="%.4f", key="l_k")
        v["l_cp"] = c4.number_input("Calor específico [kJ/kg·K]", value=float(H["cp_l"] / 1e3), format="%.3f",
                                    key="l_cp")
        v["l_Tref"] = c5.number_input("Temperatura de las propiedades [°C]", value=float(H["T_film_ref"]),
                                      help="Se recomienda evaluarlas a la temperatura media de la película "
                                           "de condensado.")

    with t_agua:
        c1, c2 = st.columns(2)
        v["c_fluido"] = c1.text_input("Fluido refrigerante", F["fluido"])
        v["c_modo"] = c2.radio("¿Qué dato conocés?", ["Conozco la temperatura de salida", "Conozco el caudal"],
                               horizontal=True)
        c1, c2, c3 = st.columns(3)
        v["c_t1"] = c1.number_input("Temperatura de entrada [°C]", value=float(F["t1"]), step=0.5)
        v["c_t2"] = c2.number_input("Temperatura de salida [°C] (si la conocés)", value=float(F["t2"]), step=0.5)
        v["c_W"] = c3.number_input("Caudal [kg/h] (si lo conocés)", value=18000.0, min_value=0.0, step=100.0)
        c1, c2 = st.columns(2)
        v["c_Rd"] = c1.number_input("Factor de ensuciamiento requerido [m²K/W]", value=float(F["Rd"]),
                                    format="%.6f", step=0.00001, key="c_Rd")
        v["c_dP"] = c2.number_input("Pérdida de carga admisible [kPa]", value=float(F["dP_adm"] / 1e3), step=5.0,
                                    key="c_dP")
        st.caption("Las propiedades del agua se calculan automáticamente a la temperatura media.")

    with t_tubo:
        c1, c2, c3 = st.columns(3)
        v["Do"] = c1.number_input("Diámetro externo del tubo [mm]", value=float(K["Do"] * 1000), format="%.2f",
                                  step=0.05)
        v["Di"] = c2.number_input("Diámetro interno del tubo [mm]", value=float(K["Di"] * 1000), format="%.2f",
                                  step=0.05)
        v["L_max"] = c3.number_input("Longitud máxima del tubo [m]", value=float(K["L_max"]), step=0.1)
        c1, c2, c3 = st.columns(3)
        v["arreglo"] = c1.selectbox("Arreglo de tubos", ["triangular", "cuadrado"],
                                    format_func=lambda x: "Triangular (60°)" if x == "triangular" else "Cuadrado (90°)")
        v["Pt"] = c2.number_input("Paso entre tubos [mm]", value=float(K["Pt"] * 1000), format="%.2f", step=0.1)
        v["k_pared"] = c3.number_input("Conductividad del material del tubo [W/m·K]", value=float(K["k_pared"]),
                                       step=5.0)
        c1, c2, c3, c4 = st.columns(4)
        v["v_min"] = c1.number_input("Velocidad mínima en tubos [m/s]", value=float(K["v_min"]), step=0.1)
        v["v_max"] = c2.number_input("Velocidad máxima en tubos [m/s]", value=float(K["v_max"]), step=0.1)
        v["Ud_est"] = c3.number_input("Coeficiente global estimado [W/m²K]", value=float(D["Ud_est"]), step=50.0,
                                      help="Solo se usa para el prediseño inicial.")
        v["Ft_min"] = c4.number_input("Ft mínimo", value=float(D["Ft_min"]), step=0.01, format="%.2f")

    calcular = st.form_submit_button("Calcular diseño", type="primary")

# -----------------------------------------------------------------------------
# Cálculo
# -----------------------------------------------------------------------------
if calcular:
    errores = validar(v)
    if errores:
        st.session_state.pop("res", None)
        for e in errores:
            st.error(e)
    else:
        caso = construir_caso(v)
        log = []
        try:
            with st.spinner("Buscando la mejor configuración..."):
                bal, r = disenar(caso, log)
                notas = notas_criticas(caso, r)
                xlsx = excel_en_memoria(caso, bal, r, notas, log)
            st.session_state["res"] = {"caso": caso, "bal": bal, "r": r, "notas": notas, "log": log, "xlsx": xlsx}
        except ValueError as e:
            st.session_state.pop("res", None)
            st.error(f"No se pudo calcular: {e}")
        except Exception as e:  # error inesperado: se informa sin romper la aplicación
            st.session_state.pop("res", None)
            st.error(f"Ocurrió un error inesperado durante el cálculo: {e}")

# -----------------------------------------------------------------------------
# Resultados (se conservan al interactuar con la página)
# -----------------------------------------------------------------------------
res = st.session_state.get("res")
if res:
    caso, bal, r, notas, log = res["caso"], res["bal"], res["r"], res["notas"], res["log"]
    st.subheader("2. Resultados")

    if r["cumple"]:
        st.markdown(
            "<div class='veredicto ok'>✅ El diseño es factible"
            "<small>Cumple el factor de corrección Ft, el factor de ensuciamiento, la velocidad por tubos "
            "y las pérdidas de carga admisibles.</small></div>", unsafe_allow_html=True)
    else:
        malos = [n for n, x in r["viol"].items() if x > 0]
        st.markdown(
            "<div class='veredicto mal'>❌ No se encontró un diseño factible"
            f"<small>Restricciones que no se cumplen: {', '.join(malos)}. Se muestra la configuración que "
            "más se acerca. Probá con más longitud de tubo, mayor pérdida de carga admisible o menor "
            "factor de ensuciamiento.</small></div>", unsafe_allow_html=True)

    c = st.columns(4)
    c[0].metric("Diámetro interno del casco", f"{r['Ds']*1000:.0f} mm")
    c[1].metric("Tubos por casco", f"{r['Nt']}")
    c[2].metric("Superficie de intercambio", f"{r['A_total']:.2f} m²")
    c[3].metric("Carga térmica", f"{bal['Q']/1e3:,.0f} kW")
    c = st.columns(4)
    c[0].metric("Coef. global limpio (Uc)", f"{r['Uc']:,.0f} W/m²K")
    c[1].metric("Coef. global de diseño (Ud)", f"{r['Ud']:,.0f} W/m²K")
    c[2].metric("Exceso de área", f"{r['exceso']:.0f} %")
    c[3].metric("Caudal de agua", f"{bal['Wc']*3600:,.0f} kg/h")

    st.download_button("⬇️ Descargar hoja de especificaciones TEMA (Excel)", data=res["xlsx"],
                       file_name="Hoja_TEMA_condensador.xlsx", type="primary",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    tab_ver, tab_det, tab_obs, tab_log = st.tabs(["Verificaciones", "Detalle del equipo", "Observaciones",
                                                  "Registro de iteraciones"])

    with tab_ver:
        st.dataframe(tabla_verificaciones(caso, r), hide_index=True)

    with tab_det:
        k = caso["constructivo"]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Geometría**")
            st.dataframe(pd.DataFrame({
                "Dato": ["Carcasas en serie", "Tipo de equipo (TEMA)", "Diámetro interno del casco",
                         "Tubos (diámetro externo / calibre)", "Longitud de tubo", "Pasos por tubos",
                         "Arreglo y paso", "Espaciado de deflectores", "Cantidad de deflectores",
                         "Boquilla de entrada de vapor", "Boquillas de agua"],
                "Valor": [r["Ns"], caso["identificacion"]["tipo_TEMA"], f"{r['Ds']*1000:.0f} mm",
                          f"{k['Do']*1000:.2f} mm / BWG {bwg_de(k['Do'], k['Di'])}", f"{r['L']:.2f} m", r["n"],
                          f"{k['arreglo'].capitalize()}, {k['Pt']*1000:.2f} mm", f"{r['B']*1000:.0f} mm",
                          r["n_deflectores"], r["boq_vapor"][0], r["boq_tubos"][0]]}), hide_index=True)
        with c2:
            st.markdown("**Desempeño térmico e hidráulico**")
            st.dataframe(pd.DataFrame({
                "Dato": ["Coef. de película del vapor condensando (ho)", "Coef. de película del agua (hi)",
                         "Modelo usado para ho", "Diferencia media de temperatura (DMLT × Ft)",
                         "Velocidad del vapor en el casco", "Pérdida de carga en tubos (fricción / cabezales / boquillas)",
                         "Pérdida de carga en casco (haz / boquilla)", "Temperatura de pared exterior"],
                "Valor": [f"{r['ho']:,.0f} W/m²K", f"{r['hi']:,.0f} W/m²K", r["modelo_ho"], f"{r['dT_bal']:.1f} K",
                          f"{r['u_vapor_casco']:.1f} m/s",
                          f"{r['dP_tubos_fric']/1e3:.1f} / {r['dP_tubos_ret']/1e3:.1f} / "
                          f"{r['dP_tubos_noz']/1e3:.1f} kPa",
                          f"{r['dP_casco_haz']/1e3:.1f} / {r['dP_casco_noz']/1e3:.1f} kPa",
                          f"{r['Tw']:.1f} °C"]}), hide_index=True)
        st.markdown("**Zonas de intercambio**")
        st.dataframe(pd.DataFrame([{
            "Zona": z["nombre"], "Calor [kW]": round(z["Q"] / 1e3, 1), "DMLT [K]": round(z["dTml"], 1),
            "Ft": round(z["Ft"], 3), "ho [W/m²K]": round(z["ho"]), "Uc [W/m²K]": round(z["Uc"]),
            "Área limpia [m²]": round(z["A_limpia"], 2)} for z in r["zonas"]]), hide_index=True)

    with tab_obs:
        st.markdown("Observaciones de criterio de ingeniería sobre el equipo calculado:")
        for n in notas:
            st.markdown(f"- {n}")

    with tab_log:
        st.markdown("Decisiones que tomó el algoritmo, paso a paso:")
        st.code("\n".join(log), language="text")
