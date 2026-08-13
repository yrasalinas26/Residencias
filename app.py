import streamlit as st
import pandas as pd
import requests
from datetime import date
import urllib.parse

st.set_page_config(page_title="Condominio Residencias El Roble", layout="wide")

# --- CONEXIÓN DIRECTA A SUPABASE (REST API) ---
SUPABASE_URL = st.secrets["SUPABASE_URL"].rstrip("/")
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

# --- FUNCIONES DE BASE DE DATOS ---
def get_propietarios():
    url = f"{SUPABASE_URL}/rest/v1/propietarios?select=*&order=apartamento.asc"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return pd.DataFrame(resp.json())
    st.error(f"Error al cargar propietarios: {resp.text}")
    return pd.DataFrame()

def update_propietario(apto, prop, tel):
    url = f"{SUPABASE_URL}/rest/v1/propietarios?apartamento=eq.{urllib.parse.quote(apto)}"
    payload = {"propietario": prop, "telefono": tel}
    resp = requests.patch(url, headers=HEADERS, json=payload)
    if resp.status_code not in [200, 204]:
        st.error(f"Error al actualizar: {resp.text}")

def get_gastos(periodo):
    url = f"{SUPABASE_URL}/rest/v1/gastos?periodo=eq.{urllib.parse.quote(periodo)}&select=*&order=fecha.desc"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return pd.DataFrame(resp.json())
    return pd.DataFrame()

def add_gasto(periodo, fecha, tipo, apartamento, proveedor, concepto, monto):
    url = f"{SUPABASE_URL}/rest/v1/gastos"
    payload = {
        "periodo": periodo,
        "fecha": str(fecha),
        "tipo": tipo,
        "apartamento": apartamento if tipo == "No Común" else "",
        "proveedor": proveedor,
        "concepto": concepto,
        "monto": float(monto)
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    if resp.status_code not in [200, 201]:
        st.error(f"Error al guardar gasto: {resp.text}")

def delete_gasto(gasto_id):
    url = f"{SUPABASE_URL}/rest/v1/gastos?id=eq.{gasto_id}"
    resp = requests.delete(url, headers=HEADERS)
    if resp.status_code not in [200, 204]:
        st.error(f"Error al eliminar: {resp.text}")

# --- INTERFAZ ---
st.title("🏢 Residencias El Roble")
st.subheader("Sistema de Administración y Condominio")

menu = st.sidebar.selectbox("Seleccionar módulo", [
    "1. Registro de Gastos", 
    "2. Directorio de Propietarios", 
    "3. Previsualización y Envío de Recibos"
])

# --- 1. REGISTRO DE GASTOS ---
if menu == "1. Registro de Gastos":
    st.markdown("### 📝 Registrar Nuevo Gasto")
    
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período (Ej: Agosto 2026)", value=f"{date.today().strftime('%B %Y').capitalize()}")
        fecha = st.date_input("Fecha del gasto", value=date.today())
        tipo = st.selectbox("Tipo de gasto", ["Común", "No Común"])
        
        apto_gasto = ""
        if tipo == "No Común":
            props_df = get_propietarios()
            if not props_df.empty:
                apto_gasto = st.selectbox("Apartamento imputado", props_df["apartamento"].tolist())
            
    with col2:
        proveedor = st.text_input("Proveedor / Beneficiario")
        concepto = st.text_input("Concepto / Descripción del gasto")
        monto = st.number_input("Monto ($)", min_value=0.0, step=0.01, format="%.2f")

    if st.button("Guardar Gasto", type="primary"):
        if proveedor and concepto and monto > 0:
            add_gasto(periodo, fecha, tipo, apto_gasto, proveedor, concepto, monto)
            st.success("✅ Gasto registrado exitosamente en la nube.")
            st.rerun()
        else:
            st.error("Por favor complete todos los campos requeridos con un monto mayor a 0.")

    st.markdown("---")
    st.markdown(f"### 📋 Gastos registrados para el período: **{periodo}**")
    gastos_df = get_gastos(periodo)
    
    if not gastos_df.empty:
        cols_mostrar = [c for c in ["id", "fecha", "tipo", "apartamento", "proveedor", "concepto", "monto"] if c in gastos_df.columns]
        st.dataframe(gastos_df[cols_mostrar], use_container_width=True)
        
        del_id = st.number_input("ID del gasto a eliminar", min_value=0, step=1)
        if st.button("Eliminar Gasto"):
            if "id" in gastos_df.columns and del_id in gastos_df["id"].values:
                delete_gasto(del_id)
                st.warning(f"Gasto #{del_id} eliminado.")
                st.rerun()
            else:
                st.error("ID no encontrado en este período.")
    else:
        st.info("No hay gastos registrados para este período aún.")

# --- 2. DIRECTORIO DE PROPIETARIOS ---
elif menu == "2. Directorio de Propietarios":
    st.markdown("### 👥 Directorio de Propietarios y Alícuotas")
    props_df = get_propietarios()
    
    if not props_df.empty:
        col_a, col_b = st.columns([1, 2])
        
        with col_a:
            st.markdown("#### Editar Información")
            apto_sel = st.selectbox("Seleccionar Apartamento", props_df["apartamento"].tolist())
            curr_row = props_df[props_df["apartamento"] == apto_sel].iloc[0]
            
            nuevo_prop = st.text_input("Nombre del Propietario", value=curr_row.get("propietario", "") or "")
            nuevo_tel = st.text_input("Teléfono (Ej: 584121234567)", value=curr_row.get("telefono", "") or "")
            
            if st.button("Actualizar Propietario"):
                update_propietario(apto_sel, nuevo_prop, nuevo_tel)
                st.success(f"Datos del apto {apto_sel} actualizados.")
                st.rerun()
                
        with col_b:
            st.markdown("#### Lista de Apartamentos")
            props_display = props_df.copy()
            if "alicuota" in props_display.columns:
                props_display["alicuota"] = (props_display["alicuota"].astype(float) * 100).map("{:.1f}%".format)
            cols_p = [c for c in ["apartamento", "alicuota", "propietario", "telefono"] if c in props_display.columns]
            st.dataframe(props_display[cols_p], use_container_width=True)

# --- 3. PREVISUALIZACIÓN Y ENVÍO DE RECIBOS ---
elif menu == "3. Previsualización y Envío de Recibos":
    st.markdown("### 📊 Generación y Previsualización de Recibos")
    periodo_sel = st.text_input("Período a consultar", value=f"{date.today().strftime('%B %Y').capitalize()}")
    
    gastos_df = get_gastos(periodo_sel)
    props_df = get_propietarios()
    
    if gastos_df.empty:
        st.warning("No hay gastos registrados en este período para calcular recibos.")
    elif props_df.empty:
        st.warning("No se pudo obtener la información de propietarios.")
    else:
        gastos_df["monto"] = gastos_df["monto"].astype(float)
        total_comun = gastos_df[gastos_df["tipo"] == "Común"]["monto"].sum()
        
        st.markdown(f"#### Resumen General - Total Gastos Comunes: **${total_comun:,.2f}**")
        
        apto_recibo = st.selectbox("Ver Recibo para Apartamento:", props_df["apartamento"].tolist())
        prop_info = props_df[props_df["apartamento"] == apto_recibo].iloc[0]
        
        alicuota = float(prop_info["alicuota"])
        cuota_comun = total_comun * alicuota
        
        no_comunes_apto = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto_recibo)]["monto"].sum()
        total_a_pagar = cuota_comun + no_comunes_apto
        
        st.markdown("---")
        recibo_texto = (
            f"🏢 *RESIDENCIAS EL ROBLE*\n"
            f"📄 *Aviso de Cobro - {periodo_sel}*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Propietario:* {prop_info.get('propietario') or 'N/A'}\n"
            f"🏠 *Apartamento:* {apto_recibo} (Alícuota: {alicuota*100:.1f}%)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 *Total Gastos Comunes Edif:* ${total_comun:,.2f}\n"
            f"🔹 *Su Cuota Común ({alicuota*100:.1f}%):* ${cuota_comun:,.2f}\n"
        )
        if no_comunes_apto > 0:
            recibo_texto += f"🔹 *Gastos Propios / No Comunes:* ${no_comunes_apto:,.2f}\n"
            
        recibo_texto += (
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 *TOTAL A PAGAR:* ${total_a_pagar:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Por favor remitir el comprobante de pago. ¡Gracias!"
        )
        
        st.text_area("Vista previa del mensaje:", value=recibo_texto, height=260)
        
        telefono_limpio = "".join(filter(str.isdigit, str(prop_info.get("telefono", ""))))
        if telefono_limpio:
            mensaje_url = urllib.parse.quote(recibo_texto)
            whatsapp_link = f"https://wa.me/{telefono_limpio}?text={mensaje_url}"
            st.markdown(f'''
                <a href="{whatsapp_link}" target="_blank">
                    <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:8px; cursor:pointer; font-size:16px;">
                        📲 Enviar Recibo por WhatsApp
                    </button>
                </a>
            ''', unsafe_allow_html=True)
        else:
            st.info("💡 Asigne un número de teléfono en el Directorio para habilitar el botón de WhatsApp directo.")
