import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
from datetime import date

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Condominio - Residencias El Roble",
    page_icon="🏢",
    layout="wide"
)

DB_NAME = "condominio.db"

# --- HELPER PARA FECHAS EN ESPAÑOL ---
MESES_ESP = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

def get_periodo_actual():
    hoy = date.today()
    return f"{MESES_ESP[hoy.month]} {hoy.year}"

# --- CONEXIÓN A BASE DE DATOS Y CONTEXT MANAGER ---
def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- INICIALIZACIÓN DE LA BASE DE DATOS ---
def init_db():
    with get_connection() as conn:
        c = conn.cursor()
        
        # 1. Tabla Datos del Edificio y Credenciales Admin
        c.execute('''
            CREATE TABLE IF NOT EXISTS edificio_info (
                id INTEGER PRIMARY KEY,
                nombre_edificio TEXT,
                rif TEXT,
                direccion TEXT,
                banco_nombre TEXT,
                num_cuenta TEXT,
                pago_movil_telf TEXT,
                pago_movil_cedula TEXT,
                usuario_admin TEXT,
                clave_admin TEXT
            )
        ''')
        
        # Migraciones por si las columnas no existían
        try:
            c.execute("ALTER TABLE edificio_info ADD COLUMN usuario_admin TEXT DEFAULT 'admin'")
        except sqlite3.OperationalError:
            pass
            
        try:
            c.execute("ALTER TABLE edificio_info ADD COLUMN clave_admin TEXT DEFAULT '1234'")
        except sqlite3.OperationalError:
            pass
        
        c.execute("SELECT COUNT(*) FROM edificio_info")
        if c.fetchone()[0] == 0:
            c.execute('''
                INSERT INTO edificio_info VALUES (
                    1, 'Residencias El Roble', 'J-00000000-0', 
                    'Caracas, Venezuela', 'Banesco', 
                    '0134-0000-00-0000000000', '0412-0000000', 'V-12345678', 'admin', '1234'
                )
            ''')

        # 2. Tabla Propietarios y Alícuotas
        c.execute('''
            CREATE TABLE IF NOT EXISTS propietarios (
                apartamento TEXT PRIMARY KEY,
                propietario TEXT,
                telefono TEXT,
                alicuota REAL
            )
        ''')
        
        c.execute("SELECT COUNT(*) FROM propietarios")
        if c.fetchone()[0] == 0:
            apts_iniciales = [
                ("1A", "", "", 0.06), ("1B", "", "", 0.06),
                ("2",  "", "", 0.12),
                ("3A", "", "", 0.06), ("3B", "", "", 0.06),
                ("4A", "", "", 0.06), ("4B", "", "", 0.06),
                ("5A", "", "", 0.06), ("5B", "", "", 0.06),
                ("6A", "", "", 0.06), ("6B", "", "", 0.06),
                ("7",  "", "", 0.12),
                ("PH", "", "", 0.16)
            ]
            c.executemany("INSERT INTO propietarios VALUES (?, ?, ?, ?)", apts_iniciales)
            
        # 3. Tabla Gastos
        c.execute('''
            CREATE TABLE IF NOT EXISTS gastos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                periodo TEXT,
                concepto TEXT,
                monto REAL,
                tipo TEXT,
                apartamento TEXT,
                fecha TEXT
            )
        ''')
        
        # 4. Tabla Pagos
        c.execute('''
            CREATE TABLE IF NOT EXISTS pagos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                apartamento TEXT,
                periodo TEXT,
                monto REAL,
                referencia TEXT,
                fecha TEXT,
                estado TEXT DEFAULT 'Pendiente'
            )
        ''')
        conn.commit()

init_db()

# --- FUNCIONES DE CONSULTA ---
def run_query(query, params=(), fetch_all=True):
    try:
        with get_connection() as conn:
            c = conn.cursor()
            c.execute(query, params)
            conn.commit()
            if fetch_all:
                return c.fetchall()
            return None
    except Exception as e:
        st.error(f"Error en base de datos: {e}")
        return [] if fetch_all else None

def get_edificio_info():
    try:
        with get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT nombre_edificio, rif, direccion, banco_nombre, num_cuenta, pago_movil_telf, pago_movil_cedula, usuario_admin, clave_admin FROM edificio_info WHERE id=1")
            row = c.fetchone()
            if row:
                return {
                    "nombre": row[0], "rif": row[1], "direccion": row[2],
                    "banco": row[3], "cuenta": row[4], "pm_telf": row[5], "pm_cedula": row[6],
                    "usuario_admin": row[7] if row[7] else "admin",
                    "clave_admin": row[8] if row[8] else "1234"
                }
    except Exception:
        pass
    return {
        "nombre": "Residencias El Roble", "rif": "J-00000000-0", "direccion": "Caracas, Venezuela",
        "banco": "Banesco", "cuenta": "0134-0000-00-0000000000", "pm_telf": "0412-0000000", "pm_cedula": "V-12345678",
        "usuario_admin": "admin", "clave_admin": "1234"
    }

def get_propietarios():
    try:
        with get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM propietarios ORDER BY apartamento", conn)
    except Exception:
        return pd.DataFrame(columns=["apartamento", "propietario", "telefono", "alicuota"])

def get_gastos(periodo=None):
    try:
        with get_connection() as conn:
            if periodo:
                return pd.read_sql_query("SELECT * FROM gastos WHERE periodo = ?", conn, params=[periodo])
            return pd.read_sql_query("SELECT * FROM gastos ORDER BY id DESC", conn)
    except Exception:
        return pd.DataFrame(columns=["id", "periodo", "concepto", "monto", "tipo", "apartamento", "fecha"])

def get_pagos():
    try:
        with get_connection() as conn:
            return pd.read_sql_query("SELECT * FROM pagos ORDER BY id DESC", conn)
    except Exception:
        return pd.DataFrame(columns=["id", "apartamento", "periodo", "monto", "referencia", "fecha", "estado"])

# --- INTERFAZ DE USUARIO ---
info_edif = get_edificio_info()

st.title(f"🏢 {info_edif.get('nombre', 'Sistema de Condominio')}")
st.caption(f"RIF: {info_edif.get('rif', '')} | {info_edif.get('direccion', '')}")

perfil = st.sidebar.radio("Seleccione el Perfil:", ["👤 Portal Residente", "⚙️ Administración"])

if perfil == "⚙️ Administración":
    st.sidebar.markdown("---")
    
    # --- MÓDULO DE AUTENTICACIÓN (USUARIO Y CLAVE) ---
    if "admin_autenticado" not in st.session_state:
        st.session_state.admin_autenticado = False

    if not st.session_state.admin_autenticado:
        st.subheader("🔒 Acceso Restringido - Administración")
        st.info("Ingrese su usuario y clave de administrador.")
        
        with st.form("form_login"):
            usuario_ingresado = st.text_input("Usuario Administrador:")
            clave_ingresada = st.text_input("Clave de Acceso:", type="password")
            submit_login = st.form_submit_button("🔑 Ingresar")
            
            if submit_login:
                user_ok = info_edif.get("usuario_admin", "admin")
                pass_ok = info_edif.get("clave_admin", "1234")
                
                if usuario_ingresado.strip() == user_ok and clave_ingresada == pass_ok:
                    st.session_state.admin_autenticado = True
                    st.success("¡Acceso concedido!")
                    st.rerun()
                else:
                    st.error("❌ Usuario o clave incorrectos. Intente nuevamente.")
    else:
        # Botón para cerrar sesión en la barra lateral
        if st.sidebar.button("🔒 Cerrar Sesión Admin"):
            st.session_state.admin_autenticado = False
            st.rerun()

        menu_admin = st.sidebar.selectbox("Opciones de Administración:", [
            "1. Datos del Edificio, Cuentas y Credenciales",
            "2. Gestión de Propietarios y Alícuotas",
            "3. Registro de Gastos del Mes",
            "4. Recibos y Envío WhatsApp",
            "5. Control de Pagos Recibidos"
        ])
        
        # 1. DATOS DEL EDIFICIO Y CREDENCIALES
        if menu_admin == "1. Datos del Edificio, Cuentas y Credenciales":
            st.subheader("⚙️ Configuración de Datos del Edificio y Seguridad")
            
            with st.form("form_edificio"):
                col1, col2 = st.columns(2)
                with col1:
                    nom_edif = st.text_input("Nombre del Edificio / Condominio:", value=info_edif.get("nombre", ""))
                    rif_edif = st.text_input("RIF / Identificación Fiscal:", value=info_edif.get("rif", ""))
                    dir_edif = st.text_input("Dirección:", value=info_edif.get("direccion", ""))
                    
                    st.markdown("---")
                    st.markdown("🔑 **Credenciales de Administrador:**")
                    user_actual = st.text_input("Usuario Admin:", value=info_edif.get("usuario_admin", "admin"))
                    clave_actual = st.text_input("Clave Admin:", value=info_edif.get("clave_admin", "1234"), type="password")
                    
                with col2:
                    banco_nom = st.text_input("Banco:", value=info_edif.get("banco", ""))
                    cuenta_num = st.text_input("Número de Cuenta Corriente:", value=info_edif.get("cuenta", ""))
                    pm_telf = st.text_input("Teléfono Pago Móvil:", value=info_edif.get("pm_telf", ""))
                    pm_ced = st.text_input("Cédula / RIF Pago Móvil:", value=info_edif.get("pm_cedula", ""))
                    
                guardar_info = st.form_submit_button("💾 Guardar Cambios")
                if guardar_info:
                    run_query('''
                        UPDATE edificio_info 
                        SET nombre_edificio=?, rif=?, direccion=?, banco_nombre=?, num_cuenta=?, pago_movil_telf=?, pago_movil_cedula=?, usuario_admin=?, clave_admin=?
                        WHERE id=1
                    ''', (nom_edif, rif_edif, dir_edif, banco_nom, cuenta_num, pm_telf, pm_ced, user_actual.strip(), clave_actual), fetch_all=False)
                    st.success("¡Información del edificio y credenciales actualizadas correctamente!")
                    st.rerun()

        # 2. PROPIETARIOS Y ALÍCUOTAS
        elif menu_admin == "2. Gestión de Propietarios y Alícuotas":
            st.subheader("👥 Directorio de Propietarios y Configuración de Alícuotas")
            tab_listado, tab_nuevo = st.tabs(["📋 Modificar Propietarios y Alícuotas", "➕ Agregar Nuevo Apartamento"])
            
            with tab_listado:
                df_props = get_propietarios()
                edited_df = st.data_editor(
                    df_props,
                    column_config={
                        "apartamento": st.column_config.TextColumn("Apto", disabled=True),
                        "propietario": "Nombre Propietario",
                        "telefono": "Teléfono (Ej: 584121234567)",
                        "alicuota": st.column_config.NumberColumn("Alícuota (Ej: 0.06 = 6%)", format="%.4f", min_value=0.0, max_value=1.0, step=0.01)
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                suma_alicuotas = edited_df["alicuota"].sum() if not edited_df.empty else 0.0
                st.caption(f"📊 Suma total de alícuotas actuales: **{suma_alicuotas*100:.2f}%**")
                if abs(suma_alicuotas - 1.0) > 0.001:
                    st.warning("⚠️ La suma total de alícuotas no da el 100% (1.0). Ajuste los valores.")
                
                if st.button("💾 Guardar Cambios en Propietarios y Alícuotas"):
                    for _, row in edited_df.iterrows():
                        run_query(
                            "UPDATE propietarios SET propietario = ?, telefono = ?, alicuota = ? WHERE apartamento = ?",
                            (row["propietario"], str(row["telefono"]), float(row["alicuota"]), row["apartamento"]),
                            fetch_all=False
                        )
                    st.success("Información actualizada exitosamente.")
                    st.rerun()
                    
            with tab_nuevo:
                with st.form("form_nuevo_apto"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        nuevo_apto = st.text_input("Identificador / Número de Apto:")
                        nuevo_prop = st.text_input("Nombre del Propietario:")
                    with col_b:
                        nuevo_telf = st.text_input("Teléfono de Contacto:")
                        nueva_aliq = st.number_input("Alícuota:", min_value=0.0, max_value=1.0, value=0.06, step=0.01, format="%.4f")
                    
                    guardar_nuevo = st.form_submit_button("➕ Registrar Apartamento")
                    if guardar_nuevo and nuevo_apto:
                        try:
                            run_query("INSERT INTO propietarios VALUES (?, ?, ?, ?)", (nuevo_apto.upper().strip(), nuevo_prop, nuevo_telf, nueva_aliq), fetch_all=False)
                            st.success(f"Apartamento {nuevo_apto} agregado exitosamente.")
                            st.rerun()
                        except Exception as e:
                            st.error("El número de apartamento ya existe o fue inválido.")

        # 3. REGISTRO DE GASTOS
        elif menu_admin == "3. Registro de Gastos del Mes":
            st.subheader("📝 Registrar Gastos del Condominio")
            col1, col2 = st.columns(2)
            
            with col1:
                periodo = st.text_input("Período / Mes", value=get_periodo_actual())
                concepto = st.text_input("Concepto del Gasto")
                monto = st.number_input("Monto ($)", min_value=0.0, step=10.0, format="%.2f")
                
            with col2:
                tipo_gasto = st.selectbox("Tipo de Gasto", ["Común", "No Común"])
                apto_asig = "-"
                if tipo_gasto == "No Común":
                    df_props = get_propietarios()
                    apto_asig = st.selectbox("Asignar a Apartamento:", df_props["apartamento"].tolist() if not df_props.empty else ["1A"])
                fecha_gasto = st.date_input("Fecha de Registro", date.today())

            if st.button("➕ Agregar Gasto"):
                if concepto and monto > 0:
                    run_query(
                        "INSERT INTO gastos (periodo, concepto, monto, tipo, apartamento, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                        (periodo, concepto, monto, tipo_gasto, apto_asig, str(fecha_gasto)),
                        fetch_all=False
                    )
                    st.success(f"Gasto '{concepto}' registrado exitosamente para {periodo}.")
                    st.rerun()
                else:
                    st.error("Complete el concepto y un monto mayor a cero.")

            st.markdown("---")
            st.subheader("📋 Gastos Registrados")
            st.dataframe(get_gastos(periodo), use_container_width=True)

        # 4. RECIBOS Y WHATSAPP
        elif menu_admin == "4. Recibos y Envío WhatsApp":
            st.subheader("📊 Previsualización y Envío de Recibos")
            periodo_sel = st.text_input("Período a calcular", value=get_periodo_actual())
            
            gastos_df = get_gastos(periodo_sel)
            props_df = get_propietarios()
            
            if gastos_df.empty or props_df.empty:
                st.warning("No hay gastos registrados para este período o faltan datos en el directorio.")
            else:
                gastos_df["monto"] = gastos_df["monto"].astype(float)
                total_comun = gastos_df[gastos_df["tipo"] == "Común"]["monto"].sum()
                total_no_comun = gastos_df[gastos_df["tipo"] == "No Común"]["monto"].sum()
                total_general = total_comun + total_no_comun
                
                tab_gen, tab_ind = st.tabs(["📢 Recibo General (Grupo WhatsApp)", "👤 Recibo Individual (Privado)"])
                
                with tab_gen:
                    msg_general = (
                        f"🏢 *{info_edif.get('nombre', 'CONDOMINIO').upper()}*\n"
                        f"📄 RIF: {info_edif.get('rif', 'N/A')}\n"
                        f"📋 *RELACIÓN GENERAL DE GASTOS Y COBRO - {periodo_sel.upper()}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💵 *TOTAL GASTOS COMUNES:* ${total_comun:,.2f}\n"
                    )
                    if total_no_comun > 0:
                        msg_general += f"🔧 *TOTAL GASTOS NO COMUNES:* ${total_no_comun:,.2f}\n"
                    msg_general += f"💰 *TOTAL MES EDIFICIO:* ${total_general:,.2f}\n"
                    msg_general += f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    msg_general += f"📊 *DISTRIBUCIÓN POR APARTAMENTO:*\n"
                    
                    filas_resumen = []
                    for _, prop in props_df.iterrows():
                        apto = prop["apartamento"]
                        alicuota = float(prop["alicuota"])
                        cuota_c = total_comun * alicuota
                        no_c = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto)]["monto"].sum()
                        tot_apto = cuota_c + no_c
                        
                        filas_resumen.append({
                            "Apto": apto,
                            "Alícuota": f"{alicuota*100:.1f}%",
                            "Propietario": prop.get("propietario") or "-",
                            "Cuota Común ($)": round(cuota_c, 2),
                            "Gastos Ind. ($)": round(no_c, 2),
                            "Total a Pagar ($)": round(tot_apto, 2)
                        })
                        
                        det_no_c = f" (+$ {no_c:,.2f} no común)" if no_c > 0 else ""
                        msg_general += f"▫️ *Apto {apto}* ({alicuota*100:.1f}%): *${tot_apto:,.2f}*{det_no_c}\n"
                    
                    msg_general += (
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"💳 *DATOS DE PAGO:*\n"
                        f"Banco: {info_edif.get('banco', 'N/A')}\n"
                        f"Cuenta: {info_edif.get('cuenta', 'N/A')}\n"
                        f"Pago Móvil: {info_edif.get('pm_telf', 'N/A')} / {info_edif.get('pm_cedula', 'N/A')}\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"Por favor remitir sus comprobantes de pago por el portal o al privado. ¡Muchas gracias!"
                    )
                    
                    st.dataframe(pd.DataFrame(filas_resumen), use_container_width=True)
                    st.text_area("Vista previa mensaje para WhatsApp:", value=msg_general, height=220)
                    
                    url_general = urllib.parse.quote(msg_general)
                    st.link_button("📲 Compartir Relación General al Grupo de WhatsApp", f"https://wa.me/?text={url_general}")

                with tab_ind:
                    apto_recibo = st.selectbox("Seleccionar Apartamento:", props_df["apartamento"].tolist())
                    prop_info = props_df[props_df["apartamento"] == apto_recibo].iloc[0]
                    
                    alicuota_ind = float(prop_info["alicuota"])
                    cuota_comun_ind = total_comun * alicuota_ind
                    no_comunes_ind = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto_recibo)]["monto"].sum()
                    total_ind = cuota_comun_ind + no_comunes_ind
                    
                    recibo_ind = (
                        f"🏢 *{info_edif.get('nombre', 'CONDOMINIO').upper()}*\n"
                        f"📄 *Aviso de Cobro - {periodo_sel}*\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"👤 *Propietario:* {prop_info.get('propietario') or 'N/A'}\n"
                        f"🏠 *Apartamento:* {apto_recibo} (Alícuota: {alicuota_ind*100:.1f}%)\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🔹 *Gastos Comunes Edificio:* ${total_comun:,.2f}\n"
                        f"🔹 *Su Cuota Común ({alicuota_ind*100:.1f}%):* ${cuota_comun_ind:,.2f}\n"
                    )
                    if no_comunes_ind > 0:
                        recibo_ind += f"🔹 *Gastos Propios / Ind.:* ${no_comunes_ind:,.2f}\n"
                    recibo_ind += (
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"💰 *TOTAL A PAGAR:* ${total_ind:,.2f}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"💳 *DATOS DE PAGO:*\n"
                        f"Banco: {info_edif.get('banco', 'N/A')}\n"
                        f"Cuenta: {info_edif.get('cuenta', 'N/A')}\n"
                        f"Pago Móvil: {info_edif.get('pm_telf', 'N/A')} / {info_edif.get('pm_cedula', 'N/A')}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"Por favor enviar comprobante de pago por este medio. ¡Gracias!"
                    )
                    
                    st.text_area("Vista previa recibo individual:", value=recibo_ind, height=200)
                    
                    telefono_limpio = "".join(filter(str.isdigit, str(prop_info.get("telefono", ""))))
                    if telefono_limpio:
                        mensaje_url = urllib.parse.quote(recibo_ind)
                        st.link_button(f"📲 Enviar Recibo Privado por WhatsApp al Apto {apto_recibo}", f"https://wa.me/{telefono_limpio}?text={mensaje_url}")
                    else:
                        st.info("💡 Asigne un número de teléfono en el Directorio para habilitar el botón directo.")

        # 5. CONTROL DE PAGOS
        elif menu_admin == "5. Control de Pagos Recibidos":
            st.subheader("💳 Reportes de Pago Registrados por Propietarios")
            pagos_df = get_pagos()
            if pagos_df.empty:
                st.info("No hay reporte de pagos registrados por los residentes aún.")
            else:
                st.dataframe(pagos_df, use_container_width=True)

# --- PORTAL RESIDENTE ---
else:
    st.subheader(f"🏠 Portal de Consulta de Propietarios - {info_edif.get('nombre', '')}")
    props_df = get_propietarios()
    if props_df.empty:
        st.warning("No hay lista de apartamentos configurada.")
    else:
        apto_sel = st.selectbox("Seleccione su Apartamento:", props_df["apartamento"].tolist())
        periodo_consulta = st.text_input("Período a consultar", value=get_periodo_actual())
        
        prop_data = props_df[props_df["apartamento"] == apto_sel].iloc[0]
        gastos_df = get_gastos(periodo_consulta)
        
        if gastos_df.empty:
            st.info(f"No hay recibo generado aún para el período {periodo_consulta}.")
        else:
            gastos_df["monto"] = gastos_df["monto"].astype(float)
            total_comun = gastos_df[gastos_df["tipo"] == "Común"]["monto"].sum()
            alicuota = float(prop_data["alicuota"])
            cuota_comun = total_comun * alicuota
            gastos_ind = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto_sel)]["monto"].sum()
            total_pagar = cuota_comun + gastos_ind
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Alícuota", f"{alicuota*100:.1f}%")
            c2.metric("Cuota Gastos Comunes", f"${cuota_comun:,.2f}")
            c3.metric("Total a Pagar", f"${total_pagar:,.2f}")
            
            st.markdown("---")
            st.markdown("### 💳 Datos para el Pago")
            st.write(f"**Banco:** {info_edif.get('banco', '')}")
            st.write(f"**Cuenta:** {info_edif.get('cuenta', '')}")
            st.write(f"**Pago Móvil:** {info_edif.get('pm_telf', '')} | C.I/RIF: {info_edif.get('pm_cedula', '')}")
            
            st.markdown("---")
            st.markdown("### 📤 Reportar Transferencia / Pago Móvil")
            with st.form("form_pago"):
                monto_pago = st.number_input("Monto Transferido ($)", value=float(total_pagar))
                referencia = st.text_input("Número de Referencia")
                submit_pago = st.form_submit_button("Registrar Comprobante")
                
                if submit_pago:
                    if referencia:
                        run_query(
                            "INSERT INTO pagos (apartamento, periodo, monto, referencia, fecha) VALUES (?, ?, ?, ?, ?)",
                            (apto_sel, periodo_consulta, monto_pago, referencia, str(date.today())),
                            fetch_all=False
                        )
                        st.success("¡Pago reportado con éxito! La junta/administrador verificará el depósito.")
                    else:
                        st.error("Por favor ingrese el número de referencia del pago.")
