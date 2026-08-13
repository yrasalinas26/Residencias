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
        
        # Migraciones
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

        # 2. Tabla Propietarios y Alícuotas (Agregado campo clave_residente)
        c.execute('''
            CREATE TABLE IF NOT EXISTS propietarios (
                apartamento TEXT PRIMARY KEY,
                propietario TEXT,
                telefono TEXT,
                alicuota REAL,
                clave_residente TEXT DEFAULT '1234'
            )
        ''')
        
        # Migración por si la tabla existía sin clave_residente
        try:
            c.execute("ALTER TABLE propietarios ADD COLUMN clave_residente TEXT DEFAULT '1234'")
        except sqlite3.OperationalError:
            pass

        c.execute("SELECT COUNT(*) FROM propietarios")
        if c.fetchone()[0] == 0:
            apts_iniciales = [
                ("1A", "", "", 0.06, "1234"), ("1B", "", "", 0.06, "1234"),
                ("2",  "", "", 0.12, "1234"),
                ("3A", "", "", 0.06, "1234"), ("3B", "", "", 0.06, "1234"),
                ("4A", "", "", 0.06, "1234"), ("4B", "", "", 0.06, "1234"),
                ("5A", "", "", 0.06, "1234"), ("5B", "", "", 0.06, "1234"),
                ("6A", "", "", 0.06, "1234"), ("6B", "", "", 0.06, "1234"),
                ("7",  "", "", 0.12, "1234"),
                ("PH", "", "", 0.16, "1234")
            ]
            c.executemany("INSERT INTO propietarios VALUES (?, ?, ?, ?, ?)", apts_iniciales)
            
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
        return pd.DataFrame(columns=["apartamento", "propietario", "telefono", "alicuota", "clave_residente"])

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

# --- ESTADOS DE SESIÓN ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "rol" not in st.session_state:
    st.session_state.rol = None  # "admin" o "residente"
if "apto_usuario" not in st.session_state:
    st.session_state.apto_usuario = None

info_edif = get_edificio_info()

# --- PANTALLA DE ACCESO UNIFICADA ---
if not st.session_state.autenticado:
    st.markdown("<h2 style='text-align: center;'>🏢 Sistema de Condominio</h2>", unsafe_allow_text=True)
    st.markdown(f"<h4 style='text-align: center;'>{info_edif.get('nombre', '')}</h4>", unsafe_allow_text=True)
    st.caption(f"<p style='text-align: center;'>RIF: {info_edif.get('rif', '')} | {info_edif.get('direccion', '')}</p>", unsafe_allow_html=True)
    st.markdown("---")
    
    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        st.subheader("🔑 Inicio de Sesión")
        with st.form("form_login"):
            usuario_ingresado = st.text_input("Usuario:")
            clave_ingresada = st.text_input("Clave:", type="password")
            submit_login = st.form_submit_button("Ingresar")
            
            if submit_login:
                usr = usuario_ingresado.strip().upper()
                usr_admin = info_edif.get("usuario_admin", "admin").strip().upper()
                pass_admin = info_edif.get("clave_admin", "1234")
                
                # 1. Validar Credencial Admin
                if usr == usr_admin and clave_ingresada == pass_admin:
                    st.session_state.autenticado = True
                    st.session_state.rol = "admin"
                    st.rerun()
                else:
                    # 2. Validar Credenciales de Propietarios (Apto como usuario)
                    df_props = get_propietarios()
                    residente_match = df_props[df_props["apartamento"].str.upper() == usr]
                    
                    if not residente_match.empty:
                        clave_correcta = str(residente_match.iloc[0].get("clave_residente", "1234"))
                        if clave_ingresada == clave_correcta:
                            st.session_state.autenticado = True
                            st.session_state.rol = "residente"
                            st.session_state.apto_usuario = residente_match.iloc[0]["apartamento"]
                            st.rerun()
                        else:
                            st.error("❌ Usuario o clave incorrectos.")
                    else:
                        st.error("❌ Usuario o clave incorrectos.")

# --- ÁREA PRIVADA (UNA VEZ AUTENTICADO) ---
else:
    st.sidebar.markdown(f"**Bienvenido:** `{st.session_state.apto_usuario if st.session_state.rol == 'residente' else 'Administrador'}`")
    if st.sidebar.button("🔒 Cerrar Sesión"):
        st.session_state.autenticado = False
        st.session_state.rol = None
        st.session_state.apto_usuario = None
        st.rerun()

    # --- MÓDULO ADMINISTRACIÓN ---
    if st.session_state.rol == "admin":
        st.title(f"🏢 {info_edif.get('nombre', '')} - Módulo de Control")
        
        menu_admin = st.sidebar.selectbox("Opciones:", [
            "1. Datos del Edificio y Credenciales",
            "2. Gestión de Propietarios, Alícuotas y Claves",
            "3. Registro de Gastos del Mes",
            "4. Recibos y Envío WhatsApp",
            "5. Control de Pagos Recibidos"
        ])
        
        # 1. DATOS DEL EDIFICIO Y CREDENCIALES ADMIN
        if menu_admin == "1. Datos del Edificio y Credenciales":
            st.subheader("⚙️ Configuración de Datos y Credencial Principal")
            with st.form("form_edificio"):
                col1, col2 = st.columns(2)
                with col1:
                    nom_edif = st.text_input("Nombre del Edificio:", value=info_edif.get("nombre", ""))
                    rif_edif = st.text_input("RIF / Identificación Fiscal:", value=info_edif.get("rif", ""))
                    dir_edif = st.text_input("Dirección:", value=info_edif.get("direccion", ""))
                    st.markdown("---")
                    user_actual = st.text_input("Usuario Administrador:", value=info_edif.get("usuario_admin", "admin"))
                    clave_actual = st.text_input("Clave Administrador:", value=info_edif.get("clave_admin", "1234"), type="password")
                with col2:
                    banco_nom = st.text_input("Banco:", value=info_edif.get("banco", ""))
                    cuenta_num = st.text_input("Número de Cuenta:", value=info_edif.get("cuenta", ""))
                    pm_telf = st.text_input("Teléfono Pago Móvil:", value=info_edif.get("pm_telf", ""))
                    pm_ced = st.text_input("Cédula / RIF Pago Móvil:", value=info_edif.get("pm_cedula", ""))
                    
                if st.form_submit_button("💾 Guardar Cambios"):
                    run_query('''
                        UPDATE edificio_info 
                        SET nombre_edificio=?, rif=?, direccion=?, banco_nombre=?, num_cuenta=?, pago_movil_telf=?, pago_movil_cedula=?, usuario_admin=?, clave_admin=?
                        WHERE id=1
                    ''', (nom_edif, rif_edif, dir_edif, banco_nom, cuenta_num, pm_telf, pm_ced, user_actual.strip(), clave_actual), fetch_all=False)
                    st.success("Configuración actualizada correctamente.")
                    st.rerun()

        # 2. PROPIETARIOS, ALÍCUOTAS Y CLAVES
        elif menu_admin == "2. Gestión de Propietarios, Alícuotas y Claves":
            st.subheader("👥 Directorio de Propietarios y Acceso")
            tab_listado, tab_nuevo = st.tabs(["📋 Modificar Propietarios", "➕ Agregar Nuevo Apartamento"])
            
            with tab_listado:
                df_props = get_propietarios()
                edited_df = st.data_editor(
                    df_props,
                    column_config={
                        "apartamento": st.column_config.TextColumn("Apto (Usuario)", disabled=True),
                        "propietario": "Nombre Propietario",
                        "telefono": "Teléfono",
                        "alicuota": st.column_config.NumberColumn("Alícuota", format="%.4f", min_value=0.0, max_value=1.0, step=0.01),
                        "clave_residente": st.column_config.TextColumn("Clave de Acceso Apto")
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                suma_alicuotas = edited_df["alicuota"].sum() if not edited_df.empty else 0.0
                st.caption(f"📊 Suma total de alícuotas: **{suma_alicuotas*100:.2f}%**")
                
                if st.button("💾 Guardar Cambios"):
                    for _, row in edited_df.iterrows():
                        run_query(
                            "UPDATE propietarios SET propietario = ?, telefono = ?, alicuota = ?, clave_residente = ? WHERE apartamento = ?",
                            (row["propietario"], str(row["telefono"]), float(row["alicuota"]), str(row["clave_residente"]), row["apartamento"]),
                            fetch_all=False
                        )
                    st.success("Directorio de propietarios actualizado.")
                    st.rerun()
                    
            with tab_nuevo:
                with st.form("form_nuevo_apto"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        nuevo_apto = st.text_input("Apto / Usuario:")
                        nuevo_prop = st.text_input("Nombre:")
                        nueva_clave = st.text_input("Clave de Acceso Apto:", value="1234")
                    with col_b:
                        nuevo_telf = st.text_input("Teléfono:")
                        nueva_aliq = st.number_input("Alícuota:", min_value=0.0, max_value=1.0, value=0.06, step=0.01, format="%.4f")
                    
                    if st.form_submit_button("➕ Registrar Apartamento") and nuevo_apto:
                        try:
                            run_query("INSERT INTO propietarios VALUES (?, ?, ?, ?, ?)", (nuevo_apto.upper().strip(), nuevo_prop, nuevo_telf, nueva_aliq, nueva_clave), fetch_all=False)
                            st.success(f"Apartamento {nuevo_apto} registrado.")
                            st.rerun()
                        except Exception:
                            st.error("El número de apartamento ya existe.")

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
                    run_query("INSERT INTO gastos (periodo, concepto, monto, tipo, apartamento, fecha) VALUES (?, ?, ?, ?, ?, ?)",
                              (periodo, concepto, monto, tipo_gasto, apto_asig, str(fecha_gasto)), fetch_all=False)
                    st.success("Gasto registrado.")
                    st.rerun()

            st.markdown("---")
            st.dataframe(get_gastos(periodo), use_container_width=True)

        # 4. RECIBOS Y WHATSAPP
        elif menu_admin == "4. Recibos y Envío WhatsApp":
            st.subheader("📊 Recibos y Envíos WhatsApp")
            periodo_sel = st.text_input("Período a calcular", value=get_periodo_actual())
            gastos_df = get_gastos(periodo_sel)
            props_df = get_propietarios()
            
            if not gastos_df.empty and not props_df.empty:
                gastos_df["monto"] = gastos_df["monto"].astype(float)
                total_comun = gastos_df[gastos_df["tipo"] == "Común"]["monto"].sum()
                total_no_comun = gastos_df[gastos_df["tipo"] == "No Común"]["monto"].sum()
                total_general = total_comun + total_no_comun
                
                tab_gen, tab_ind = st.tabs(["📢 Recibo General", "👤 Recibo Individual"])
                with tab_gen:
                    msg_general = f"🏢 *{info_edif.get('nombre', '').upper()}*\n📋 *RELACIÓN GENERAL - {periodo_sel.upper()}*\n━━━━━━━━━━━━━━━━━━━━\n💵 *TOTAL GASTOS COMUNES:* ${total_comun:,.2f}\n"
                    if total_no_comun > 0:
                        msg_general += f"🔧 *TOTAL NO COMUNES:* ${total_no_comun:,.2f}\n"
                    msg_general += f"💰 *TOTAL GENERAL:* ${total_general:,.2f}\n━━━━━━━━━━━━━━━━━━━━\n"
                    
                    filas_resumen = []
                    for _, prop in props_df.iterrows():
                        apto = prop["apartamento"]
                        alicuota = float(prop["alicuota"])
                        cuota_c = total_comun * alicuota
                        no_c = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto)]["monto"].sum()
                        tot_apto = cuota_c + no_c
                        filas_resumen.append({"Apto": apto, "Alícuota": f"{alicuota*100:.1f}%", "Propietario": prop.get("propietario") or "-", "Total ($)": round(tot_apto, 2)})
                        msg_general += f"▫️ *Apto {apto}*: ${tot_apto:,.2f}\n"
                    
                    st.dataframe(pd.DataFrame(filas_resumen), use_container_width=True)
                    url_gen = urllib.parse.quote(msg_general)
                    st.link_button("📲 Compartir al Grupo de WhatsApp", f"https://wa.me/?text={url_gen}")

                with tab_ind:
                    apto_recibo = st.selectbox("Seleccionar Apartamento:", props_df["apartamento"].tolist())
                    prop_info = props_df[props_df["apartamento"] == apto_recibo].iloc[0]
                    alicuota_ind = float(prop_info["alicuota"])
                    cuota_comun_ind = total_comun * alicuota_ind
                    no_comunes_ind = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto_recibo)]["monto"].sum()
                    total_ind = cuota_comun_ind + no_comunes_ind
                    
                    recibo_ind = (
                        f"🏢 *{info_edif.get('nombre', '').upper()}*\n📄 *Aviso de Cobro - {periodo_sel}*\n"
                        f"🏠 *Apartamento:* {apto_recibo}\n💰 *TOTAL A PAGAR:* ${total_ind:,.2f}\n"
                    )
                    st.text_area("Vista previa:", value=recibo_ind, height=150)
                    telf = "".join(filter(str.isdigit, str(prop_info.get("telefono", ""))))
                    if telf:
                        st.link_button(f"📲 Enviar WhatsApp al Apto {apto_recibo}", f"https://wa.me/{telf}?text={urllib.parse.quote(recibo_ind)}")

        # 5. CONTROL DE PAGOS
        elif menu_admin == "5. Control de Pagos Recibidos":
            st.subheader("💳 Pagos Registrados por Residentes")
            st.dataframe(get_pagos(), use_container_width=True)

    # --- MÓDULO RESIDENTE ---
    elif st.session_state.rol == "residente":
        apto_actual = st.session_state.apto_usuario
        st.title(f"🏠 Apartamento {apto_actual}")
        
        periodo_consulta = st.text_input("Período a consultar", value=get_periodo_actual())
        props_df = get_propietarios()
        prop_data = props_df[props_df["apartamento"] == apto_actual].iloc[0]
        gastos_df = get_gastos(periodo_consulta)
        
        if gastos_df.empty:
            st.info(f"No hay recibo emitido para el período {periodo_consulta}.")
        else:
            gastos_df["monto"] = gastos_df["monto"].astype(float)
            total_comun = gastos_df[gastos_df["tipo"] == "Común"]["monto"].sum()
            alicuota = float(prop_data["alicuota"])
            cuota_comun = total_comun * alicuota
            gastos_ind = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto_actual)]["monto"].sum()
            total_pagar = cuota_comun + gastos_ind
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Alícuota", f"{alicuota*100:.1f}%")
            c2.metric("Cuota Común", f"${cuota_comun:,.2f}")
            c3.metric("Total a Pagar", f"${total_pagar:,.2f}")
            
            st.markdown("---")
            st.markdown("### 💳 Datos para la Transferencia")
            st.write(f"**Banco:** {info_edif.get('banco', '')} | **Cuenta:** {info_edif.get('cuenta', '')}")
            st.write(f"**Pago Móvil:** {info_edif.get('pm_telf', '')} | **C.I/RIF:** {info_edif.get('pm_cedula', '')}")
            
            st.markdown("---")
            st.markdown("### 📤 Reportar Transferencia / Pago Móvil")
            with st.form("form_pago"):
                monto_pago = st.number_input("Monto Transferido ($)", value=float(total_pagar))
                referencia = st.text_input("Número de Referencia")
                
                if st.form_submit_button("Registrar Comprobante"):
                    if referencia:
                        run_query("INSERT INTO pagos (apartamento, periodo, monto, referencia, fecha) VALUES (?, ?, ?, ?, ?)",
                                  (apto_actual, periodo_consulta, monto_pago, referencia, str(date.today())), fetch_all=False)
                        st.success("¡Pago reportado exitosamente!")
                    else:
                        st.error("Por favor ingrese la referencia del pago.")
