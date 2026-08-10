import sqlite3
import pandas as pd
import streamlit as st
from datetime import datetime
import urllib.parse
import os

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

    # 2. Tabla Usuarios / Propietarios
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            apartamento TEXT PRIMARY KEY,
            nombre TEXT DEFAULT 'Propietario',
            telefono TEXT DEFAULT '',
            password TEXT NOT NULL DEFAULT '1234'
        )
    """)

    # Agregar columnas si venías de una versión anterior
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN nombre TEXT DEFAULT 'Propietario'")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN telefono TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass

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
            fecha TEXT DEFAULT CURRENT_DATE,
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

    cursor.execute("INSERT OR IGNORE INTO admin (usuario, password) VALUES (?, ?)", ("admin", "admin123"))
    cursor.execute("INSERT OR IGNORE INTO residencia (id, nombre, rif, direccion) VALUES (1, 'Residencias El Condominio', 'J-12345678-0', 'Av. Principal #123')")

    apartamentos = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
    for ap in apartamentos:
        cursor.execute("INSERT OR IGNORE INTO usuarios (apartamento, password, nombre, telefono) VALUES (?, ?, ?, ?)", (ap, "1234", f"Propietario Apt {ap}", ""))

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

def obtener_propietarios():
    conn = conectar_db()
    df = pd.read_sql_query("SELECT apartamento AS Apt, nombre AS Nombre, telefono AS Telefono FROM usuarios", conn)
    conn.close()
    return df

def actualizar_propietario(apto, nombre, telefono):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE usuarios SET nombre = ?, telefono = ? WHERE apartamento = ?", (nombre, telefono, apto))
    conn.commit()
    conn.close()

def verificar_usuario(apartamento, password):
    conn = conectar_db()
    cursor = conn.cursor()
    apt_clean = apartamento.strip().upper()
    cursor.execute("SELECT password FROM usuarios WHERE apartamento = ?", (apt_clean,))
    res = cursor.fetchone()
    conn.close()
    if res is not None and res[0] == password:
        return True, apt_clean
    return False, None

def verificar_admin(usuario, password):
    conn = conectar_db()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM admin WHERE usuario = ?", (usuario.strip(),))
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
# GENERACIÓN DE REPORTES Y WHATSAPP
# -----------------------------------------------------------------------------

def generar_recibo_general_html(nombre_edificio, rif, direccion, mes_cobro, df_gastos, df_resumen):
    tabla_gastos_html = df_gastos.to_html(index=False, justify='left')
    tabla_resumen_html = df_resumen.to_html(index=False, justify='left')
    total_gastos = df_gastos["Monto ($)"].sum()
    
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Recibo General de Condominio - {mes_cobro}</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 25px; color: #333; line-height: 1.4; }}
            .header {{ border-bottom: 2px solid #1E3A8A; padding-bottom: 10px; margin-bottom: 15px; }}
            .header h1 {{ color: #1E3A8A; margin: 0; font-size: 24px; }}
            .info-box {{ background-color: #f8fafc; border: 1px solid #cbd5e1; padding: 12px; border-radius: 6px; margin-bottom: 15px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; margin-bottom: 20px; }}
            th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; font-size: 14px; }}
            th {{ background-color: #f1f5f9; font-weight: bold; }}
            tr:nth-child(even) {{ background-color: #f8fafc; }}
            .total-box {{ text-align: right; font-size: 16px; font-weight: bold; color: #1E3A8A; margin-bottom: 20px; }}
            .btn-container {{ text-align: center; margin-bottom: 15px; }}
            .print-btn {{ padding: 10px 20px; background-color: #2563eb; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 15px; font-weight: bold; }}
            @media print {{ .btn-container {{ display: none; }} }}
        </style>
    </head>
    <body>
        <div class="btn-container"><button class="print-btn" onclick="window.print()">🖨️ Imprimir / Guardar PDF</button></div>
        <div class="header">
            <h1>🏢 {nombre_edificio}</h1>
            <p style="margin:2px 0;"><b>RIF:</b> {rif} | <b>Dirección:</b> {direccion}</p>
        </div>
        <div class="info-box">
            <p style="margin:2px 0;"><b>AVISO Y RECIBO GENERAL DE GASTOS DE CONDOMINIO</b></p>
            <p style="margin:2px 0;"><b>MES CORRESPONDIENTE:</b> {mes_cobro}</p>
            <p style="margin:2px 0;"><b>FECHA DE EMISIÓN:</b> {datetime.now().strftime('%d/%m/%Y')}</p>
        </div>
        <h3>1. Relación de Gastos del Mes</h3>
        {tabla_gastos_html}
        <div class="total-box">TOTAL GASTOS REGISTRADOS: ${total_gastos:.2f}</div>
        <h3>2. Distribución de Pagos por Alicuota y Apartamento</h3>
        {tabla_resumen_html}
    </body>
    </html>
    """

def generar_recibo_html(nombre_edificio, rif, direccion, mes_cobro, apto, alicuota, df_gastos, total_pagar):
    tabla_html = df_gastos.to_html(index=False, justify='left')
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Recibo de Cobro - Apt {apto}</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 25px; color: #333; line-height: 1.4; }}
            .header {{ border-bottom: 2px solid #1E3A8A; padding-bottom: 10px; margin-bottom: 15px; }}
            .header h1 {{ color: #1E3A8A; margin: 0; font-size: 24px; }}
            .info-box {{ background-color: #f8fafc; border: 1px solid #cbd5e1; padding: 12px; border-radius: 6px; margin-bottom: 15px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ border: 1px solid #cbd5e1; padding: 8px; text-align: left; font-size: 14px; }}
            th {{ background-color: #f1f5f9; font-weight: bold; }}
            tr:nth-child(even) {{ background-color: #f8fafc; }}
            .total-box {{ margin-top: 15px; text-align: right; font-size: 18px; font-weight: bold; color: #1E3A8A; }}
            .btn-container {{ text-align: center; margin-bottom: 15px; }}
            .print-btn {{ padding: 10px 20px; background-color: #2563eb; color: white; border: none; border-radius: 5px; cursor: pointer; font-size: 15px; font-weight: bold; }}
            @media print {{ .btn-container {{ display: none; }} }}
        </style>
    </head>
    <body>
        <div class="btn-container"><button class="print-btn" onclick="window.print()">🖨️ Imprimir / Guardar PDF</button></div>
        <div class="header">
            <h1>🏢 {nombre_edificio}</h1>
            <p style="margin:2px 0;"><b>RIF:</b> {rif} | <b>Dirección:</b> {direccion}</p>
        </div>
        <div class="info-box">
            <p style="margin:2px 0;"><b>MES CORRESPONDIENTE:</b> {mes_cobro}</p>
            <p style="margin:2px 0;"><b>APARTAMENTO:</b> {apto} | <b>ALÍCUOTA:</b> {alicuota*100:.0f}%</p>
            <p style="margin:2px 0;"><b>FECHA DE EMISIÓN:</b> {datetime.now().strftime('%d/%m/%Y')}</p>
        </div>
        <h3>Detalle de Gastos</h3>
        {tabla_html}
        <div class="total-box">TOTAL A CANCELAR: ${total_pagar:.2f}</div>
    </body>
    </html>
    """

def generar_reporte_html(titulo, df_datos, subtitulo=""):
    tabla_html = df_datos.to_html(index=False, justify='left')
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{titulo}</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 30px; color: #333; }}
            h1 {{ text-align: center; color: #1E3A8A; margin-bottom: 5px; }}
            h3 {{ text-align: center; color: #4b5563; margin-top: 0px; margin-bottom: 20px; }}
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
        <div class="btn-container"><button class="print-btn" onclick="window.print()">🖨️ Imprimir / Guardar como PDF</button></div>
        <h1>{titulo}</h1>
        {f'<h3>{subtitulo}</h3>' if subtitulo else ''}
        {tabla_html}
    </body>
    </html>
    """

def boton_whatsapp(telefono, mensaje, texto_boton="📲 Enviar por WhatsApp"):
    msg_url = urllib.parse.quote(mensaje)
    tel_clean = ''.join(filter(str.isdigit, str(telefono))) if telefono else ""
    if tel_clean:
        link = f"https://wa.me/{tel_clean}?text={msg_url}"
    else:
        link = f"https://api.whatsapp.com/send?text={msg_url}"
    st.markdown(f'<a href="{link}" target="_blank" style="background-color:#25D366;color:white;padding:8px 15px;border-radius:5px;text-decoration:none;font-weight:bold;display:inline-block;margin-top:5px;">{texto_boton}</a>', unsafe_allow_html=True)

# =============================================================================
# 3. INTERFAZ DE USUARIO
# =============================================================================

st.set_page_config(page_title="Gestión de Condominio", page_icon="logo.jpg", layout="wide")
inicializar_base_de_datos()

if "rol" not in st.session_state:
    st.session_state["rol"] = None
if "usuario_logueado" not in st.session_state:
    st.session_state["usuario_logueado"] = None

# A. INICIO DE SESIÓN
if st.session_state["rol"] is None:
    col_l1, col_l2, col_l3 = st.columns([1, 1, 1])
    with col_l2:
        if os.path.exists("logo.jpg"):
            st.image("logo.jpg", use_container_width=True)
        elif os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)

    st.title("🏢 Sistema de Gestión de Condominio")
    st.markdown("---")
    tipo_acceso = st.radio("Seleccione el tipo de usuario:", ["Propietario", "Administrador"], horizontal=True)

    if tipo_acceso == "Propietario":
        st.subheader("🔑 Acceso Propietarios")
        apt_input = st.text_input("Apartamento (Ej: 1A, 2, PH):", value="", placeholder="Escriba su apartamento")
        clave_prop = st.text_input("Contraseña:", type="password", value="", placeholder="Ingrese su contraseña")

        if st.button("Ingresar como Propietario"):
            if apt_input and clave_prop:
                valido, apt_confirmado = verificar_usuario(apt_input, clave_prop)
                if valido:
                    st.session_state["rol"] = "Propietario"
                    st.session_state["usuario_logueado"] = apt_confirmado
                    st.rerun()
                else:
                    st.error("Apartamento o contraseña incorrecta.")
            else:
                st.warning("Por favor complete ambos campos.")
    else:
        st.subheader("🛡️ Acceso Administración")
        user_admin = st.text_input("Usuario Administrador:", value="", placeholder="Escriba su usuario de administración")
        clave_admin = st.text_input("Contraseña:", type="password", value="", placeholder="Ingrese su contraseña")

        if st.button("Ingresar como Administrador"):
            if user_admin and clave_admin:
                if verificar_admin(user_admin, clave_admin):
                    st.session_state["rol"] = "Administrador"
                    st.session_state["usuario_logueado"] = user_admin
                    st.rerun()
                else:
                    st.error("Credenciales incorrectas.")
            else:
                st.warning("Por favor complete ambos campos.")

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
    tab_recibos, tab_reporte, tab_historial, tab_seguridad = st.tabs(["📄 Recibo del Mes", "💳 Reportar Pago", "📋 Mis Pagos", "⚙️ Cambiar Contraseña"])

    with tab_recibos:
        col_logo, col_info = st.columns([1, 3])
        with col_logo:
            if logo_res:
                st.image(logo_res, width=130)
            elif os.path.exists("logo.jpg"):
                st.image("logo.jpg", width=130)
        with col_info:
            st.markdown(f"### **{nombre_res}**")
            st.write(f"**RIF:** {rif_res} | **Dirección:** {dir_res}")
            st.caption(f"**Apartamento:** {apt} | **Alícuota:** {alicuota*100:.0f}%")

        st.markdown("---")
        conn = conectar_db()
        df_gastos = pd.read_sql_query("SELECT mes_ano AS 'Mes/Año', concepto AS 'Concepto', tipo AS 'Tipo', monto AS 'Monto Total ($)', apto_destino AS 'Apto Destino' FROM gastos", conn)
        conn.close()

        if not df_gastos.empty:
            mes_actual = df_gastos["Mes/Año"].iloc[-1]
            st.subheader(f"📄 Recibo de Cobro - {mes_actual}")
            st.dataframe(df_gastos, use_container_width=True)

            gastos_comunes = df_gastos[df_gastos["Tipo"] == "Común"]["Monto Total ($)"].sum()
            gastos_no_comunes = df_gastos[(df_gastos["Tipo"] == "No Común") & (df_gastos["Apto Destino"] == apt)]["Monto Total ($)"].sum()

            cuota_comun = gastos_comunes * alicuota
            total_a_pagar = cuota_comun + gastos_no_comunes

            col1, col2, col3 = st.columns(3)
            col1.metric("Cuota Gastos Comunes", f"${cuota_comun:.2f}")
            col2.metric("Gastos No Comunes", f"${gastos_no_comunes:.2f}")
            col3.metric("TOTAL A PAGAR", f"${total_a_pagar:.2f}")

            html_recibo = generar_recibo_html(nombre_res, rif_res, dir_res, mes_actual, apt, alicuota, df_gastos, total_a_pagar)
            st.download_button("📥 Descargar / Imprimir Recibo", data=html_recibo, file_name=f"recibo_apt_{apt}_{mes_actual}.html", mime="text/html")
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
        st.markdown("##### 📅 Seleccionar Periodo del Reporte")
        col_f1, col_f2 = st.columns(2)
        with col_f1:
            fecha_inicio = st.date_input("Fecha Desde", value=datetime(2026, 1, 1))
        with col_f2:
            fecha_fin = st.date_input("Fecha Hasta", value=datetime.now())

        conn = conectar_db()
        df_p = pd.read_sql_query("SELECT fecha AS 'Fecha', monto AS 'Monto ($)', referencia AS 'Referencia', metodo AS 'Método', estado AS 'Estado' FROM pagos_reportados WHERE apartamento = ? AND fecha >= ? AND fecha <= ? ORDER BY fecha DESC", conn, params=(apt, str(fecha_inicio), str(fecha_fin)))
        conn.close()

        if not df_p.empty:
            st.dataframe(df_p, use_container_width=True)
            monto_total_periodo = df_p[df_p["Estado"] == "Aprobado"]["Monto ($)"].sum()
            st.caption(f"**Total Aprobado en el periodo:** ${monto_total_periodo:.2f}")

            sub_tit = f"Periodo: {fecha_inicio.strftime('%d/%m/%Y')} al {fecha_fin.strftime('%d/%m/%Y')}"
            html_pagos = generar_reporte_html(f"Historial de Pagos - Apt {apt}", df_p, sub_tit)
            st.download_button("📥 Descargar / Imprimir Reporte de Pagos", data=html_pagos, file_name=f"reporte_pagos_apt_{apt}.html", mime="text/html")
        else:
            st.info("No se encontraron pagos registrados en el periodo seleccionado.")

    with tab_seguridad:
        st.subheader("⚙️ Cambiar Contraseña")
        p_act = st.text_input("Contraseña Actual", type="password")
        p_new = st.text_input("Nueva Contraseña", type="password")
        p_cnf = st.text_input("Confirmar Nueva Contraseña", type="password")
        if st.button("Guardar Clave"):
            valido, _ = verificar_usuario(apt, p_act)
            if valido and len(p_new) >= 4 and p_new == p_cnf:
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
    tab_aprobar, tab_recibo_gen, tab_reportes_admin, tab_gastos_admin, tab_props, tab_prov_admin, tab_datos = st.tabs([
        "✅ Aprobar Pagos", 
        "👁️ Previsualizar Recibo General",
        "📑 Reportes por Periodo", 
        "➕ Cargar Gastos",
        "👥 Propietarios", 
        "🛠️ Proveedores", 
        "🏢 Config. Edificio"
    ])

    # 1. TAB APROBAR PAGOS
    with tab_aprobar:
        st.subheader("⏳ Revisión y Aprobación de Pagos de Propietarios")
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
            st.info("No hay pagos pendientes por revisar en este momento.")

    # 2. TAB PREVISUALIZAR RECIBO GENERAL
    with tab_recibo_gen:
        st.subheader("👁️ Vista Previa del Recibo General de Gastos")
        
        conn = conectar_db()
        df_g = pd.read_sql_query("SELECT mes_ano, concepto AS 'Concepto', tipo AS 'Tipo', monto AS 'Monto ($)', apto_destino AS 'Apto' FROM gastos", conn)
        conn.close()

        if not df_g.empty:
            nom_res_act, rif_res_act, dir_res_act, logo_res_act = obtener_datos_residencia()
            mes_actual_txt = df_g["mes_ano"].iloc[-1]
            tot_comun = df_g[df_g["Tipo"] == "Común"]["Monto ($)"].sum()
            tot_general = df_g["Monto ($)"].sum()

            col_l1, col_l2 = st.columns([1, 4])
            with col_l1:
                if logo_res_act:
                    st.image(logo_res_act, width=120)
                elif os.path.exists("logo.jpg"):
                    st.image("logo.jpg", width=120)
            with col_l2:
                st.markdown(f"## **{nom_res_act}**")
                st.write(f"**RIF:** {rif_res_act} | **Dirección:** {dir_res_act}")
                st.markdown(f"### **AVISO / RECIBO GENERAL DE GASTOS - {mes_actual_txt.upper()}**")

            st.markdown("---")
            st.markdown("#### 📋 1. Relación de Gastos Cargar del Mes")
            st.dataframe(df_g[["Concepto", "Tipo", "Monto ($)", "Apto"]], use_container_width=True)
            st.info(f"**Monto Total Gastos Comunes:** ${tot_comun:.2f} | **Total Gastos Registrados:** ${tot_general:.2f}")

            todos_apts = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
            apts_data = []

            for ap in todos_apts:
                aliq = obtener_alicuota(ap)
                g_nocomun = df_g[(df_g["Tipo"] == "No Común") & (df_g["Apto"] == ap)]["Monto ($)"].sum()
                cuota_c = tot_comun * aliq
                total_ap = cuota_c + g_nocomun
                apts_data.append({
                    "Apartamento": ap, 
                    "Alícuota": f"{aliq*100:.0f}%", 
                    "Cuota Común ($)": round(cuota_c, 2), 
                    "Gasto Propio ($)": round(g_nocomun, 2), 
                    "Total a Pagar ($)": round(total_ap, 2)
                })

            df_resumen_recibos = pd.DataFrame(apts_data)

            st.markdown("---")
            st.markdown("#### 📊 2. Monto a Pagar por Apartamento según su Alícuota")
            st.dataframe(df_resumen_recibos, use_container_width=True)

            st.markdown("---")
            col_acc1, col_acc2 = st.columns(2)
            
            with col_acc1:
                html_recibo_general = generar_recibo_general_html(nom_res_act, rif_res_act, dir_res_act, mes_actual_txt, df_g[["Concepto", "Tipo", "Monto ($)", "Apto"]], df_resumen_recibos)
                st.download_button("🖨️ Imprimir / Guardar Recibo General (PDF)", data=html_recibo_general, file_name=f"recibo_general_{mes_actual_txt}.html", mime="text/html")

            with col_acc2:
                cuota_6 = tot_comun * 0.06
                cuota_12 = tot_comun * 0.12
                cuota_16 = tot_comun * 0.16

                msg_grupo = f"🏢 *{nom_res_act}*\n"
                msg_grupo += f"📢 *AVISO Y RECIBO GENERAL - {mes_actual_txt.upper()}*\n"
                msg_grupo += f"💰 *Total Gastos Comunes:* ${tot_comun:.2f}\n"
                msg_grupo += f"__________________________________\n\n"
                msg_grupo += f"🔹 *Alicuota 6%* (Aptos: 1A, 1B, 3A, 3B, 4A, 4B, 5A, 5B, 6A, 6B):\n"
                msg_grupo += f"• *Monto a Pagar:* ${cuota_6:.2f}\n\n"
                msg_grupo += f"🔹 *Alicuota 12%* (Aptos: 2, 7):\n"
                msg_grupo += f"• *Monto a Pagar:* ${cuota_12:.2f}\n\n"
                msg_grupo += f"🔹 *Alicuota 16%* (PH):\n"
                msg_grupo += f"• *Monto a Pagar:* ${cuota_16:.2f}\n"
                msg_grupo += f"__________________________________\n"
                msg_grupo += f"📌 Verifique si posee un gasto propio o ingrese a la plataforma para reportar su pago."

                boton_whatsapp("", msg_grupo, "📲 Enviar Resumen General al Grupo de WhatsApp")

        else:
            st.info("No hay gastos registrados en la base de datos para generar la previsualización.")

    # 3. TAB REPORTES POR PERIODO
    with tab_reportes_admin:
        st.subheader("📑 Reportes General e Impresiones por Periodo")
        
        st.markdown("##### 📅 Definir Rango de Fechas del Reporte")
        col_df1, col_df2 = st.columns(2)
        with col_df1:
            f_desde = st.date_input("Desde:", value=datetime(2026, 1, 1), key="adm_f_desde")
        with col_df2:
            f_hasta = st.date_input("Hasta:", value=datetime.now(), key="adm_f_hasta")

        sub_periodo = f"Periodo: {f_desde.strftime('%d/%m/%Y')} al {f_hasta.strftime('%d/%m/%Y')}"

        st.markdown("---")
        opcion_rep = st.radio("Seleccione el reporte a generar:", [
            "💰 Pagos de Propietarios (Vecinos)", 
            "🚚 Gastos y Pagos a Proveedores", 
            "📄 Consolidado de Recibos de Condominio"
        ], horizontal=True)

        if opcion_rep == "💰 Pagos de Propietarios (Vecinos)":
            st.markdown("### Reporte de Pagos de Propietarios")
            lista_apts_filtro = ["Todos"] + ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
            apto_filtro = st.selectbox("Filtrar por Apartamento:", lista_apts_filtro)

            conn = conectar_db()
            if apto_filtro == "Todos":
                df_rep_pagos = pd.read_sql_query("SELECT id AS 'ID', apartamento AS 'Apto', fecha AS 'Fecha', monto AS 'Monto ($)', referencia AS 'Referencia', metodo AS 'Método', estado AS 'Estado' FROM pagos_reportados WHERE fecha >= ? AND fecha <= ? ORDER BY fecha DESC", conn, params=(str(f_desde), str(f_hasta)))
            else:
                df_rep_pagos = pd.read_sql_query("SELECT id AS 'ID', apartamento AS 'Apto', fecha AS 'Fecha', monto AS 'Monto ($)', referencia AS 'Referencia', metodo AS 'Método', estado AS 'Estado' FROM pagos_reportados WHERE apartamento = ? AND fecha >= ? AND fecha <= ? ORDER BY fecha DESC", conn, params=(apto_filtro, str(f_desde), str(f_hasta)))
            conn.close()

            if not df_rep_pagos.empty:
                st.dataframe(df_rep_pagos, use_container_width=True)
                monto_aprobado = df_rep_pagos[df_rep_pagos["Estado"] == "Aprobado"]["Monto ($)"].sum()
                st.success(f"**Total Pagos Aprobados en el Periodo:** ${monto_aprobado:.2f}")

                html_adm_pagos = generar_reporte_html(f"Reporte de Pagos de Propietarios ({apto_filtro})", df_rep_pagos, sub_periodo)
                st.download_button("🖨️ Descargar / Imprimir Reporte de Pagos", data=html_adm_pagos, file_name=f"reporte_pagos_prop_{f_desde}_al_{f_hasta}.html", mime="text/html")
            else:
                st.info("No se registraron pagos de propietarios en este periodo.")

        elif opcion_rep == "🚚 Gastos y Pagos a Proveedores":
            st.markdown("### Reporte de Gastos / Pagos a Proveedores")
            conn = conectar_db()
            df_rep_gastos = pd.read_sql_query("SELECT id AS 'ID', mes_ano AS 'Mes/Año', concepto AS 'Concepto / Proveedor', tipo AS 'Tipo Gasto', monto AS 'Monto ($)', apto_destino AS 'Apto Destino' FROM gastos ORDER BY id DESC", conn)
            conn.close()

            if not df_rep_gastos.empty:
                st.dataframe(df_rep_gastos, use_container_width=True)
                total_gastos = df_rep_gastos["Monto ($)"].sum()
                st.info(f"**Total Gastos Registrados:** ${total_gastos:.2f}")

                html_adm_gastos = generar_reporte_html("Reporte General de Gastos y Proveedores", df_rep_gastos, sub_periodo)
                st.download_button("🖨️ Descargar / Imprimir Reporte de Gastos", data=html_adm_gastos, file_name=f"reporte_gastos_{f_desde}_al_{f_hasta}.html", mime="text/html")
            else:
                st.info("No hay gastos registrados en el sistema.")

        else:
            st.markdown("### Consolidado de Recibos del Condominio")
            conn = conectar_db()
            df_g = pd.read_sql_query("SELECT mes_ano, concepto AS 'Concepto', tipo AS 'Tipo', monto AS 'Monto ($)', apto_destino AS 'Apto' FROM gastos", conn)
            df_props = pd.read_sql_query("SELECT apartamento, nombre, telefono FROM usuarios", conn)
            conn.close()

            if not df_g.empty:
                tot_comun = df_g[df_g["Tipo"] == "Común"]["Monto ($)"].sum()
                
                apts_data = []
                todos_apts = ["1A", "1B", "2", "3A", "3B", "4A", "4B", "5A", "5B", "6A", "6B", "7", "PH"]
                for ap in todos_apts:
                    aliq = obtener_alicuota(ap)
                    g_nocomun = df_g[(df_g["Tipo"] == "No Común") & (df_g["Apto"] == ap)]["Monto ($)"].sum()
                    cuota_c = tot_comun * aliq
                    total_ap = cuota_c + g_nocomun
                    
                    # Buscar datos de propietario
                    row_p = df_props[df_props["apartamento"] == ap]
                    nom_p = row_p["nombre"].values[0] if not row_p.empty else "Propietario"
                    tel_p = row_p["telefono"].values[0] if not row_p.empty else ""

                    apts_data.append({
                        "Apartamento": ap, 
                        "Propietario": nom_p,
                        "Teléfono": tel_p,
                        "Alícuota": f"{aliq*100:.0f}%", 
                        "Cuota Común ($)": round(cuota_c, 2), 
                        "Gasto Propio ($)": round(g_nocomun, 2), 
                        "Total Cobrado ($)": round(total_ap, 2)
                    })

                df_resumen_recibos = pd.DataFrame(apts_data)
                st.dataframe(df_resumen_recibos, use_container_width=True)

                html_adm_recibos = generar_reporte_html("Consolidado de Recibos de Condominio", df_resumen_recibos, sub_periodo)
                st.download_button("🖨️ Descargar / Imprimir Consolidado de Recibos", data=html_adm_recibos, file_name=f"consolidado_recibos_{f_desde}_al_{f_hasta}.html", mime="text/html")

                st.markdown("---")
                st.markdown("#### 📲 Enviar Recibos Individuales por WhatsApp")
                nom_res_actual, _, _, _ = obtener_datos_residencia()
                mes_actual_txt = df_g["mes_ano"].iloc[-1]
                
                for item in apts_data:
                    c_apt, c_nom, c_tel, c_aliq, c_cuota, c_propio, c_total = item["Apartamento"], item["Propietario"], item["Teléfono"], item["Alícuota"], item["Cuota Común ($)"], item["Gasto Propio ($)"], item["Total Cobrado ($)"]
                    
                    mensaje_recibo = f"🏢 *{nom_res_actual}*\n"
                    mensaje_recibo += f"📄 *RECIBO DE CONDOMINIO - {mes_actual_txt.upper()}*\n\n"
                    mensaje_recibo += f"👤 *Estimado(a):* {c_nom}\n"
                    mensaje_recibo += f"🏠 *Apartamento:* {c_apt}\n"
                    mensaje_recibo += f"📊 *Alícuota:* {c_aliq}\n"
                    mensaje_recibo += f"🔹 *Cuota Gastos Comunes:* ${c_cuota:.2f}\n"
                    if c_propio > 0:
                        mensaje_recibo += f"🔸 *Gastos Propios:* ${c_propio:.2f}\n"
                    mensaje_recibo += f"💵 *TOTAL A PAGAR:* ${c_total:.2f}\n\n"
                    mensaje_recibo += f"📌 Le recordamos realizar su pago y reportarlo a través de nuestra plataforma."

                    col_w1, col_w2 = st.columns([3, 2])
                    with col_w1:
                        st.write(f"🏠 **Apt {c_apt}** - {c_nom} | Total: **${c_total:.2f}**")
                    with col_w2:
                        boton_whatsapp(c_tel, mensaje_recibo, f"📲 Enviar Recibo a {c_nom}")

            else:
                st.info("No hay gastos registrados para consolidar los recibos.")

    # 4. TAB GASTOS
    with tab_gastos_admin:
        st.subheader("➕ Cargar Nuevo Gasto / Factura de Proveedor")
        with st.form("form_gastos", clear_on_submit=True):
            mes = st.text_input("Mes y Año (Ej: Agosto 2026):")
            concepto = st.text_input("Concepto / Servicio del Proveedor:")
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

        if not df_g.empty:
            st.subheader("🗑️ Eliminar Gasto Registrado")
            opciones = {f"ID #{row['ID']}: {row['Concepto']} (${row['Monto ($)']})": row['ID'] for _, row in df_g.iterrows()}
            gasto_sel = st.selectbox("Seleccione gasto:", list(opciones.keys()))
            if st.button("❌ Eliminar Gasto"):
                eliminar_gasto(opciones[gasto_sel])
                st.success("Gasto eliminado.")
                st.rerun()

    # 5. TAB PROPIETARIOS (NUEVO)
    with tab_props:
        st.subheader("👥 Directorio de Propietarios")
        st.caption("Escriba los nombres y teléfonos de cada apartamento para personalizar las notificaciones de WhatsApp (Incluya código de país sin el +, ej: 584121234567).")
        
        df_props_actuales = obtener_propietarios()
        
        for _, row in df_props_actuales.iterrows():
            apto_curr = row['Apt']
            col_p1, col_p2, col_p3, col_p4 = st.columns([1, 2, 2, 1])
            with col_p1:
                st.markdown(f"### **Apt {apto_curr}**")
            with col_p2:
                nuevo_nom = st.text_input(f"Nombre", value=row['Nombre'], key=f"nom_{apto_curr}")
            with col_p3:
                nuevo_tel = st.text_input(f"Teléfono WhatsApp", value=row['Telefono'], key=f"tel_{apto_curr}")
            with col_p4:
                st.write("")
                st.write("")
                if st.button("💾 Guardar", key=f"btn_prop_{apto_curr}"):
                    actualizar_propietario(apto_curr, nuevo_nom, nuevo_tel)
                    st.success(f"Apt {apto_curr} guardado.")
                    st.rerun()

    # 6. TAB PROVEEDORES
    with tab_prov_admin:
        st.subheader("🛠️ Directorio de Proveedores")
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

    # 7. TAB CONFIGURACIÓN EDIFICIO
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
                st.success("Datos del edificio actualizados con éxito.")
                st.rerun()
