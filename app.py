import sys
import subprocess

try:
    import sqlalchemy
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "sqlalchemy", "psycopg2-binary", "pandas"])
import streamlit as st
import pandas as pd
import urllib.parse
from datetime import date
import base64
from sqlalchemy import create_engine, text

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Sistema de Condominio - Residencias El Roble",
    page_icon="🏢",
    layout="wide"
)

# --- HELPER PARA FECHAS EN ESPAÑOL ---
MESES_ESP = {
    1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril",
    5: "Mayo", 6: "Junio", 7: "Julio", 8: "Agosto",
    9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
}

def get_periodo_actual():
    hoy = date.today()
    return f"{MESES_ESP[hoy.month]} {hoy.year}"

# --- CONEXIÓN DE BASE DE DATOS (SUPABASE CON FALLBACK A SQLITE) ---
@st.cache_resource
def get_db_engine():
    try:
        if "supabase" in st.secrets and "DB_URL" in st.secrets["supabase"]:
            db_url = st.secrets["supabase"]["DB_URL"]
            return create_engine(db_url, pool_pre_ping=True)
    except Exception:
        pass
    return create_engine("sqlite:///condominio.db", check_same_thread=False)

engine = get_db_engine()

def execute_query(query, params=None, fetch=False):
    """Ejecuta consultas SQL garantizando el commit inmediato de transacciones."""
    with engine.begin() as conn:
        if params:
            result = conn.execute(text(query), params)
        else:
            result = conn.execute(text(query))
        
        if fetch:
            return result.fetchall()
        return None

def get_dataframe(query, params=None):
    """Obtiene resultados en un DataFrame de Pandas."""
    with engine.connect() as conn:
        return pd.read_sql_query(text(query), conn, params=params)

# --- INICIALIZACIÓN Y MIGRACIÓN DE LA BASE DE DATOS ---
def init_db():
    with engine.begin() as conn:
        # 1. Tabla Datos del Edificio
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS edificio_info (
                id INT PRIMARY KEY,
                nombre_edificio TEXT,
                rif TEXT,
                direccion TEXT,
                banco_nombre TEXT,
                num_cuenta TEXT,
                pago_movil_telf TEXT,
                pago_movil_cedula TEXT,
                usuario_admin TEXT DEFAULT 'admin',
                clave_admin TEXT DEFAULT '1234',
                imagen_edificio TEXT
            )
        '''))
        
        # Insertar registro base si no existe
        res = conn.execute(text("SELECT COUNT(*) FROM edificio_info")).scalar()
        if res == 0:
            conn.execute(text('''
                INSERT INTO edificio_info (id, nombre_edificio, rif, direccion, banco_nombre, num_cuenta, pago_movil_telf, pago_movil_cedula, usuario_admin, clave_admin)
                VALUES (1, 'Residencias El Roble', 'J-00000000-0', 'Caracas, Venezuela', 'Banesco', '0134-0000-00-0000000000', '0412-0000000', 'V-12345678', 'admin', '1234')
            '''))

        # 2. Tabla Propietarios y Alícuotas
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS propietarios (
                apartamento VARCHAR(10) PRIMARY KEY,
                propietario TEXT,
                telefono TEXT,
                alicuota NUMERIC(5,4),
                clave_residente TEXT DEFAULT '1234'
            )
        '''))

        res_p = conn.execute(text("SELECT COUNT(*) FROM propietarios")).scalar()
        if res_p == 0:
            conn.execute(text('''
                INSERT INTO propietarios (apartamento, propietario, telefono, alicuota, clave_residente) VALUES
                ('1A', '', '', 0.06, '1234'), ('1B', '', '', 0.06, '1234'),
                ('2',  '', '', 0.12, '1234'),
                ('3A', '', '', 0.06, '1234'), ('3B', '', '', 0.06, '1234'),
                ('4A', '', '', 0.06, '1234'), ('4B', '', '', 0.06, '1234'),
                ('5A', '', '', 0.06, '1234'), ('5B', '', '', 0.06, '1234'),
                ('6A', '', '', 0.06, '1234'), ('6B', '', '', 0.06, '1234'),
                ('7',  '', '', 0.12, '1234'),
                ('PH', '', '', 0.16, '1234')
            '''))

        # 3. Tabla Gastos (Incluye Proveedores y Cuotas Extra)
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS gastos (
                id SERIAL PRIMARY KEY,
                periodo TEXT,
                concepto TEXT,
                monto NUMERIC(10,2),
                tipo TEXT,
                apartamento TEXT DEFAULT '-',
                fecha TEXT,
                comprobante TEXT,
                proveedor TEXT DEFAULT '-',
                estado_proveedor TEXT DEFAULT 'Pagado'
            )
        '''))

        # 4. Tabla Pagos de Propietarios (Verificación)
        conn.execute(text('''
            CREATE TABLE IF NOT EXISTS pagos (
                id SERIAL PRIMARY KEY,
                apartamento TEXT,
                periodo TEXT,
                monto NUMERIC(10,2),
                referencia TEXT,
                fecha TEXT,
                comprobante_pago TEXT,
                estado TEXT DEFAULT 'Pendiente',
                notas TEXT DEFAULT ''
            )
        '''))

init_db()

# --- FUNCIONES DE CONSULTA ---
def get_edificio_info():
    try:
        df = get_dataframe("SELECT * FROM edificio_info WHERE id=1")
        if not df.empty:
            row = df.iloc[0]
            return {
                "nombre": row.get("nombre_edificio", "Residencias El Roble"),
                "rif": row.get("rif", "J-00000000-0"),
                "direccion": row.get("direccion", "Caracas, Venezuela"),
                "banco": row.get("banco_nombre", "Banesco"),
                "cuenta": row.get("num_cuenta", "0134-0000-00-0000000000"),
                "pm_telf": row.get("pago_movil_telf", "0412-0000000"),
                "pm_cedula": row.get("pago_movil_cedula", "V-12345678"),
                "usuario_admin": row.get("usuario_admin") or "admin",
                "clave_admin": str(row.get("clave_admin")) if row.get("clave_admin") else "1234",
                "imagen": row.get("imagen_edificio")
            }
    except Exception:
        pass
    return {"nombre": "Residencias El Roble", "rif": "J-00000000-0", "direccion": "Caracas", "banco": "Banesco", "cuenta": "0134", "pm_telf": "0412", "pm_cedula": "V-1234", "usuario_admin": "admin", "clave_admin": "1234", "imagen": None}

def get_propietarios():
    return get_dataframe("SELECT * FROM propietarios ORDER BY apartamento")

def get_gastos(periodo=None):
    if periodo:
        return get_dataframe("SELECT * FROM gastos WHERE periodo = :p ORDER BY id DESC", {"p": periodo})
    return get_dataframe("SELECT * FROM gastos ORDER BY id DESC")

def get_pagos():
    return get_dataframe("SELECT * FROM pagos ORDER BY id DESC")

# --- ESTADOS DE SESIÓN ---
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
if "rol" not in st.session_state:
    st.session_state.rol = None
if "apto_usuario" not in st.session_state:
    st.session_state.apto_usuario = None

info_edif = get_edificio_info()

# --- PANTALLA DE ACCESO UNIFICADA ---
if not st.session_state.autenticado:
    st.markdown("<h2 style='text-align: center;'>🏢 Sistema de Condominio</h2>", unsafe_allow_html=True)
    
    if info_edif.get("imagen") and pd.notna(info_edif["imagen"]):
        try:
            img_edif_bytes = base64.b64decode(info_edif["imagen"])
            c_l, c_m, c_r = st.columns([1, 1, 1])
            with c_m:
                st.image(img_edif_bytes, use_column_width=True)
        except Exception:
            pass
            
    st.markdown(f"<h4 style='text-align: center;'>{info_edif.get('nombre', '')}</h4>", unsafe_allow_html=True)
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
                
                if usr == usr_admin and clave_ingresada == pass_admin:
                    st.session_state.autenticado = True
                    st.session_state.rol = "admin"
                    st.rerun()
                else:
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

# --- ÁREA PRIVADA ---
else:
    if info_edif.get("imagen") and pd.notna(info_edif["imagen"]):
        try:
            img_edif_bytes = base64.b64decode(info_edif["imagen"])
            st.sidebar.image(img_edif_bytes, use_column_width=True)
        except Exception:
            pass

    st.sidebar.markdown(f"**Bienvenido:** `{st.session_state.apto_usuario if st.session_state.rol == 'residente' else 'Administrador'}`")
    if st.sidebar.button("🔒 Cerrar Sesión"):
        st.session_state.autenticado = False
        st.session_state.rol = None
        st.session_state.apto_usuario = None
        st.rerun()

    # ==========================================
    # MÓDULO ADMINISTRADOR
    # ==========================================
    if st.session_state.rol == "admin":
        st.title(f"🏢 {info_edif.get('nombre', '')} - Control Administrativo")
        
        menu_admin = st.sidebar.selectbox("Opciones:", [
            "1. Datos del Edificio y Credenciales",
            "2. Propietarios, Alícuotas y Claves",
            "3. Gastos, Proveedores y Cuotas Extra",
            "4. Recibos y Envío WhatsApp",
            "5. Verificación de Pagos de Residentes"
        ])
        
        # 1. DATOS DEL EDIFICIO
        if menu_admin == "1. Datos del Edificio y Credenciales":
            st.subheader("⚙️ Configuración General y Datos Bancarios")
            
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
                
                nueva_foto_edificio = st.file_uploader("🖼️ Foto del Edificio (PNG, JPG)", type=["png", "jpg", "jpeg"])
                    
                if st.form_submit_button("💾 Guardar Cambios"):
                    str_foto = info_edif.get("imagen")
                    if nueva_foto_edificio is not None:
                        str_foto = base64.b64encode(nueva_foto_edificio.read()).decode('utf-8')
                        
                    execute_query('''
                        UPDATE edificio_info 
                        SET nombre_edificio=:n, rif=:r, direccion=:d, banco_nombre=:b, num_cuenta=:c, pago_movil_telf=:pt, pago_movil_cedula=:pc, usuario_admin=:u, clave_admin=:cl, imagen_edificio=:img
                        WHERE id=1
                    ''', {
                        "n": nom_edif, "r": rif_edif, "d": dir_edif, "b": banco_nom, "c": cuenta_num,
                        "pt": pm_telf, "pc": pm_ced, "u": user_actual.strip(), "cl": clave_actual, "img": str_foto
                    })
                    st.success("Configuración actualizada correctamente.")
                    st.rerun()

        # 2. PROPIETARIOS
        elif menu_admin == "2. Propietarios, Alícuotas y Claves":
            st.subheader("👥 Directorio de Propietarios")
            tab_listado, tab_nuevo = st.tabs(["📋 Modificar Propietarios", "➕ Agregar Apartamento"])
            
            with tab_listado:
                df_props = get_propietarios()
                edited_df = st.data_editor(
                    df_props,
                    column_config={
                        "apartamento": st.column_config.TextColumn("Apto", disabled=True),
                        "propietario": "Nombre Propietario",
                        "telefono": "Teléfono WhatsApp",
                        "alicuota": st.column_config.NumberColumn("Alícuota", format="%.4f", min_value=0.0, max_value=1.0),
                        "clave_residente": "Clave de Acceso"
                    },
                    use_container_width=True,
                    hide_index=True
                )
                
                suma_aliq = edited_df["alicuota"].astype(float).sum() if not edited_df.empty else 0.0
                st.caption(f"📊 Suma Total de Alícuotas: **{suma_aliq*100:.2f}%**")
                
                if st.button("💾 Guardar Cambios de Propietarios"):
                    for _, row in edited_df.iterrows():
                        execute_query(
                            "UPDATE propietarios SET propietario = :p, telefono = :t, alicuota = :a, clave_residente = :c WHERE apartamento = :ap",
                            {"p": row["propietario"], "t": str(row["telefono"]), "a": float(row["alicuota"]), "c": str(row["clave_residente"]), "ap": row["apartamento"]}
                        )
                    st.success("Directorio de propietarios actualizado.")
                    st.rerun()
                    
            with tab_nuevo:
                with st.form("form_nuevo_apto"):
                    col_a, col_b = st.columns(2)
                    with col_a:
                        nuevo_apto = st.text_input("Apto / Identificador:")
                        nuevo_prop = st.text_input("Nombre del Propietario:")
                        nueva_clave = st.text_input("Clave de Acceso:", value="1234")
                    with col_b:
                        nuevo_telf = st.text_input("Teléfono WhatsApp:")
                        nueva_aliq = st.number_input("Alícuota (ej. 0.06):", min_value=0.0, max_value=1.0, value=0.06, format="%.4f")
                    
                    if st.form_submit_button("➕ Registrar Apartamento") and nuevo_apto:
                        try:
                            execute_query("INSERT INTO propietarios VALUES (:ap, :pr, :tl, :al, :cl)", {
                                "ap": nuevo_apto.upper().strip(), "pr": nuevo_prop, "tl": nuevo_telf, "al": nueva_aliq, "cl": nueva_clave
                            })
                            st.success(f"Apartamento {nuevo_apto} registrado.")
                            st.rerun()
                        except Exception:
                            st.error("El número de apartamento ya existe.")

        # 3. GASTOS, PROVEEDORES Y CUOTAS EXTRA
        elif menu_admin == "3. Gastos, Proveedores y Cuotas Extra":
            st.subheader("📝 Registro de Gastos, Proveedores y Cuotas Extraordinarias")
            
            with st.form("form_gasto"):
                col1, col2 = st.columns(2)
                with col1:
                    periodo = st.text_input("Período / Mes:", value=get_periodo_actual())
                    concepto = st.text_input("Concepto del Gasto o Cuota Extra:")
                    monto = st.number_input("Monto Total ($):", min_value=0.0, step=10.0, format="%.2f")
                    proveedor = st.text_input("Proveedor / Empresa del Servicio:", value="-")
                with col2:
                    tipo_gasto = st.selectbox("Tipo de Carga:", ["Común", "Cuota Extraordinaria", "No Común"])
                    apto_asig = "-"
                    if tipo_gasto == "No Común":
                        df_props = get_propietarios()
                        apto_asig = st.selectbox("Asignar a Apartamento:", df_props["apartamento"].tolist() if not df_props.empty else ["1A"])
                    
                    estado_prov = st.selectbox("Estatus del Pago al Proveedor:", ["Pagado", "Pendiente de Pago"])
                    fecha_gasto = st.date_input("Fecha de Registro:", date.today())
                
                archivo_imagen = st.file_uploader("📷 Adjuntar Factura o Comprobante de Servicio (Opcional)", type=["png", "jpg", "jpeg"])
                
                if st.form_submit_button("💾 Guardar Registro"):
                    if concepto and monto > 0:
                        img_str = None
                        if archivo_imagen is not None:
                            img_str = base64.b64encode(archivo_imagen.read()).decode('utf-8')
                        
                        execute_query('''
                            INSERT INTO gastos (periodo, concepto, monto, tipo, apartamento, fecha, comprobante, proveedor, estado_proveedor)
                            VALUES (:p, :c, :m, :t, :a, :f, :comp, :prov, :ep)
                        ''', {
                            "p": periodo, "c": concepto, "m": monto, "t": tipo_gasto,
                            "a": apto_asig, "f": str(fecha_gasto), "comp": img_str,
                            "prov": proveedor, "ep": estado_prov
                        })
                        st.success("✅ Gasto registrado y guardado exitosamente.")
                        st.rerun()
                    else:
                        st.error("Por favor completa el concepto y un monto mayor a cero.")

            st.markdown("---")
            st.subheader(f"📋 Gastos e Inventario del Período ({periodo})")
            df_gastos = get_gastos(periodo)
            
            if not df_gastos.empty:
                for _, row in df_gastos.iterrows():
                    color_tipo = "🔴" if row['tipo'] == 'Cuota Extraordinaria' else ("🟡" if row['tipo'] == 'No Común' else "🔵")
                    with st.expander(f"{color_tipo} {row['concepto']} - ${float(row['monto']):,.2f} [{row['tipo']}]"):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.write(f"**Fecha:** {row['fecha']}")
                            st.write(f"**Proveedor:** {row.get('proveedor', '-')}")
                            st.write(f"**Estatus Pago Proveedor:** `{row.get('estado_proveedor', 'Pagado')}`")
                        with c2:
                            st.write(f"**Asignación:** {row['apartamento']}")
                            if row.get('comprobante') and pd.notna(row['comprobante']):
                                try:
                                    img_bytes = base64.b64decode(row['comprobante'])
                                    st.image(img_bytes, caption="Factura / Comprobante", width=250)
                                except Exception:
                                    st.warning("No se pudo cargar la imagen.")
                        
                        if st.button("🗑️ Eliminar Registro", key=f"del_{row['id']}"):
                            execute_query("DELETE FROM gastos WHERE id = :id", {"id": row['id']})
                            st.success(f"Registro '{row['concepto']}' eliminado.")
                            st.rerun()
            else:
                st.info("No hay gastos ni cuotas extras en este período.")

        # 4. RECIBOS Y WHATSAPP
        elif menu_admin == "4. Recibos y Envío WhatsApp":
            st.subheader("📊 Emisión de Recibos y Notificaciones")
            periodo_sel = st.text_input("Período a Calcular:", value=get_periodo_actual())
            gastos_df = get_gastos(periodo_sel)
            props_df = get_propietarios()
            
            if not gastos_df.empty and not props_df.empty:
                gastos_df["monto"] = gastos_df["monto"].astype(float)
                total_comun = gastos_df[gastos_df["tipo"] == "Común"]["monto"].sum()
                total_cuota_extra = gastos_df[gastos_df["tipo"] == "Cuota Extraordinaria"]["monto"].sum()
                total_no_comun = gastos_df[gastos_df["tipo"] == "No Común"]["monto"].sum()
                total_general = total_comun + total_cuota_extra + total_no_comun
                
                tab_gen, tab_ind = st.tabs(["📢 Recibo General", "👤 Recibo Individual por Apto"])
                with tab_gen:
                    msg_general = f"🏢 *{info_edif.get('nombre', '').upper()}*\n📋 *RELACIÓN DE COBRO - {periodo_sel.upper()}*\n━━━━━━━━━━━━━━━━━━━━\n"
                    msg_general += f"💵 *Gastos Comunes:* ${total_comun:,.2f}\n"
                    if total_cuota_extra > 0:
                        msg_general += f"🚨 *Cuota Extraordinaria:* ${total_cuota_extra:,.2f}\n"
                    if total_no_comun > 0:
                        msg_general += f"🔧 *Gastos No Comunes:* ${total_no_comun:,.2f}\n"
                    msg_general += f"💰 *TOTAL MES:* ${total_general:,.2f}\n━━━━━━━━━━━━━━━━━━━━\n"
                    
                    filas_resumen = []
                    for _, prop in props_df.iterrows():
                        apto = prop["apartamento"]
                        alicuota = float(prop["alicuota"])
                        c_comun = total_comun * alicuota
                        c_extra = total_cuota_extra * alicuota
                        no_c = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto)]["monto"].sum()
                        tot_apto = c_comun + c_extra + no_c
                        
                        filas_resumen.append({
                            "Apto": apto, "Alícuota": f"{alicuota*100:.1f}%",
                            "Cuota Común": round(c_comun, 2), "Cuota Extra": round(c_extra, 2),
                            "No Común": round(no_c, 2), "TOTAL ($)": round(tot_apto, 2)
                        })
                        msg_general += f"▫️ *Apto {apto}*: ${tot_apto:,.2f}\n"
                    
                    st.dataframe(pd.DataFrame(filas_resumen), use_container_width=True)
                    url_gen = urllib.parse.quote(msg_general)
                    st.link_button("📲 Enviar Resumen al Grupo de WhatsApp", f"https://wa.me/?text={url_gen}")

                with tab_ind:
                    apto_recibo = st.selectbox("Seleccionar Apartamento:", props_df["apartamento"].tolist())
                    prop_info = props_df[props_df["apartamento"] == apto_recibo].iloc[0]
                    alicuota_ind = float(prop_info["alicuota"])
                    
                    c_comun_i = total_comun * alicuota_ind
                    c_extra_i = total_cuota_extra * alicuota_ind
                    no_c_i = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto_recibo)]["monto"].sum()
                    total_ind = c_comun_i + c_extra_i + no_c_i
                    
                    recibo_ind = f"🏢 *{info_edif.get('nombre', '').upper()}*\n📄 *AVISO DE COBRO - {periodo_sel}*\n━━━━━━━━━━━━━━━━━━━━\n"
                    recibo_ind += f"🏠 *Apartamento:* {apto_recibo} ({prop_info.get('propietario', '')})\n"
                    recibo_ind += f"📊 *Alícuota:* {alicuota_ind*100:.1f}%\n"
                    recibo_ind += f"▫️ Cuota Común: ${c_comun_i:,.2f}\n"
                    if c_extra_i > 0:
                        recibo_ind += f"🚨 Cuota Extraordinaria: ${c_extra_i:,.2f}\n"
                    if no_c_i > 0:
                        recibo_ind += f"🔧 Gastos No Comunes: ${no_c_i:,.2f}\n"
                    recibo_ind += f"━━━━━━━━━━━━━━━━━━━━\n💰 *TOTAL A PAGAR:* ${total_ind:,.2f}\n"
                    
                    st.text_area("Vista previa del mensaje:", value=recibo_ind, height=180)
                    telf = "".join(filter(str.isdigit, str(prop_info.get("telefono", ""))))
                    if telf:
                        st.link_button(f"📲 Enviar WhatsApp Privado a Apto {apto_recibo}", f"https://wa.me/{telf}?text={urllib.parse.quote(recibo_ind)}")

        # 5. VERIFICACIÓN DE PAGOS
        elif menu_admin == "5. Verificación de Pagos de Residentes":
            st.subheader("💳 Verificación y Aprobación de Pagos Recibidos")
            df_pagos = get_pagos()
            
            if not df_pagos.empty:
                for _, row in df_pagos.iterrows():
                    estado = row.get("estado", "Pendiente")
                    color_status = "🟡" if estado == "Pendiente" else ("🟢" if estado == "Aprobado" else "🔴")
                    
                    with st.expander(f"{color_status} Apto {row['apartamento']} - ${float(row['monto']):,.2f} (Ref: {row['referencia']}) [{estado}]"):
                        c1, c2 = st.columns(2)
                        with c1:
                            st.write(f"**Período:** {row['periodo']}")
                            st.write(f"**Fecha de Pago:** {row['fecha']}")
                            st.write(f"**Número de Referencia:** `{row['referencia']}`")
                            st.write(f"**Estatus:** `{estado}`")
                        with c2:
                            if row.get('comprobante_pago') and pd.notna(row['comprobante_pago']):
                                try:
                                    img_bytes = base64.b64decode(row['comprobante_pago'])
                                    st.image(img_bytes, caption=f"Comprobante Apto {row['apartamento']}", width=250)
                                except Exception:
                                    st.warning("No se pudo cargar la captura del comprobante.")
                            else:
                                st.info("El residente no adjunto foto del comprobante.")
                        
                        col_btn1, col_btn2 = st.columns(2)
                        with col_btn1:
                            if st.button("✅ Aprobar Pago", key=f"ap_{row['id']}"):
                                execute_query("UPDATE pagos SET estado = 'Aprobado' WHERE id = :id", {"id": row['id']})
                                st.success("Pago marcado como APROBADO.")
                                st.rerun()
                        with col_btn2:
                            if st.button("❌ Rechazar Pago", key=f"rec_{row['id']}"):
                                execute_query("UPDATE pagos SET estado = 'Rechazado' WHERE id = :id", {"id": row['id']})
                                st.error("Pago RECHAZADO.")
                                st.rerun()
            else:
                st.info("No hay pagos registrados por verificar.")

    # ==========================================
    # MÓDULO RESIDENTE
    # ==========================================
    elif st.session_state.rol == "residente":
        apto_actual = st.session_state.apto_usuario
        st.title(f"🏠 Panel Residente - Apartamento {apto_actual}")
        
        tab_recibo, tab_reportar = st.tabs(["📄 Consulta de Recibo", "📤 Reportar Pago Realizado"])
        
        props_df = get_propietarios()
        prop_data = props_df[props_df["apartamento"] == apto_actual].iloc[0]
        periodo_consulta = st.text_input("Período a Consultar:", value=get_periodo_actual())
        gastos_df = get_gastos(periodo_consulta)
        
        with tab_recibo:
            if gastos_df.empty:
                st.info(f"No hay relación de cobro emitida aún para el período {periodo_consulta}.")
            else:
                gastos_df["monto"] = gastos_df["monto"].astype(float)
                total_comun = gastos_df[gastos_df["tipo"] == "Común"]["monto"].sum()
                total_extra = gastos_df[gastos_df["tipo"] == "Cuota Extraordinaria"]["monto"].sum()
                alicuota = float(prop_data["alicuota"])
                
                cuota_comun = total_comun * alicuota
                cuota_extra = total_extra * alicuota
                gastos_ind = gastos_df[(gastos_df["tipo"] == "No Común") & (gastos_df["apartamento"] == apto_actual)]["monto"].sum()
                total_pagar = cuota_comun + cuota_extra + gastos_ind
                
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Alícuota", f"{alicuota*100:.1f}%")
                c2.metric("Cuota Común", f"${cuota_comun:,.2f}")
                c3.metric("Cuota Extra", f"${cuota_extra:,.2f}")
                c4.metric("Total Mes", f"${total_pagar:,.2f}")
                
                st.markdown("---")
                st.subheader("🧾 Soportes y Facturas del Mes")
                for _, row in gastos_df.iterrows():
                    if row.get('comprobante') and pd.notna(row['comprobante']):
                        with st.expander(f"📷 Ver Factura: {row['concepto']} (${float(row['monto']):,.2f})"):
                            try:
                                img_bytes = base64.b64decode(row['comprobante'])
                                st.image(img_bytes, caption=row['concepto'], width=300)
                            except Exception:
                                st.write("Vista previa no disponible.")

        with tab_reportar:
            st.markdown("### 💳 Datos Bancarios para Transferencias")
            st.write(f"**Banco:** {info_edif.get('banco', '')} | **Cuenta:** {info_edif.get('cuenta', '')}")
            st.write(f"**Pago Móvil:** {info_edif.get('pm_telf', '')} | **C.I/RIF:** {info_edif.get('pm_cedula', '')}")
            st.markdown("---")
            
            st.subheader("📤 Formulario de Reporte de Pago")
            with st.form("form_reporte_pago"):
                monto_pagado = st.number_input("Monto Transferido ($):", min_value=0.0, format="%.2f")
                referencia_pago = st.text_input("Número de Referencia del Banco / Pago Móvil:")
                fecha_pago = st.date_input("Fecha del Pago:", date.today())
                captura_comp = st.file_uploader("📷 Adjuntar Captura o Foto del Comprobante (Obligatorio)", type=["png", "jpg", "jpeg"])
                
                if st.form_submit_button("📤 Registrar Comprobante de Pago"):
                    if referencia_pago and captura_comp is not None and monto_pagado > 0:
                        img_pago_str = base64.b64encode(captura_comp.read()).decode('utf-8')
                        execute_query('''
                            INSERT INTO pagos (apartamento, periodo, monto, referencia, fecha, comprobante_pago, estado)
                            VALUES (:ap, :p, :m, :r, :f, :comp, 'Pendiente')
                        ''', {
                            "ap": apto_actual, "p": periodo_consulta, "m": monto_pagado,
                            "r": referencia_pago, "f": str(fecha_pago), "comp": img_pago_str
                        })
                        st.success("✅ ¡Pago reportado exitosamente! El administrador lo verificará a la brevedad.")
                        st.rerun()
                    else:
                        st.error("Por favor ingresa el monto, número de referencia y adjunta la imagen del comprobante.")
            
            st.markdown("---")
            st.subheader("📜 Tus Pagos Reportados")
            df_mis_pagos = get_dataframe("SELECT * FROM pagos WHERE apartamento = :ap ORDER BY id DESC", {"ap": apto_actual})
            if not df_mis_pagos.empty:
                st.dataframe(
                    df_mis_pagos[["periodo", "fecha", "monto", "referencia", "estado"]],
                    column_config={
                        "periodo": "Período", "fecha": "Fecha", "monto": "Monto ($)",
                        "referencia": "Referencia", "estado": "Estatus"
                    },
                    use_container_width=True, hide_index=True
                )
            else:
                st.info("No has reportado pagos recientemente.")
