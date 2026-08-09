import streamlit as st
import pandas as pd
import streamlit.components.v1 as components
from datetime import datetime

# ==========================================
# 1. CONFIGURACIÓN INICIAL Y DATOS BASE
# ==========================================
st.set_page_config(
    page_title="Condominio Residencial",
    page_icon="🏢",
    layout="wide"
)

# Datos de los 13 apartamentos con sus alícuotas fijadas
APARTAMENTOS_INFO = {
    "1A": {"alicuota": 6.0, "propietario": "Propietario 1A", "pass": "apto1a123"},
    "1B": {"alicuota": 6.0, "propietario": "Propietario 1B", "pass": "apto1b123"},
    "2":  {"alicuota": 12.0, "propietario": "Propietario 2",  "pass": "apto2123"},
    "3A": {"alicuota": 6.0, "propietario": "Propietario 3A", "pass": "apto3a123"},
    "3B": {"alicuota": 6.0, "propietario": "Propietario 3B", "pass": "apto3b123"},
    "4A": {"alicuota": 6.0, "propietario": "Propietario 4A", "pass": "apto4a123"},
    "4B": {"alicuota": 6.0, "propietario": "Propietario 4B", "pass": "apto4b123"},
    "5A": {"alicuota": 6.0, "propietario": "Propietario 5A", "pass": "apto5a123"},
    "5B": {"alicuota": 6.0, "propietario": "Propietario 5B", "pass": "apto5b123"},
    "6A": {"alicuota": 6.0, "propietario": "Propietario 6A", "pass": "apto6a123"},
    "6B": {"alicuota": 6.0, "propietario": "Propietario 6B", "pass": "apto6b123"},
    "7":  {"alicuota": 12.0, "propietario": "Propietario 7",  "pass": "apto7123"},
    "PH": {"alicuota": 16.0, "propietario": "Propietario PH", "pass": "penth123"}
}

PASS_ADMIN = "admin123"

# Inicializar datos en la sesión
if "df_pagos" not in st.session_state:
    st.session_state.df_pagos = pd.DataFrame([
        {"Recibo": "REC-001", "Apto": "1A", "Fecha": "2026-07-01", "Concepto": "Cuota Condominio Julio", "Monto ($)": 120.0, "Estado": "Pagado"},
        {"Recibo": "REC-002", "Apto": "2",  "Fecha": "2026-07-01", "Concepto": "Cuota Condominio Julio", "Monto ($)": 240.0, "Estado": "Pagado"},
        {"Recibo": "REC-003", "Apto": "PH", "Fecha": "2026-07-01", "Concepto": "Cuota Condominio Julio", "Monto ($)": 320.0, "Estado": "Pendiente"},
    ])

if "df_proveedores" not in st.session_state:
    st.session_state.df_proveedores = pd.DataFrame([
        {"Factura": "FAC-101", "Proveedor": "Servicio Limpieza", "Fecha": "2026-07-05", "Concepto": "Mantenimiento mensual", "Monto ($)": 450.0},
        {"Factura": "FAC-102", "Proveedor": "Compañía Eléctrica", "Fecha": "2026-07-10", "Concepto": "Luz áreas comunes", "Monto ($)": 180.0},
    ])


# ==========================================
# 2. FUNCIONES DE IMPRESIÓN Y EXPORTACIÓN
# ==========================================
def boton_imprimir_navegador():
    """Genera un botón HTML que abre el cuadro de impresión nativo del navegador."""
    components.html(
        """
        <button onclick="window.print()" style="
            background-color: #28a745;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            font-size: 15px;
            font-weight: bold;
            width: 100%;
            margin-top: 10px;
        ">
            🖨️ Imprimir / Guardar como PDF
        </button>
        """,
        height=60
    )

def conversion_csv(df):
    """Convierte un DataFrame a formato CSV para descarga directa."""
    return df.to_csv(index=False).encode('utf-8')


# ==========================================
# 3. SISTEMA DE LOGIN Y SESIÓN
# ==========================================
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.rol = None
    st.session_state.usuario_apto = None

def login():
    st.title("🏢 Acceso al Condominio")
    rol = st.radio("Selecciona tu perfil de acceso:", ["Propietario / Vecino", "Administrador"])
    
    if rol == "Propietario / Vecino":
        apto = st.selectbox("Apartamento:", list(APARTAMENTOS_INFO.keys()))
        clave = st.text_input("Contraseña del Apartamento:", type="password")
        
        if st.button("Iniciar Sesión"):
            if clave == APARTAMENTOS_INFO[apto]["pass"]:
                st.session_state.autenticado = True
                st.session_state.rol = "Propietario"
                st.session_state.usuario_apto = apto
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
                
    else:  # Administrador
        clave_admin = st.text_input("Contraseña de Administración:", type="password")
        if st.button("Iniciar Sesión como Administrador"):
            if clave_admin == PASS_ADMIN:
                st.session_state.autenticado = True
                st.session_state.rol = "Administrador"
                st.rerun()
            else:
                st.error("Contraseña de administrador incorrecta.")

if not st.session_state.autenticado:
    login()
    st.stop()


# ==========================================
# 4. PANEL DE CONTROL (USUARIO AUTENTICADO)
# ==========================================
st.sidebar.title("🏢 Edificio Residencial")
st.sidebar.write(f"**Rol activo:** {st.session_state.rol}")

if st.session_state.rol == "Propietario":
    st.sidebar.write(f"**Apartamento:** {st.session_state.usuario_apto}")

if st.sidebar.button("Cerrar Sesión"):
    st.session_state.autenticado = False
    st.rerun()

# ------------------------------------------
# VISTA: PROPIETARIO
# ------------------------------------------
if st.session_state.rol == "Propietario":
    apto = st.session_state.usuario_apto
    info = APARTAMENTOS_INFO[apto]
    
    st.title(f"🏠 Panel del Apartamento {apto}")
    st.caption(f"Propietario: {info['propietario']} | Alícuota asignada: {info['alicuota']}%")

    st.subheader("📋 Mi Historial de Pagos y Recibos")
    
    # Filtrar datos correspondientes solo al apartamento logueado
    df_mi_apto = st.session_state.df_pagos[st.session_state.df_pagos["Apto"] == apto]
    
    st.dataframe(df_mi_apto, use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        boton_imprimir_navegador()
    with col2:
        st.download_button(
            label="📊 Descargar Histórico (CSV / Excel)",
            data=conversion_csv(df_mi_apto),
            file_name=f"Historico_Apto_{apto}.csv",
            mime="text/csv",
            use_container_width=True
        )

# ------------------------------------------
# VISTA: ADMINISTRADOR
# ------------------------------------------
else:
    st.title("⚙️ Panel de Administración")
    
    tab1, tab2, tab3 = st.tabs(["📊 Pagos de Propietarios", "🚚 Pagos a Proveedores", "➕ Registrar Pago"])

    # TAB 1: Pagos de Propietarios
    with tab1:
        st.subheader("Histórico de Pagos de Apartamentos")
        
        filtro_apto = st.selectbox("Filtrar por Apartamento:", ["Todos"] + list(APARTAMENTOS_INFO.keys()))
        
        if filtro_apto == "Todos":
            df_admin_pagos = st.session_state.df_pagos.copy()
        else:
            df_admin_pagos = st.session_state.df_pagos[st.session_state.df_pagos["Apto"] == filtro_apto]

        st.dataframe(df_admin_pagos, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            boton_imprimir_navegador()
        with col2:
            st.download_button(
                label="📊 Descargar Reporte (CSV / Excel)",
                data=conversion_csv(df_admin_pagos),
                file_name=f"Reporte_Pagos_{filtro_apto}.csv",
                mime="text/csv",
                use_container_width=True
            )

    # TAB 2: Pagos a Proveedores
    with tab2:
        st.subheader("Egresos y Pagos a Proveedores")
        st.dataframe(st.session_state.df_proveedores, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            boton_imprimir_navegador()
        with col2:
            st.download_button(
                label="📊 Descargar Proveedores (CSV / Excel)",
                data=conversion_csv(st.session_state.df_proveedores),
                file_name="Reporte_Proveedores.csv",
                mime="text/csv",
                use_container_width=True
            )

    # TAB 3: Registrar Nuevo Pago
    with tab3:
        st.subheader("Registrar Pago de Propietario")
        with st.form("form_pago"):
            recibo = f"REC-00{len(st.session_state.df_pagos) + 1}"
            apto_pago = st.selectbox("Apartamento", list(APARTAMENTOS_INFO.keys()))
            fecha_pago = st.date_input("Fecha")
            concepto_pago = st.text_input("Concepto", value="Gastos Comunes")
            monto_pago = st.number_input("Monto ($)", min_value=0.0, step=10.0)
            estado_pago = st.selectbox("Estado", ["Pagado", "Pendiente"])
            
            submit = st.form_submit_button("Guardar Registro")
            if submit:
                nuevo_pago = {
                    "Recibo": recibo,
                    "Apto": apto_pago,
                    "Fecha": str(fecha_pago),
                    "Concepto": concepto_pago,
                    "Monto ($)": monto_pago,
                    "Estado": estado_pago
                }
                st.session_state.df_pagos = pd.concat(
                    [st.session_state.df_pagos, pd.DataFrame([nuevo_pago])], 
                    ignore_index=True
                )
                st.success(f"¡Pago {recibo} registrado con éxito!")
                st.rerun()
