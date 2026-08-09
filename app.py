import sqlite3
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import datetime
import urllib.parse
import io

# =============================================================================
# 1. CONFIGURACIÓN Y BASE DE DATOS
# =============================================================================

def conectar_db():
    return sqlite3.connect("condominio_v2.db")

def inicializar_base_de_datos():
    conn = conectar_db()
    cursor = conn.cursor()

    # 1. Tabla Residencia
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS residencia (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            rif TEXT,
            direccion TEXT,
            logo_bytes BLOB
        )
    """)

    # 2. Tabla Usuarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            apartamento TEXT PRIMARY KEY,
            password TEXT NOT NULL DEFAULT '1234'
        )
    """)

    # 3. Tabla Admin
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS admin (
            usuario TEXT PRIMARY KEY,
            password TEXT NOT NULL DEFAULT 'admin123'
        )
    """)

    # 4. Tabla Gastos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mes_ano TEXT NOT NULL,
            concepto TEXT NOT NULL,
            monto REAL NOT NULL,
            tipo TEXT NOT NULL,
            apto_destino TEXT DEFAULT ''
        )
    """)

    # 5. Tabla Pagos
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

    # 6. Tabla Proveedores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            servicio TEXT NOT NULL,
            telefono TEXT NOT NULL,
            nota TEXT DEFAULT ''
        )
    """)

    # Reparación y datos iniciales
    try:
        cursor.execute("INSERT OR IGNORE INTO admin (usuario, password) VALUES (?, ?)", ("admin", "admin123"))
    except sqlite3.OperationalError:
        cursor.execute("DROP TABLE IF EXISTS admin")
        cursor.execute("CREATE TABLE admin (usuario TEXT PRIMARY KEY, password TEXT NOT NULL DEFAULT 'admin123')")
        cursor.execute("INSERT OR IGNORE INTO admin (usuario, password) VALUES (?, ?)", ("admin", "admin123"))

    cursor.execute("INSERT OR IGNORE INTO residencia (id, nombre, rif, direccion) VALUES (1, 'Residencias El Condominio', 'J-12345678-0', 'Av. Principal #123')")

    apartamentos = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
    for ap in apartamentos:
        try:
            cursor.execute("INSERT OR IGNORE INTO usuarios (apartamento, password) VALUES (?, ?)", (ap, "1234"))
        except sqlite3.OperationalError:
            cursor.execute("DROP TABLE IF EXISTS usuarios")
            cursor.execute("CREATE TABLE usuarios (apartamento TEXT PRIMARY KEY, password TEXT NOT NULL DEFAULT '1234')")
            cursor.execute("INSERT OR IGNORE INTO usuarios (apartamento, password) VALUES (?, ?)", (ap, "1234"))

    conn.commit()
    conn.close()

# =============================================================================
# 2. LÓGICA DE NEGOCIO Y FUNCIONES
# =============================================================================

def obtener_alicuota(apartamento):
    if apartamento in ["2", "7"]:
        return 0.12  # 12%
    elif apartamento == "PH":
        return 0.16  # 16%
    else:
        return 0.06  # 6% para los 10 restantes

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

def eliminar_gasto(gasto_id):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM gastos WHERE id = ?", (gasto_id,))
    conn.commit()
    conn.close()

def actualizar_estado_pago(pago_id, nuevo_estado):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE pagos_reportados SET estado = ? WHERE id = ?", (nuevo_estado, pago_id))
    conn.commit()
    conn.close()

def guardar_proveedor(nombre, servicio, telefono, nota):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO proveedores (nombre, servicio, telefono, nota) VALUES (?, ?, ?, ?)", (nombre, servicio, telefono, nota))
    conn.commit()
    conn.close()

def eliminar_proveedor(prov_id):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM proveedores WHERE id = ?", (prov_id,))
    conn.commit()
    conn.close()

# -----------------------------------------------------------------------------
# GENERACIÓN DE REPORTES (SIN DEPENDENCIAS EXTERNAS) Y WHATSAPP
# -----------------------------------------------------------------------------

def generar_reporte_html(titulo, df_datos):
    tabla_html = df_datos.to_html(index=False, justify='left')
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{titulo}</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 30px; color: #333; }}
            h1 {{ text-align: center; color: #1E3A8A; margin-bottom: 20px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ border: 1px solid #cbd5e1; padding: 10px; text-align: left; }}
            th {{ background-color: #f1f5f9; font-weight: bold; }}
            tr:nth-child(even) {{ background-color: #f8fafc; }}
            .btn-container {{ text-align: center; margin-bottom: 20px; }}
            .print-btn {{ padding: 10px 20px; background-color: #2563eb; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 16px; font-weight: bold; }}
            @media print {{ .btn-container {{ display: none; }} }}
        </style>
    </head>
    <body>
        <div class="btn-container">
            <button class="print-btn" onclick="window.print()">🖨️ Imprimir / Guardar como PDF</button>
        </div>
        <h1>{titulo}</h1>
        {tabla_html}
    </body>
    </html>
    """
    return html_content

def boton_whatsapp(telefono, mensaje):
    msg_url = urllib.parse.quote(mensaje)
    link = f"https://wa.me/{telefono}?text={msg_url}"
    st.markdown(f'<a href="{link}" target="_blank" style="background-color:#25D366;color:white;padding:8px 15px;border-radius:5px;text-decoration:none;font-weight:bold;">📲 Enviar por WhatsApp</a>', unsafe_allow_html=True)

# =============================================================================
# 3. INTERFAZ DE USUARIO
# =============================================================================

st.set_page_config(page_title="Gestión de Condominio", page_icon="🏢", layout="wide")
inicializar_base_de_datos()

if "rol" not in st.session_state:
    st.session_state["rol"] = None
if "usuario_logueado" not in st.session_state:
    st.session_state["usuario_logueado"] = None

# A. INICIO DE SESIÓN
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

# B. PANEL DEL PROPIETARIO
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
    tab_recibos, tab_reporte, tab_historial, tab_prov, tab_seguridad = st.tabs(["📄 Recibo del Mes", "💳 Reportar Pago", "📋 Mis Pagos", "🛠️ Proveedores", "⚙️ Cambiar Contraseña"])

    with tab_recibos:
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

            gastos_comunes = df_gastos[df_gastos["Tipo"] == "Común"]["Monto Total ($)"].sum()
            gastos_no_comunes = df_gastos[(df_gastos["Tipo"] == "No Común") & (df_gastos["Apto Destino"] == apt)]["Monto Total ($)"].sum()

            cuota_comun = gastos_comunes * alicuota
            total_a_pagar = cuota_comun + gastos_no_comunes

            col1, col2, col3 = st.columns(3)
            col1.metric("Cuota Gastos Comunes", f"${cuota_comun:.2f}")
            col2.metric("Gastos No Comunes", f"${gastos_no_comunes:.2f}")
            col3.metric("TOTAL A PAGAR", f"${total_a_pagar:.2f}")

            html_recibo = generar_reporte_html(f"Recibo de Condominio - Apt {apt}", df_gastos)
            st.download_button("📥 Descargar / Imprimir Recibo", data=html_recibo, file_name=f"recibo_apt_{apt}.html", mime="text/html")
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
        st.subheader("📋 Historial de Mis Pagos")
        conn = conectar_db()
        df_p = pd.read_sql_query("SELECT fecha AS 'Fecha', monto AS 'Monto ($)', referencia AS 'Referencia', metodo AS 'Método', estado AS 'Estado' FROM pagos_reportados WHERE apartamento = ? ORDER BY id DESC", conn, params=(apt,))
        conn.close()
        st.dataframe(df_p, use_container_width=True)
        if not df_p.empty:
            html_pagos = generar_reporte_html(f"Historial de Pagos - Apt {apt}", df_p)
            st.download_button("📥 Descargar / Imprimir Historial", data=html_pagos, file_name=f"pagos_apt_{apt}.html", mime="text/html")

    with tab_prov:
        st.subheader("🛠️ Directorio de Proveedores y Servicios")
        conn = conectar_db()
        df_prov = pd.read_sql_query("SELECT nombre AS 'Nombre', servicio AS 'Servicio', telefono AS 'Teléfono', nota AS 'Nota' FROM proveedores", conn)
        conn.close()
        if not df_prov.empty:
            st.dataframe(df_prov, use_container_width=True)
        else:
            st.info("No hay proveedores registrados aún.")

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

# C. PANEL DE ADMINISTRACIÓN
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
    tab_gastos, tab_datos, tab_pagos_admin, tab_prov_admin = st.tabs(["➕ Gastos", "🏢 Edificio", "📊 Pagos Reportados", "🛠️ Proveedores"])

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

        st.markdown("---")
        conn = conectar_db()
        df_g = pd.read_sql_query("SELECT id AS 'ID', mes_ano AS 'Mes/Año', concepto AS 'Concepto', tipo AS 'Tipo', monto AS 'Monto ($)', apto_destino AS 'Apto' FROM gastos ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(df_g, use_container_width=True)

        if not df_g.empty:
            html_gastos = generar_reporte_html("Reporte General de Gastos", df_g)
            st.download_button("📥 Descargar / Imprimir Reporte de Gastos", data=html_gastos, file_name="reporte_gastos.html", mime="text/html")
            
            st.markdown("---")
            st.subheader("🗑️ Eliminar Gasto")
            opciones = {f"ID #{row['ID']}: {row['Concepto']} (${row['Monto ($)']})": row['ID'] for _, row in df_g.iterrows()}
            gasto_sel = st.selectbox("Seleccione gasto:", list(opciones.keys()))
            if st.button("❌ Eliminar Gasto"):
                eliminar_gasto(opciones[gasto_sel])
                st.success("Gasto eliminado.")
                st.rerun()

    with tab_datos:
        st.subheader("🏢 Datos de la Residencia")
        nom_act, rif_act, dir_act, logo_act = obtener_datos_residencia()
        with st.form("form_edificio"):
            nombre_input = st.text_input("Nombre de la Residencia:", value=nom_act)
            rif_input = st.text_input("RIF:", value=rif_act)
            direccion_input = st.text_area("Dirección Fiscal:", value=dir_act)
            logo_file = st.file_uploader("Logo (PNG, JPG)", type=["png", "jpg", "jpeg"])

            if st.form_submit_button("Actualizar Información"):
                bytes_logo = logo_file.read() if logo_file else None
                guardar_datos_residencia(nombre_input, rif_input, direccion_input, bytes_logo)
                st.success("Actualizado correctamente.")
                st.rerun()

    with tab_pagos_admin:
        st.subheader("⏳ Revisión de Pagos")
        conn = conectar_db()
        df_pendientes = pd.read_sql_query("SELECT id, apartamento, fecha, monto, referencia, metodo FROM pagos_reportados WHERE estado = 'Pendiente' ORDER BY id DESC", conn)
        conn.close()

        if not df_pendientes.empty:
            for _, row in df_pendientes.iterrows():
                with st.expander(f"📌 Pago ID #{row['id']} - Apt {row['apartamento']} | Monto: ${row['monto']:.2f}"):
                    st.write(f"**Fecha:** {row['fecha']} | **Ref:** {row['referencia']} | **Método:** {row['metodo']}")
                    col_ok, col_no = st.columns(2)
                    with col_ok:
                        if st.button(f"✅ Aprobar (#{row['id']})", key=f"ap_{row['id']}"):
                            actualizar_estado_pago(row['id'], 'Aprobado')
                            st.rerun()
                    with col_no:
                        if st.button(f"❌ Rechazar (#{row['id']})", key=f"rec_{row['id']}"):
                            actualizar_estado_pago(row['id'], 'Rechazado')
                            st.rerun()
        else:
            st.info("No hay pagos pendientes.")

        st.markdown("---")
        conn = conectar_db()
        df_todos_pagos = pd.read_sql_query("SELECT id AS 'ID', apartamento AS 'Apto', fecha AS 'Fecha', monto AS 'Monto ($)', referencia AS 'Ref', metodo AS 'Método', estado AS 'Estado' FROM pagos_reportados ORDER BY id DESC", conn)
        conn.close()
        st.dataframe(df_todos_pagos, use_container_width=True)
        if not df_todos_pagos.empty:
            html_todos_pagos = generar_reporte_html("Reporte General de Pagos", df_todos_pagos)
            st.download_button("📥 Descargar / Imprimir Reporte General de Pagos", data=html_todos_pagos, file_name="reporte_general_pagos.html", mime="text/html")

    with tab_prov_admin:
        st.subheader("🛠️ Administrar Proveedores y Servicios")
        with st.form("form_prov"):
            p_nombre = st.text_input("Nombre / Empresa:")
            p_servicio = st.text_input("Servicio (Ej: Plomería, Ascensores):")
            p_telefono = st.text_input("Teléfono (Ej: 584121234567):", help="Incluya código de país sin signo +")
            p_nota = st.text_input("Nota / Comentario:")
            if st.form_submit_button("Guardar Proveedor"):
                if p_nombre and p_telefono:
                    guardar_proveedor(p_nombre, p_servicio, p_telefono, p_nota)
                    st.success("Proveedor guardado.")
                    st.rerun()

        st.markdown("---")
        conn = conectar_db()
        df_prov_list = pd.read_sql_query("SELECT id, nombre, servicio, telefono, nota FROM proveedores", conn)
        conn.close()

        if not df_prov_list.empty:
            for _, row in df_prov_list.iterrows():
                col_p1, col_p2, col_p3 = st.columns([2, 1, 1])
                with col_p1:
                    st.write(f"**{row['nombre']}** ({row['servicio']}) - Tel: {row['telefono']}")
                with col_p2:
                    boton_whatsapp(row['telefono'], f"Hola {row['nombre']}, te escribo de la administración del condominio.")
                with col_p3:
                    if st.button(f"🗑️ Eliminar", key=f"del_prov_{row['id']}"):
                        eliminar_proveedor(row['id'])
                        st.rerun()
