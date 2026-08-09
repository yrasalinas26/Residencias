import sqlite3
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import base64

# =============================================================================
# 1. CONFIGURACIÓN Y BASE DE DATOS
# =============================================================================

def conectar_db():
    return sqlite3.connect("condominio.db")

def inicializar_base_de_datos():
    conn = conectar_db()
    cursor = conn.cursor()

    # Tabla de Perfil de la Residencia
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS residencia (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            rif TEXT,
            direccion TEXT,
            logo_bytes BLOB
        )
    """)

    # Tabla de Usuarios Propietarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            apartamento TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)

    # Tabla de Administrador
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            usuario TEXT PRIMARY KEY,
            password TEXT NOT NULL
        )
    """)

    # Tabla de Gastos Mensuales (Comunes y No Comunes)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_ano TEXT NOT NULL,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL,
            tipo TEXT NOT NULL,          -- 'Común' o 'No Común'
            apto_destino TEXT DEFAULT ''  -- Si es No Común, se asigna a un apto específico
        )
    """)

    # Tabla de Reporte de Pagos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_reportados (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            apartamento TEXT NOT NULL,
            fecha TEXT NOT NULL,
            monto REAL NOT NULL,
            referencia TEXT NOT NULL,
            metodo TEXT NOT NULL,
            estado TEXT DEFAULT 'Pendiente'
        )
    """)

    # Datos por defecto
    cursor.execute("INSERT OR IGNORE INTO admin (usuario, password) VALUES (?, ?)", ("admin", "admin123"))
    cursor.execute("INSERT OR IGNORE INTO residencia (id, nombre, rif, direccion) VALUES (1, 'Residencias El Condominio', 'J-12345678-0', 'Av. Principal #123')")

    apartamentos = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
    for ap in apartamentos:
        cursor.execute("INSERT OR IGNORE INTO usuarios (apartamento, password) VALUES (?, ?)", (ap, "1234"))

    conn.commit()
    conn.close()

# =============================================================================
# 2. FUNCIONES DE LÓGICA Y DATOS
# =============================================================================

def obtener_alicuota(apartamento):
    if apartamento in ["2", "7"]:
        return 0.12
    elif apartamento == "PH":
        return 0.16
    else:
        return 0.06

def obtener_datos_residencia():
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT nombre, rif, direccion, logo_bytes FROM residencia WHERE id = 1")
    res = cursor.fetchone()
    conn.close()
    return res

def guardar_datos_residencia(nombre, rif, direccion, logo_bytes=None):
    conn = conectar_db()
    cursor = conn.cursor()
    if logo_bytes:
        cursor.execute("UPDATE residencia SET nombre=?, rif=?, direccion=?, logo_bytes=? WHERE id=1", (nombre, rif, direccion, logo_bytes))
    else:
        cursor.execute("UPDATE residencia SET nombre=?, rif=?, direccion=? WHERE id=1", (nombre, rif, direccion))
    conn.commit()
    conn.close()

def verificar_usuario(apartamento, password):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM usuarios WHERE apartamento = ?", (apartamento,))
    res = cursor.fetchone()
    conn.close()
    return res is not None and res[0] == password

def verificar_admin(usuario, password):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM admin WHERE usuario = ?", (usuario,))
    res = cursor.fetchone()
    conn.close()
    return res is not None and res[0] == password

def cambiar_password_propietario(apartamento, nueva_password):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET password = ? WHERE apartamento = ?", (nueva_password, apartamento))
    conn.commit()
    conn.close()

def guardar_reporte_pago(apartamento, fecha, monto, referencia, metodo):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO pagos_reportados (apartamento, fecha, monto, referencia, metodo) VALUES (?, ?, ?, ?, ?)", (apartamento, str(fecha), monto, referencia, metodo))
    conn.commit()
    conn.close()

def boton_imprimir_navegador():
    components.html("""
        <button onclick="window.print()" style="
            background-color: #28a745; color: white; padding: 10px 20px;
            border: none; border-radius: 5px; cursor: pointer;
            font-size: 15px; font-weight: bold; width: 100%; margin-top: 10px;">
            🖨️ Imprimir Recibo / Guardar como PDF
        </button>
    """, height=60)

# =============================================================================
# 3. INTERFAZ Y FLUJO DE LA APLICACIÓN
# =============================================================================

st.set_page_config(page_title="Gestión de Condominio", page_icon="🏢", layout="wide")
inicializar_base_de_datos()

if "rol" not in st.session_state:
    st.session_state["rol"] = None
if "usuario_logueado" not in st.session_state:
    st.session_state["usuario_logueado"] = None

# -----------------------------------------------------------------------------
# A. INICIO DE SESIÓN
# -----------------------------------------------------------------------------
if st.session_state["rol"] is None:
    st.title("🏢 Sistema de Gestión de Condominio")
    st.markdown("---")
    
    tipo_acceso = st.radio("Seleccione el tipo de usuario:", ["Propietario", "Administrador"], horizontal=True)

    if tipo_acceso == "Propietario":
        st.subheader("🔑 Acceso Propietarios")
        lista_apts = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
        apt_sel = st.selectbox("Seleccione su Apartamento:", lista_apts)
        clave_prop = st.text_input("Contraseña:", type="password", help="La contraseña por defecto es 1234")

        if st.button("Ingresar como Propietario"):
            if verificar_usuario(apt_sel, clave_prop):
                st.session_state["rol"] = "Propietario"
                st.session_state["usuario_logueado"] = apt_sel
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")

    else:
        st.subheader("🛡️ Acceso Administración")
        user_admin = st.text_input("Usuario Administrador:")
        clave_admin = st.text_input("Contraseña:", type="password")

        if st.button("Ingresar como Administrador"):
            if verificar_admin(user_admin, clave_admin):
                st.session_state["rol"] = "Administrador"
                st.session_state["usuario_logueado"] = user_admin
                st.rerun()
            else:
                st.error("Credenciales incorrectas.")

# -----------------------------------------------------------------------------
# B. PANEL DEL PROPIETARIO
# -----------------------------------------------------------------------------
elif st.session_state["rol"] == "Propietario":
    apt = st.session_state["usuario_logueado"]
    alicuota = obtener_alicuota(apt)
    nombre_res, rif_res, dir_res, logo_res = obtener_datos_residencia()

    col_t, col_b = st.columns([3, 1])
    with col_t:
        st.title(f"🏠 Panel Apt. {apt}")
    with col_b:
        if st.button("Cerrar Sesión"):
            st.session_state["rol"] = None
            st.session_state["usuario_logueado"] = None
            st.rerun()

    st.markdown("---")
    tab_recibos, tab_reporte, tab_historial, tab_seguridad = st.tabs(["📄 Recibo del Mes", "💳 Reportar Pago", "📋 Mis Pagos", "⚙️ Cambiar Contraseña"])

    with tab_recibos:
        # Encabezado del Recibo con datos de la Residencia
        col_logo, col_info = st.columns([1, 3])
        with col_logo:
            if logo_res:
                st.image(logo_res, width=130)
            else:
                st.write("🏢")
        with col_info:
            st.markdown(f"### **{nombre_res}**")
            st.write(f"**RIF:** {rif_res} | **Dirección:** {dir_res}")
            st.caption(f"**Apartamento:** {apt} | **Alícuota:** {alicuota*100:.0f}%")

        st.markdown("---")
        conn = conectar_db()
        df_gastos = pd.read_sql_query("SELECT mes_ano AS 'Mes/Año', concepto AS 'Concepto', tipo AS 'Tipo', monto AS 'Monto Total ($)', apto_destino AS 'Apto Destino' FROM gastos", conn)
        conn.close()

        if not df_gastos.empty:
            st.subheader("Detalle de Gastos del Mes")
            st.dataframe(df_gastos, use_container_width=True)

            # Cálculo individual del recibo
            gastos_comunes = df_gastos[df_gastos["Tipo"] == "Común"]["Monto Total ($)"].sum()
            gastos_no_comunes = df_gastos[(df_gastos["Tipo"] == "No Común") & (df_gastos["Apto Destino"] == apt)]["Monto Total ($)"].sum()

            cuota_comun = gastos_comunes * alicuota
            total_a_pagar = cuota_comun + gastos_no_comunes

            col1, col2, col3 = st.columns(3)
            col1.metric("Cuota Gastos Comunes", f"${cuota_comun:.2f}")
            col2.metric("Gastos No Comunes (Directos)", f"${gastos_no_comunes:.2f}")
            col3.metric("TOTAL A PAGAR", f"${total_a_pagar:.2f}")

            boton_imprimir_navegador()
        else:
            st.info("No hay gastos cargados en el sistema actualmente.")

    with tab_reporte:
        st.subheader("💳 Reportar Pago")
        with st.form("form_reporte", clear_on_submit=True):
            fecha = st.date_input("Fecha de Pago")
            monto = st.number_input("Monto Pagado ($)", min_value=0.01)
            referencia = st.text_input("Número de Referencia")
            metodo = st.selectbox("Método de Pago", ["Pago Móvil", "Transferencia", "Zelle", "Efectivo"])
            if st.form_submit_button("Enviar Reporte"):
                if referencia:
                    guardar_reporte_pago(apt, fecha, monto, referencia, metodo)
                    st.success("Pago reportado con éxito.")
                else:
                    st.error("Ingrese una referencia válida.")

    with tab_historial:
        st.subheader("📋 Historial de Pagos")
        conn = conectar_db()
        df_p = pd.read_sql_query("SELECT fecha, monto, referencia, metodo, estado FROM pagos_reportados WHERE apartamento = ?", conn, params=(apt,))
        conn.close()
        st.dataframe(df_p, use_container_width=True)

    with tab_seguridad:
        st.subheader("⚙️ Cambiar Contraseña")
        p_act = st.text_input("Contraseña Actual", type="password")
        p_new = st.text_input("Nueva Contraseña", type="password")
        p_cnf = st.text_input("Confirmar Nueva Contraseña", type="password")
        if st.button("Guardar Clave"):
            if verificar_usuario(apt, p_act) and len(p_new) >= 4 and p_new == p_cnf:
                cambiar_password_propietario(apt, p_new)
                st.success("Contraseña actualizada.")
            else:
                st.error("Verifique los datos ingresados.")

# -----------------------------------------------------------------------------
# C. PANEL DE ADMINISTRACIÓN
# -----------------------------------------------------------------------------
elif st.session_state["rol"] == "Administrador":
    col_t, col_b = st.columns([3, 1])
    with col_t:
        st.title("🛡️ Panel de Administración")
    with col_b:
        if st.button("Cerrar Sesión"):
            st.session_state["rol"] = None
            st.session_state["usuario_logueado"] = None
            st.rerun()

    st.markdown("---")
    tab_gastos, tab_datos, tab_pagos_admin = st.tabs(["➕ Gastos Comunes y No Comunes", "🏢 Datos de la Residencia / Logo", "📊 Pagos Reportados"])

    # 1. Registro de Gastos Comunes y No Comunes
    with tab_gastos:
        st.subheader("Cargar Nuevo Gasto")
        with st.form("form_gastos", clear_on_submit=True):
            mes = st.text_input("Mes y Año (Ej: Agosto 2026):")
            concepto = st.text_input("Concepto del Gasto:")
            monto = st.number_input("Monto ($):", min_value=0.01, step=5.0)
            tipo_gasto = st.radio("Tipo de Gasto:", ["Común", "No Común"], horizontal=True)
            
            lista_apts = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
            apto_destino = st.selectbox("Apartamento Destino (Solo si es No Común):", ["N/A"] + lista_apts)

            if st.form_submit_button("Guardar Gasto"):
                if mes and concepto and monto > 0:
                    apto_final = apto_destino if tipo_gasto == "No Común" else ""
                    conn = conectar_db()
                    cursor = conn.cursor()
                    cursor.execute("INSERT INTO gastos (mes_ano, concepto, monto, tipo, apto_destino) VALUES (?, ?, ?, ?, ?)", (mes, concepto, monto, tipo_gasto, apto_final))
                    conn.commit()
                    conn.close()
                    st.success("Gasto registrado exitosamente.")
                    st.rerun()
                else:
                    st.error("Por favor llene todos los campos requeridos.")

        st.markdown("---")
        st.subheader("Gastos Registrados")
        conn = conectar_db()
        df_g = pd.read_sql_query("SELECT id, mes_ano, concepto, tipo, monto, apto_destino FROM gastos ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(df_g, use_container_width=True)

    # 2. Configurar Nombre, RIF, Dirección y Logo
    with tab_datos:
        st.subheader("🏢 Configuración del Edificio y Recibo")
        nom_act, rif_act, dir_act, logo_act = obtener_datos_residencia()

        with st.form("form_edificio"):
            nombre_input = st.text_input("Nombre de la Residencia / Condominio:", value=nom_act)
            rif_input = st.text_input("RIF de la Residencia:", value=rif_act)
            direccion_input = st.text_area("Dirección Fiscal:", value=dir_act)
            logo_file = st.file_uploader("Cargar / Cambiar Logo (PNG, JPG)", type=["png", "jpg", "jpeg"])

            if st.form_submit_button("Actualizar Información"):
                bytes_logo = logo_file.read() if logo_file else None
                guardar_datos_residencia(nombre_input, rif_input, direccion_input, bytes_logo)
                st.success("¡Datos e imagen actualizados correctamente!")
                st.rerun()

    # 3. Pagos Reportados por Propietarios
    with tab_pagos_admin:
        st.subheader("Revisión de Pagos")
        conn = conectar_db()
        df_p_all = pd.read_sql_query("SELECT id, apartamento, fecha, monto, referencia, metodo, estado FROM pagos_reportados ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(df_p_all, use_container_width=True)
