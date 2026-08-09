import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
import streamlit.components.v1 as components

st.set_page_config(page_title="Gestión de Condominio", page_icon="🏢", layout="wide")

# Cambiamos a v4 para agregar soporte de claves individuales por apartamento
DB_NAME = 'condominio_v4.db'

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- INYECCIÓN DE PWA Y MODOS PANTALLA COMPLETA ---
st.html("""
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="apple-mobile-web-app-title" content="Condominio">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="theme-color" content="#2563eb">
    <link rel="apple-touch-icon" href="https://cdn-icons-png.flaticon.com/512/2558/2558042.png">
    <link rel="icon" type="image/png" sizes="192x192" href="https://cdn-icons-png.flaticon.com/512/2558/2558042.png">
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        .stAppHeader {display: none;}
    </style>
""")

# --- INICIALIZACIÓN DE LA BASE DE DATOS ---
def inicializar_bd():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # 1. Tabla Edificio
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS edificio (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            rif TEXT,
            direccion TEXT,
            logo_url TEXT
        )""")

        cursor.execute("SELECT COUNT(*) FROM edificio")
        if cursor.fetchone()[0] == 0:
            cursor.execute("""
                INSERT INTO edificio (id, nombre, rif, direccion, logo_url) 
                VALUES (1, 'RESIDENCIAS EL PARQUE', 'J-12345678-9', 'Av. Principal, Calle 4', '')
            """)

        # 2. Tabla Apartamentos (Con columna 'clave')
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS apartamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT UNIQUE,
            propietario TEXT,
            telefono TEXT,
            alicuota REAL,
            clave TEXT DEFAULT '1234'
        )""")

        # Carga inicial predeterminada (Clave inicial '1234' para cada apto)
        cursor.execute("SELECT COUNT(*) FROM apartamentos")
        if cursor.fetchone()[0] == 0:
            aptos_iniciales = [
                ('1A', 'Propietario 1A', '', 0.06, '1234'),
                ('1B', 'Propietario 1B', '', 0.06, '1234'),
                ('3A', 'Propietario 3A', '', 0.06, '1234'),
                ('3B', 'Propietario 3B', '', 0.06, '1234'),
                ('4A', 'Propietario 4A', '', 0.06, '1234'),
                ('4B', 'Propietario 4B', '', 0.06, '1234'),
                ('5A', 'Propietario 5A', '', 0.06, '1234'),
                ('5B', 'Propietario 5B', '', 0.06, '1234'),
                ('6A', 'Propietario 6A', '', 0.06, '1234'),
                ('6B', 'Propietario 6B', '', 0.06, '1234'),
                ('2',  'Propietario 2',  '', 0.12, '1234'),
                ('7',  'Propietario 7',  '', 0.12, '1234'),
                ('PH', 'Propietario PH', '', 0.16, '1234')
            ]
            cursor.executemany("""
                INSERT INTO apartamentos (numero, propietario, telefono, alicuota, clave)
                VALUES (?, ?, ?, ?, ?)
            """, aptos_iniciales)

        # 3. Tabla Proveedores
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT UNIQUE,
            rif TEXT,
            telefono TEXT,
            servicio TEXT
        )""")

        # 4. Tabla Gastos
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo TEXT,
            descripcion TEXT,
            monto REAL,
            es_comun INTEGER,
            apto_no_comun TEXT
        )""")

        # 5. Tabla Pagos Propietarios
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_propietarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            periodo TEXT,
            apartamento_id INTEGER,
            apartamento TEXT,
            monto REAL,
            referencia TEXT,
            metodo TEXT,
            estado TEXT
        )""")

        # 6. Tabla Pagos Proveedores
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pagos_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            proveedor TEXT,
            rif_proveedor TEXT,
            concepto TEXT,
            monto REAL,
            num_factura TEXT
        )""")

        conn.commit()

inicializar_bd()

# --- FUNCIONES AUXILIARES ---
def get_edificio():
    with get_connection() as conn:
        df = pd.read_sql("SELECT * FROM edificio WHERE id=1", conn)
    if not df.empty:
        res = df.iloc[0].to_dict()
        if not res.get('logo_url'):
            res['logo_url'] = ''
        return res
    return {"nombre": "Condominio", "rif": "J-00000000-0", "direccion": "N/A", "logo_url": ""}

def get_apartamentos():
    with get_connection() as conn:
        return pd.read_sql("SELECT * FROM apartamentos ORDER BY numero", conn)

def get_proveedores():
    with get_connection() as conn:
        return pd.read_sql("SELECT * FROM proveedores ORDER BY nombre", conn)

# --- LOGIN CON CLAVES INDIVIDUALES ---
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
    st.session_state['rol'] = None
    st.session_state['apto_login'] = None

if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema de Condominio")
    tipo_usuario = st.radio("Seleccione el tipo de usuario:", ["Administrador", "Vecino / Propietario"])
    
    if tipo_usuario == "Administrador":
        clave = st.text_input("Clave Administrador:", type="password")
        if st.button("Iniciar Sesión"):
            if clave == "admin123":
                st.session_state['autenticado'] = True
                st.session_state['rol'] = "Admin"
                st.session_state['apto_login'] = None
                st.rerun()
            else:
                st.error("❌ Clave de Administrador incorrecta.")
    else:
        aptos_df = get_apartamentos()
        lista_aptos = aptos_df['numero'].tolist() if not aptos_df.empty else []
        apto_sel = st.selectbox("Seleccione su Apartamento:", lista_aptos)
        clave_apto = st.text_input("Ingrese su Clave Personal:", type="password")
        
        if st.button("Iniciar Sesión"):
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT clave FROM apartamentos WHERE numero = ?", (apto_sel,))
                res = cursor.fetchone()
                
            if res and res[0] == clave_apto:
                st.session_state['autenticado'] = True
                st.session_state['rol'] = "Vecino"
                st.session_state['apto_login'] = apto_sel
                st.rerun()
            else:
                st.error("❌ Clave incorrecta para este apartamento.")
    st.stop()

# --- NAVEGACIÓN Y SESIÓN ---
st.sidebar.title("🏢 Menú Condominio")
if st.session_state['rol'] == "Admin":
    st.sidebar.write("**Usuario:** Administrador")
else:
    st.sidebar.write(f"**Usuario:** Propietario Apto {st.session_state['apto_login']}")

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state['autenticado'] = False
    st.session_state['rol'] = None
    st.session_state['apto_login'] = None
    st.rerun()

if st.session_state['rol'] == "Admin":
    opcion = st.sidebar.radio("Navegación:", [
        "0. Datos del Edificio (Logo / RIF)",
        "1. Registro de Propietarios & Claves",
        "2. Registro de Proveedores",
        "3. Registrar Gastos del Mes",
        "4. Generar Recibo & WhatsApp / PDF",
        "5. Registrar Pago de Apartamento",
        "6. Reportes (Morosidad y Proveedores)"
    ])
else:
    opcion = st.sidebar.radio("Navegación:", [
        "4. Ver Mi Recibo de Condominio",
        "🔑 Cambiar Mi Clave"
    ])

edificio = get_edificio()

# --- MÓDULO 0: DATOS DEL EDIFICIO ---
if opcion == "0. Datos del Edificio (Logo / RIF)":
    st.header("⚙️ Configuración del Condominio")
    with st.form("form_edificio"):
        nombre_e = st.text_input("Nombre del Condominio / Edificio:", value=edificio['nombre'])
        rif_e = st.text_input("RIF:", value=edificio['rif'])
        dir_e = st.text_area("Dirección:", value=edificio['direccion'])
        logo_e = st.text_input("URL del Logo (Opcional):", value=edificio.get('logo_url', ''))
        btn_edificio = st.form_submit_button("💾 Actualizar Datos del Edificio")
        if btn_edificio:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE edificio 
                    SET nombre = ?, rif = ?, direccion = ?, logo_url = ?
                    WHERE id = 1
                """, (nombre_e, rif_e, dir_e, logo_e))
                conn.commit()
            st.success("¡Datos actualizados!")
            st.rerun()

# --- MÓDULO 1: REGISTRO Y CLAVES (ADMIN) ---
elif opcion == "1. Registro de Propietarios & Claves":
    st.header("🏠 Gestión de Apartamentos, Propietarios y Claves")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Registrar / Editar Apto")
        numero_apto = st.text_input("Número de Apto (ej: 1A, PH):").strip().upper()
        propietario = st.text_input("Nombre del Propietario:")
        telefono = st.text_input("Teléfono WhatsApp (ej: +584121234567):")
        alicuota_pct = st.number_input("Alícuota (%):", min_value=0.0, max_value=100.0, value=6.0, step=0.1)
        clave_apto = st.text_input("Clave de Acceso:", value="1234")
        
        if st.button("💾 Guardar Apartamento"):
            if numero_apto != "" and propietario != "":
                alicuota_real = alicuota_pct / 100.0
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT id FROM apartamentos WHERE numero = ?", (numero_apto,))
                    existe = cursor.fetchone()
                    
                    if existe:
                        cursor.execute("""
                            UPDATE apartamentos 
                            SET propietario = ?, telefono = ?, alicuota = ?, clave = ?
                            WHERE numero = ?
                        """, (propietario, telefono, alicuota_real, clave_apto, numero_apto))
                    else:
                        cursor.execute("""
                            INSERT INTO apartamentos (numero, propietario, telefono, alicuota, clave)
                            VALUES (?, ?, ?, ?, ?)
                        """, (numero_apto, propietario, telefono, alicuota_real, clave_apto))
                    conn.commit()
                st.success(f"Apartamento {numero_apto} guardado exitosamente.")
                st.rerun()

    with col2:
        st.subheader("Listado de Apartamentos y Claves")
        df_aptos = get_apartamentos()
        if not df_aptos.empty:
            df_display = df_aptos.copy()
            df_display['alicuota'] = df_display['alicuota'].apply(lambda x: f"{x*100:.2f}%")
            st.dataframe(df_display[['numero', 'propietario', 'telefono', 'alicuota', 'clave']], use_container_width=True)
        else:
            st.info("Aún no hay apartamentos registrados.")

# --- MÓDULO CAMBIAR CLAVE (VECINO) ---
elif opcion == "🔑 Cambiar Mi Clave":
    st.header(f"🔑 Cambiar Clave del Apartamento {st.session_state['apto_login']}")
    nueva_clave = st.text_input("Ingrese la nueva clave deseada:", type="password")
    confirmar = st.text_input("Confirme la nueva clave:", type="password")
    
    if st.button("💾 Actualizar Clave"):
        if nueva_clave != "" and nueva_clave == confirmar:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE apartamentos SET clave = ? WHERE numero = ?", (nueva_clave, st.session_state['apto_login']))
                conn.commit()
            st.success("¡Clave actualizada correctamente!")
        else:
            st.error("Las claves no coinciden o están vacías.")

# --- MÓDULO 2: PROVEEDORES ---
elif opcion == "2. Registro de Proveedores":
    st.header("🚚 Gestión de Proveedores")
    tab1, tab2 = st.tabs(["Directorio de Proveedores", "Registrar Pago a Proveedor"])
    with tab1:
        c1, c2 = st.columns([1, 2])
        with c1:
            nombre_prov = st.text_input("Nombre / Razón Social:")
            rif_prov = st.text_input("RIF:")
            tel_prov = st.text_input("Teléfono:")
            servicio_prov = st.text_input("Servicio:")
            if st.button("💾 Guardar Proveedor"):
                if nombre_prov.strip() != "":
                    with get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("INSERT OR REPLACE INTO proveedores (nombre, rif, telefono, servicio) VALUES (?,?,?,?)",
                                       (nombre_prov, rif_prov, tel_prov, servicio_prov))
                        conn.commit()
                    st.success("Proveedor guardado.")
                    st.rerun()
        with c2:
            st.dataframe(get_proveedores()[['nombre', 'rif', 'telefono', 'servicio']], use_container_width=True)

    with tab2:
        df_p = get_proveedores()
        if not df_p.empty:
            prov_sel = st.selectbox("Proveedor:", df_p['nombre'].tolist())
            fecha_pago = st.date_input("Fecha del Pago:")
            monto_pago = st.number_input("Monto ($):", min_value=0.0)
            num_fact = st.text_input("Factura No:")
            concepto_pago = st.text_input("Concepto:")
            if st.button("💾 Registrar Pago Proveedor"):
                prov_data = df_p[df_p['nombre'] == prov_sel].iloc[0]
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO pagos_proveedores (fecha, proveedor, rif_proveedor, concepto, monto, num_factura)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (str(fecha_pago), prov_sel, prov_data['rif'], concepto_pago, monto_pago, num_fact))
                    conn.commit()
                st.success("Pago registrado.")

# --- MÓDULO 3: GASTOS ---
elif opcion == "3. Registrar Gastos del Mes":
    st.header("📝 Cargar Gastos Comunes y No Comunes")
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período (Año-Mes):", "2026-05")
        descripcion = st.text_input("Descripción del Gasto:")
        monto = st.number_input("Monto ($):", min_value=0.0)
    with col2:
        tipo_gasto = st.selectbox("Tipo de Gasto:", ["Común (Aplica a todos por alícuota)", "No Común (Aplica a un solo Apto)"])
        apto_destino = None
        if "No Común" in tipo_gasto:
            aptos = get_apartamentos()
            if not aptos.empty:
                apto_destino = st.selectbox("Apartamento Responsable:", aptos['numero'].tolist())
            
    if st.button("💾 Guardar Gasto"):
        if descripcion.strip() != "":
            es_comun = 1 if "Común" in tipo_gasto else 0
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO gastos (periodo, descripcion, monto, es_comun, apto_no_comun) VALUES (?,?,?,?,?)",
                    (periodo, descripcion, monto, es_comun, apto_destino)
                )
                conn.commit()
            st.success("Gasto registrado con éxito.")

# --- MÓDULO 4: RECIBOS ---
elif opcion in ["4. Generar Recibo & WhatsApp / PDF", "4. Ver Mi Recibo de Condominio"]:
    st.header("📄 Recibo de Condominio")
    
    aptos_df = get_apartamentos()
    if aptos_df.empty:
        st.warning("⚠️ No hay apartamentos registrados.")
        st.stop()
        
    col_p, col_a = st.columns(2)
    with col_p:
        periodo = st.text_input("Período a consultar (Año-Mes):", "2026-05")
        
    with col_a:
        if st.session_state['rol'] == "Admin":
            apto_sel = st.selectbox("Seleccionar Apartamento:", aptos_df['numero'].tolist())
        else:
            apto_sel = st.session_state['apto_login']
            st.info(f"Mostrando información de su apartamento: **{apto_sel}**")
        
    apto_info = aptos_df[aptos_df['numero'] == apto_sel].iloc[0]
    
    with get_connection() as conn:
        gastos_comunes = pd.read_sql("SELECT * FROM gastos WHERE periodo = ? AND es_comun = 1", conn, params=(periodo,))
        gastos_no_comunes = pd.read_sql("SELECT * FROM gastos WHERE periodo = ? AND es_comun = 0 AND apto_no_comun = ?", conn, params=(periodo, apto_sel))
        pago_registrado = pd.read_sql("SELECT * FROM pagos_propietarios WHERE apartamento = ? AND periodo = ?", conn, params=(apto_sel, periodo))
    
    total_comun = float(gastos_comunes['monto'].sum()) if not gastos_comunes.empty else 0.0
    alicuota_pct = float(apto_info['alicuota'])
    cuota_comun = total_comun * alicuota_pct
    total_no_comun = float(gastos_no_comunes['monto'].sum()) if not gastos_no_comunes.empty else 0.0
    monto_total = cuota_comun + total_no_comun
    estado_pago = "✅ PAGADO" if not pago_registrado.empty else "⏳ PENDIENTE"
    
    st.markdown("---")
    st.subheader(f"🏢 {edificio['nombre']}")
    st.caption(f"RIF: {edificio['rif']} | Estatus: {estado_pago}")
    st.info(f"**Propietario:** {apto_info['propietario']} | **Apto:** {apto_sel} | **Alícuota:** {alicuota_pct*100:.2f}%")
    
    st.write("#### Detalle de Gastos Comunes del Edificio")
    if not gastos_comunes.empty:
        st.dataframe(gastos_comunes[['descripcion', 'monto']], use_container_width=True)
    
    if not gastos_no_comunes.empty:
        st.write("#### Gastos Individuales")
        st.dataframe(gastos_no_comunes[['descripcion', 'monto']], use_container_width=True)

    st.markdown(f"### TOTAL A CANCELAR: ${monto_total:.2f}")
    
    col_pdf, col_wa = st.columns(2)
    with col_pdf:
        st.write("### 🖨️ PDF / Recibo Impreso")
        logo_html = f'<img src="{edificio["logo_url"]}" style="max-height: 50px; float: right;">' if edificio.get('logo_url') else ''
        html_recibo = f"""
        <html><body>
            <h2>{edificio['nombre']}</h2>
            <p><b>Propietario:</b> {apto_info['propietario']} | <b>Apto:</b> {apto_sel}</p>
            <p><b>Cuota Alícuota:</b> ${cuota_comun:.2f} | <b>Gastos Indiv.:</b> ${total_no_comun:.2f}</p>
            <h3>TOTAL: ${monto_total:.2f}</h3>
            <button onclick="window.print()">🖨️ Imprimir / Guardar PDF</button>
        </body></html>
        """
        components.html(html_recibo, height=220)
        
    with col_wa:
        if st.session_state['rol'] == "Admin":
            st.write("### 📲 Envío Directo WhatsApp")
            msg_wa = f"🏢 *{edificio['nombre']}*\nRECIBO {periodo}\nPropietario: {apto_info['propietario']}\nApto: {apto_sel}\nTOTAL: ${monto_total:.2f}"
            phone_clean = str(apto_info['telefono']).replace("+", "").replace(" ", "").replace("-", "")
            wa_url = f"https://wa.me/{phone_clean}?text={urllib.parse.quote(msg_wa)}"
            st.markdown(f"[📲 Enviar Recibo a WhatsApp]({wa_url})")

# --- MÓDULO 5: PAGOS ---
elif opcion == "5. Registrar Pago de Apartamento":
    st.header("💳 Registrar Pago Recibido")
    aptos_df = get_apartamentos()
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período a pagar:", "2026-05")
        apto_sel = st.selectbox("Apartamento:", aptos_df['numero'].tolist())
        fecha = st.date_input("Fecha:")
    with col2:
        monto = st.number_input("Monto ($):", min_value=0.0)
        referencia = st.text_input("Comprobante / Ref:")
        metodo = st.selectbox("Método:", ["Pago Móvil", "Transferencia", "Zelle", "Efectivo"])
        
    if st.button("💾 Registrar Pago"):
        apto_id = int(aptos_df[aptos_df['numero'] == apto_sel].iloc[0]['id'])
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO pagos_propietarios 
                (fecha, periodo, apartamento_id, apartamento, monto, referencia, metodo, estado) 
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(fecha), periodo, apto_id, apto_sel, monto, referencia, metodo, 'PAGADO'))
            conn.commit()
        st.success(f"Pago registrado para el apto {apto_sel}.")

# --- MÓDULO 6: REPORTES ---
elif opcion == "6. Reportes (Morosidad y Proveedores)":
    st.header("📊 Reporte de Morosidad")
    periodo = st.text_input("Período (Año-Mes):", "2026-05")
    aptos_df = get_apartamentos()
    
    if not aptos_df.empty:
        with get_connection() as conn:
            res_gastos = pd.read_sql("SELECT SUM(monto) as total FROM gastos WHERE periodo = ? AND es_comun = 1", conn, params=(periodo,))
            gastos_comunes = float(res_gastos.iloc[0]['total']) if not res_gastos.empty and res_gastos.iloc[0]['total'] is not None else 0.0
            pagos_df = pd.read_sql("SELECT apartamento, SUM(monto) as pagado FROM pagos_propietarios WHERE periodo = ? GROUP BY apartamento", conn, params=(periodo,))
            
            reporte = []
            for _, row in aptos_df.iterrows():
                a_num = row['numero']
                alicuota = float(row['alicuota'])
                cuota = gastos_comunes * alicuota
                res_nocom = pd.read_sql("SELECT SUM(monto) as total FROM gastos WHERE periodo = ? AND es_comun = 0 AND apto_no_comun = ?", conn, params=(periodo, a_num))
                no_com = float(res_nocom.iloc[0]['total']) if not res_nocom.empty and res_nocom.iloc[0]['total'] is not None else 0.0
                deben = cuota + no_com
                pagado_row = pagos_df[pagos_df['apartamento'] == a_num] if not pagos_df.empty else pd.DataFrame()
                pagado = float(pagado_row.iloc[0]['pagado']) if not pagado_row.empty else 0.0
                saldo = deben - pagado
                estatus = "✅ PAGADO" if saldo <= 0.01 else "❌ MOROSO"
                
                reporte.append({
                    "Apto": a_num,
                    "Propietario": row['propietario'],
                    "Alícuota": f"{alicuota*100:.2f}%",
                    "Facturado ($)": round(deben, 2),
                    "Pagado ($)": round(pagado, 2),
                    "Saldo Pendiente ($)": round(saldo, 2),
                    "Estatus": estatus
                })
            
        st.dataframe(pd.DataFrame(reporte), use_container_width=True)
