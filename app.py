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
    return pd.DataFrame()

def update_propietario(apto, prop, tel):
    url = f"{SUPABASE_URL}/rest/v1/propietarios?apartamento=eq.{urllib.parse.quote(apto)}"
    payload = {"propietario": prop, "telefono": tel}
    requests.patch(url, headers=HEADERS, json=payload)

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
    requests.post(url, headers=HEADERS, json=payload)

def delete_gasto(gasto_id):
    url = f"{SUPABASE_URL}/rest/v1/gastos?id=eq.{gasto_id}"
    requests.delete(url, headers=HEADERS)

def get_pagos(periodo):
    url = f"{SUPABASE_URL}/rest/v1/pagos?periodo=eq.{urllib.parse.quote(periodo)}&select=*&order=fecha.desc"
    resp = requests.get(url, headers=HEADERS)
    if resp.status_code == 200:
        return pd.DataFrame(resp.json())
    return pd.DataFrame()

def add_pago(periodo, apto, fecha, referencia, banco, monto):
    url = f"{SUPABASE_URL}/rest/v1/pagos"
    payload = {
        "periodo": periodo,
        "apartamento": apto,
        "fecha": str(fecha),
        "referencia": referencia,
        "banco": banco,
        "monto": float(monto),
        "estatus": "Pendiente"
    }
    requests.post(url, headers=HEADERS, json=payload)

def update_estatus_pago(pago_id, nuevo_estatus):
    url = f"{SUPABASE_URL}/rest/v1/pagos?id=eq.{pago_id}"
    requests.patch(url, headers=HEADERS, json={"estatus": nuevo_estatus})

# --- BARRA LATERAL: ROL DE USUARIO ---
st.sidebar.title("🔐 Control de Acceso")
rol = st.sidebar.radio("Iniciar sesión como:", ["Propietario", "Administrador"])

admin_autenticado = False
if rol == "Administrador":
    clave = st.sidebar.text_input("Contraseña de Admin", type="password")
    if clave == "roble2026":  # Contraseña configurable
        admin_autenticado = True
        st.sidebar.success("🔑 Acceso concedido")
    else:
        if clave:
            st.sidebar.error("❌ Contraseña incorrecta")

# --- ENCABEZADO E INFORMACIÓN DEL EDIFICIO ---
st.title("🏢 Residencias El Roble")
st.markdown("**Sistema Integrado de Administración y Gestión de Condominio**")

col_img, col_info = st.columns([1, 2])
with col_img:
    st.image("https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=400&q=80", caption="Residencias El Roble", use_container_width=True)

with col_info:
    st.info("""
    📍 **Dirección:** Av. Principal El Roble, Edificio Residencias El Roble.
    
    💳 **Datos Bancarios para Pagos:**
    * **Banco:** Banesco (0134)
    * **Cuenta:** 0134-0000-00-0000000000
    * **RIF / C.I.:** J-12345678-0
    * **Pago Móvil:** 0412-0000000 / C.I. 12.345.678
    """)

st.markdown("---")

# --- VISTA PROPIETARIO ---
if rol == "Propietario":
    st.header("👤 Portal del Propietario")
    
    props_df = get_propietarios()
    if props_df.empty:
        st.warning("Cargando directorio de apartamentos...")
    else:
        apto_sel = st.selectbox("Seleccione su Apartamento:", props_df["apartamento"].tolist())
        periodo_sel = st.text_input("Período a consultar", value=f"{date.today().strftime('%B %Y').capitalize()}")
        
        prop_info = props_df[props_df["apartamento"] == apto_sel].iloc[0]
        gastos_df = get_gastos(periodo_sel)
        
        tab1, tab2 = st.tabs(["📄 Mi Aviso de Cobro", "📲 Reportar Pago"])
        
        with tab1:
            if gastos_df.empty:
                st.info("No hay gastos registrados para este período aún.")
            else:
                gastos_df["monto"] = gastos_df["monto"].astype(float)
                total_comun = gastos_df[gastos_df["tipo"] == "Común"]["monto"].sum()
                alicuota = float(prop_info["alicuota"])
                cuota_comun = total_comun * alicuota
                no_comunes_apto = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto_sel)]["monto"].sum()
                total_a_pagar = cuota_comun + no_comunes_apto
                
                st.markdown(f"### Recibo para Apto {apto_sel} - {periodo_sel}")
                st.write(f"**Propietario:** {prop_info.get('propietario') or 'No registrado'}")
                st.write(f"**Alícuota:** {alicuota*100:.1f}%")
                
                c1, c2, c3 = st.columns(3)
                c1.metric("Total Gastos Edificio", f"${total_comun:,.2f}")
                c2.metric("Su Cuota Común", f"${cuota_comun:,.2f}")
                c3.metric("TOTAL A PAGAR", f"${total_a_pagar:,.2f}")
                
                recibo_texto = (
                    f"🏢 *RESIDENCIAS EL ROBLE*\n"
                    f"📄 *Aviso de Cobro - {periodo_sel}*\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👤 *Propietario:* {prop_info.get('propietario') or 'N/A'}\n"
                    f"🏠 *Apartamento:* {apto_sel} (Alícuota: {alicuota*100:.1f}%)\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔹 *Total Gastos Comunes Edif:* ${total_comun:,.2f}\n"
                    f"🔹 *Su Cuota Común ({alicuota*100:.1f}%):* ${cuota_comun:,.2f}\n"
                )
                if no_comunes_apto > 0:
                    recibo_texto += f"🔹 *Gastos Propios / No Comunes:* ${no_comunes_apto:,.2f}\n"
                recibo_texto += f"━━━━━━━━━━━━━━━━━━━━\n💰 *TOTAL A PAGAR:* ${total_a_pagar:,.2f}\n━━━━━━━━━━━━━━━━━━━━"
                
                st.text_area("Vista previa de su recibo:", value=recibo_texto, height=200)

        with tab2:
            st.markdown("### 📤 Reportar Transferencia / Pago Móvil")
            with st.form("form_pago"):
                fecha_p = st.date_input("Fecha del pago", value=date.today())
                banco_p = st.text_input("Banco de origen")
                ref_p = st.text_input("Número de Referencia")
                monto_p = st.number_input("Monto pagado ($)", min_value=0.0, step=0.01, format="%.2f")
                
                submit_pago = st.form_submit_button("Enviar Reporte de Pago")
                if submit_pago:
                    if ref_p and monto_p > 0:
                        add_pago(periodo_sel, apto_sel, fecha_p, ref_p, banco_p, monto_p)
                        st.success("✅ Reporte de pago registrado exitosamente. Queda pendiente de aprobación por el administrador.")
                        st.rerun()
                    else:
                        st.error("Por favor ingrese la referencia y un monto válido.")

            # Estado de pagos reportados por el propietario
            pagos_df = get_pagos(periodo_sel)
            if not pagos_df.empty:
                mis_pagos = pagos_df[pagos_df["apartamento"] == apto_sel]
                if not mis_pagos.empty:
                    st.markdown("#### Historial de Reportes en este período")
                    st.dataframe(mis_pagos[["fecha", "banco", "referencia", "monto", "estatus"]], use_container_width=True)

# --- VISTA ADMINISTRADOR ---
elif rol == "Administrador":
    if not admin_autenticado:
        st.warning("🔒 Por favor ingrese la contraseña de administrador en el menú lateral para continuar.")
    else:
        st.header("⚙️ Panel de Administración")
        
        menu_admin = st.selectbox("Módulo de Trabajo:", [
            "1. Aprobar / Revisar Pagos Reportados",
            "2. Registro de Gastos", 
            "3. Directorio de Propietarios", 
            "4. Envío Masivo de Recibos"
        ])

        # --- 1. APROBAR PAGOS ---
        if menu_admin == "1. Aprobar / Revisar Pagos Reportados":
            st.markdown("### 📥 Pagos Reportados por Propietarios")
            periodo_admin = st.text_input("Período a revisar", value=f"{date.today().strftime('%B %Y').capitalize()}")
            
            pagos_df = get_pagos(periodo_admin)
            if pagos_df.empty:
                st.info("No hay pagos reportados registrados para este período.")
            else:
                st.dataframe(pagos_df[["id", "apartamento", "fecha", "banco", "referencia", "monto", "estatus"]], use_container_width=True)
                
                st.markdown("---")
                st.markdown("#### Gestionar Estatus de Pago")
                col_p1, col_p2, col_p3 = st.columns(3)
                with col_p1:
                    pago_id_sel = st.number_input("ID del Pago", min_value=0, step=1)
                with col_p2:
                    if st.button("✅ Aprobar Pago", type="primary"):
                        if pago_id_sel in pagos_df["id"].values:
                            update_estatus_pago(pago_id_sel, "Aprobado")
                            st.success(f"Pago #{pago_id_sel} APROBADO.")
                            st.rerun()
                        else:
                            st.error("ID de pago no encontrado.")
                with col_p3:
                    if st.button("❌ Rechazar Pago"):
                        if pago_id_sel in pagos_df["id"].values:
                            update_estatus_pago(pago_id_sel, "Rechazado")
                            st.warning(f"Pago #{pago_id_sel} RECHAZADO.")
                            st.rerun()
                        else:
                            st.error("ID de pago no encontrado.")

        # --- 2. REGISTRO DE GASTOS ---
        elif menu_admin == "2. Registro de Gastos":
            st.markdown("### 📝 Registrar Nuevo Gasto del Edificio")
            
            col1, col2 = st.columns(2)
            with col1:
                periodo = st.text_input("Período", value=f"{date.today().strftime('%B %Y').capitalize()}")
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
                    st.success("✅ Gasto registrado exitosamente.")
                    st.rerun()
                else:
                    st.error("Por favor complete todos los campos requeridos con un monto mayor a 0.")

            st.markdown("---")
            gastos_df = get_gastos(periodo)
            if not gastos_df.empty:
                cols_mostrar = [c for c in ["id", "fecha", "tipo", "apartamento", "proveedor", "concepto", "monto"] if c in gastos_df.columns]
                st.dataframe(gastos_df[cols_mostrar], use_container_width=True)
                
                del_id = st.number_input("ID del gasto a eliminar", min_value=0, step=1)
                if st.button("Eliminar Gasto"):
                    if del_id in gastos_df["id"].values:
                        delete_gasto(del_id)
                        st.warning(f"Gasto #{del_id} eliminado.")
                        st.rerun()

        # --- 3. DIRECTORIO DE PROPIETARIOS ---
        elif menu_admin == "3. Directorio de Propietarios":
            st.markdown("### 👥 Directorio de Propietarios y Alícuotas")
            props_df = get_propietarios()
            
            if not props_df.empty:
                col_a, col_b = st.columns([1, 2])
                with col_a:
                    st.markdown("#### Editar Datos de Residente")
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
                    st.dataframe(props_display[["apartamento", "alicuota", "propietario", "telefono"]], use_container_width=True)

        # --- 4. ENVÍO MASIVO DE RECIBOS ---
        elif menu_admin == "4. Envío Masivo de Recibos":
            st.markdown("### 📊 Generación y Envío Directo de Recibos")
            periodo_sel = st.text_input("Período a calcular", value=f"{date.today().strftime('%B %Y').capitalize()}")
            
            gastos_df = get_gastos(periodo_sel)
            props_df = get_propietarios()
            
            if gastos_df.empty or props_df.empty:
                st.warning("No hay gastos registrados o información de propietarios disponible para este período.")
            else:
                gastos_df["monto"] = gastos_df["monto"].astype(float)
                total_comun = gastos_df[gastos_df["tipo"] == "Común"]["monto"].sum()
                
                apto_recibo = st.selectbox("Seleccionar Apartamento para ver y enviar:", props_df["apartamento"].tolist())
                prop_info = props_df[props_df["apartamento"] == apto_recibo].iloc[0]
                
                alicuota = float(prop_info["alicuota"])
                cuota_comun = total_comun * alicuota
                no_comunes_apto = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto_recibo)]["monto"].sum()
                total_a_pagar = cuota_comun + no_comunes_apto
                
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
                recibo_texto += f"━━━━━━━━━━━━━━━━━━━━\n💰 *TOTAL A PAGAR:* ${total_a_pagar:,.2f}\n━━━━━━━━━━━━━━━━━━━━\nPor favor remitir el comprobante de pago. ¡Gracias!"
                
                st.text_area("Vista previa:", value=recibo_texto, height=220)
                
                telefono_limpio = "".join(filter(str.isdigit, str(prop_info.get("telefono", ""))))
                if telefono_limpio:
                    mensaje_url = urllib.parse.quote(recibo_texto)
                    whatsapp_link = f"https://wa.me/{telefono_limpio}?text={mensaje_url}"
                    st.markdown(f'''
                        <a href="{whatsapp_link}" target="_blank">
                            <button style="background-color:#25D366; color:white; border:none; padding:10px 20px; border-radius:8px; cursor:pointer; font-size:16px;">
                                📲 Enviar Recibo por WhatsApp a Apto {apto_recibo}
                            </button>
                        </a>
                    ''', unsafe_allow_html=True)
                else:
                    st.info("💡 Registre el teléfono del propietario en el Directorio para habilitar el envío por WhatsApp.")
