import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
import streamlit.components.v1 as components

st.set_page_config(page_title="Gestión de Condominio", page_icon="🏢", layout="wide")
# Inyectar icono personalizado para cuando se agregue a la pantalla de inicio del teléfono
st.html("""
    <!-- Icono para iPhone / Safari -->
    <link rel="apple-touch-icon" href="https://cdn-icons-png.flaticon.com/512/2558/2558042.png">
    <!-- Icono para Android / Chrome -->
    <link rel="icon" type="image/png" sizes="192x192" href="https://cdn-icons-png.flaticon.com/512/2558/2558042.png">
""")

DB_NAME = 'condominio_v3.db'

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- INICIALIZACIÓN Y MIGRACIÓN AUTOMÁTICA DE LA BASE DE DATOS ---
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
        
        cursor.execute("PRAGMA table_info(edificio)")
        cols_edificio = [col[1] for col in cursor.fetchall()]
        if 'logo_url' not in cols_edificio:
            cursor.execute("ALTER TABLE edificio ADD COLUMN logo_url TEXT")

        cursor.execute("SELECT COUNT(*) FROM edificio")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO edificio (id, nombre, rif, direccion, logo_url) VALUES (1, 'RESIDENCIAS EL PARQUE', 'J-12345678-9', 'Av. Principal, Calle 4', '')")

        # 2. Tabla Apartamentos
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS apartamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT,
            propietario TEXT,
            telefono TEXT,
            alicuota REAL
        )""")

        # 3. Tabla Proveedores
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
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

# --- FUNCIONES DE ACCESO A DATOS ---
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

# --- LOGIN ---
if 'autenticado' not in st.session_state:
    st.session_state['autenticado'] = False
    st.session_state['rol'] = None

if not st.session_state['autenticado']:
    st.title("🔐 Acceso al Sistema de Condominio")
    tipo_usuario = st.radio("Seleccione el tipo de usuario:", ["Administrador", "Vecino / Propietario"])
    clave = st.text_input("Ingrese la clave de acceso:", type="password")
    if st.button("Iniciar Sesión"):
        if tipo_usuario == "Administrador" and clave == "admin123":
            st.session_state['autenticado'] = True
            st.session_state['rol'] = "Admin"
            st.rerun()
        elif tipo_usuario == "Vecino / Propietario" and clave == "vecino123":
            st.session_state['autenticado'] = True
            st.session_state['rol'] = "Vecino"
            st.rerun()
        else:
            st.error("❌ Clave incorrecta.")
    st.stop()

# --- NAVEGACIÓN ---
st.sidebar.title("🏢 Menú Condominio")
st.sidebar.write(f"**Usuario:** {st.session_state['rol']}")

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state['autenticado'] = False
    st.session_state['rol'] = None
    st.rerun()

if st.session_state['rol'] == "Admin":
    opcion = st.sidebar.radio("Navegación:", [
        "0. Datos del Edificio (Logo / RIF)",
        "1. Registro de Propietarios & Alícuotas",
        "2. Registro de Proveedores",
        "3. Registrar Gastos del Mes",
        "4. Generar Recibo & WhatsApp / PDF",
        "5. Registrar Pago de Apartamento",
        "6. Reportes (Morosidad y Proveedores)"
    ])
else:
    opcion = st.sidebar.radio("Navegación:", [
        "4. Generar Recibo & WhatsApp / PDF",
        "6. Reportes (Morosidad y Proveedores)"
    ])

edificio = get_edificio()

# --- MÓDULO 0: DATOS DEL EDIFICIO ---
if opcion == "0. Datos del Edificio (Logo / RIF)":
    st.header("⚙️ Configuración del Condominio")
    
    with st.form("form_edificio"):
        nombre_e = st.text_input("Nombre del Condominio / Edificio:", value=edificio['nombre'])
        rif_e = st.text_input("RIF:", value=edificio['rif'])
        dir_e = st.text_area("Dirección:", value=edificio['direccion'])
        logo_e = st.text_input("URL del Logo (Opcional, ej: https://i.imgur.com/logo.png):", value=edificio.get('logo_url', ''))
        
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
            st.success("¡Datos del edificio actualizados correctamente!")
            st.rerun()

# --- MÓDULO 1: PROPIETARIOS ---
elif opcion == "1. Registro de Propietarios & Alícuotas":
    st.header("🏠 Gestión de Apartamentos y Propietarios")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Registrar / Editar Apto")
        numero_apto = st.text_input("Número de Apto (ej: 1A, PH):").strip().upper()
        propietario = st.text_input("Nombre del Propietario:")
        telefono = st.text_input("Teléfono WhatsApp (ej: +584121234567):")
        alicuota_pct = st.number_input("Alícuota (%):", min_value=0.0, max_value=100.0, value=5.0, step=0.1)
        
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
                            SET propietario = ?, telefono = ?, alicuota = ?
                            WHERE numero = ?
                        """, (propietario, telefono, alicuota_real, numero_apto))
                    else:
                        cursor.execute("""
                            INSERT INTO apartamentos (numero, propietario, telefono, alicuota)
                            VALUES (?, ?, ?, ?)
                        """, (numero_apto, propietario, telefono, alicuota_real))
                    conn.commit()
                st.success(f"Apartamento {numero_apto} guardado exitosamente.")
                st.rerun()
            else:
                st.warning("Ingrese el número de apartamento y el nombre del propietario.")

    with col2:
        st.subheader("Listado de Apartamentos")
        df_aptos = get_apartamentos()
        if not df_aptos.empty:
            df_display = df_aptos.copy()
            df_display['alicuota'] = df_display['alicuota'].apply(lambda x: f"{x*100:.2f}%")
            st.dataframe(df_display[['numero', 'propietario', 'telefono', 'alicuota']], use_container_width=True)
            
            total_alicuota = df_aptos['alicuota'].sum() * 100
            st.metric("Suma Total de Alícuotas", f"{total_alicuota:.2f}%")
            if abs(total_alicuota - 100.0) > 0.01:
                st.warning("⚠️ Nota: La suma total de las alícuotas debería ser igual a 100.00%.")
        else:
            st.info("Aún no hay apartamentos registrados.")

# --- MÓDULO 2: PROVEEDORES ---
elif opcion == "2. Registro de Proveedores":
    st.header("🚚 Gestión de Proveedores y Pagos")
    
    tab1, tab2 = st.tabs(["Directorio de Proveedores", "Registrar Pago a Proveedor"])
    
    with tab1:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("Agregar Proveedor")
            nombre_prov = st.text_input("Nombre / Razón Social:")
            rif_prov = st.text_input("RIF / Identificación:")
            tel_prov = st.text_input("Teléfono de Contacto:")
            servicio_prov = st.text_input("Servicio / Rubro (ej: Mantenimiento, Ascensores):")
            
            if st.button("💾 Guardar Proveedor"):
                if nombre_prov.strip() != "":
                    with get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO proveedores (nombre, rif, telefono, servicio) 
                            VALUES (?, ?, ?, ?)
                        """, (nombre_prov, rif_prov, tel_prov, servicio_prov))
                        conn.commit()
                    st.success("Proveedor guardado correctamente.")
                    st.rerun()
                else:
                    st.warning("Ingrese el nombre del proveedor.")
        
        with c2:
            st.subheader("Proveedores Registrados")
            df_prov = get_proveedores()
            if not df_prov.empty:
                st.dataframe(df_prov[['nombre', 'rif', 'telefono', 'servicio']], use_container_width=True)
            else:
                st.info("No hay proveedores registrados.")

    with tab2:
        st.subheader("Registrar Egreso / Pago a Proveedor")
        df_p = get_proveedores()
        if not df_p.empty:
            col_a, col_b = st.columns(2)
            with col_a:
                prov_sel = st.selectbox("Seleccionar Proveedor:", df_p['nombre'].tolist())
                fecha_pago = st.date_input("Fecha del Pago:")
                monto_pago = st.number_input("Monto Pagado ($):", min_value=0.0, step=10.0)
            with col_b:
                num_fact = st.text_input("Número de Factura / Control:")
                concepto_pago = st.text_input("Concepto del Pago:")
                
            if st.button("💾 Registrar Pago a Proveedor"):
                prov_data = df_p[df_p['nombre'] == prov_sel].iloc[0]
                with get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO pagos_proveedores (fecha, proveedor, rif_proveedor, concepto, monto, num_factura)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (str(fecha_pago), prov_sel, prov_data['rif'], concepto_pago, monto_pago, num_fact))
                    conn.commit()
                st.success("Pago a proveedor registrado exitosamente.")
        else:
            st.info("Primero debe registrar al menos un proveedor en la pestaña previa.")

# --- MÓDULO 3: REGISTRAR GASTOS ---
elif opcion == "3. Registrar Gastos del Mes":
    st.header("📝 Cargar Gastos Comunes y No Comunes")
    
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período (Año-Mes):", "2026-05")
        descripcion = st.text_input("Descripción del Gasto:")
        monto = st.number_input("Monto ($):", min_value=0.0, step=10.0)
    with col2:
        tipo_gasto = st.selectbox("Tipo de Gasto:", ["Común (Aplica a todos por alícuota)", "No Común (Aplica a un solo Apto)"])
        apto_destino = None
        if "No Común" in tipo_gasto:
            aptos = get_apartamentos()
            if not aptos.empty:
                apto_destino = st.selectbox("Apartamento Responsable:", aptos['numero'].tolist())
            else:
                st.warning("Registre apartamentos primero en el Módulo 1.")
            
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
        else:
            st.warning("Escriba una descripción para el gasto.")

    st.subheader(f"Gastos Registrados en Período: {periodo}")
    with get_connection() as conn:
        df_gastos = pd.read_sql("SELECT id, descripcion, monto, es_comun, apto_no_comun FROM gastos WHERE periodo = ?", conn, params=(periodo,))
    if not df_gastos.empty:
        df_gastos['Tipo'] = df_gastos['es_comun'].apply(lambda x: 'Común' if x == 1 else 'No Común')
        st.dataframe(df_gastos[['descripcion', 'monto', 'Tipo', 'apto_no_comun']], use_container_width=True)
    else:
        st.caption("No existen gastos para este período.")

# --- MÓDULO 4: RECIBOS (PDF & WHATSAPP) ---
elif opcion == "4. Generar Recibo & WhatsApp / PDF":
    st.header("📄 Generador de Recibos de Condominio")
    
    aptos_df = get_apartamentos()
    if aptos_df.empty:
        st.warning("⚠️ No hay apartamentos registrados. Vaya al Módulo 1 para agregarlos.")
        st.stop()
        
    col_p, col_a = st.columns(2)
    with col_p:
        periodo = st.text_input("Período a consultar (Año-Mes):", "2026-05")
    with col_a:
        apto_sel = st.selectbox("Seleccionar Apartamento:", aptos_df['numero'].tolist())
        
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
    c1, c2 = st.columns([3, 1])
    with c1:
        st.subheader(f"🏢 {edificio['nombre']}")
        st.caption(f"RIF: {edificio['rif']} | Dirección: {edificio['direccion']}")
    with c2:
        st.metric("Estatus del Pago", estado_pago)

    st.info(f"**Propietario:** {apto_info['propietario']} | **Apto:** {apto_sel} | **Alícuota:** {alicuota_pct*100:.2f}% | **Teléfono:** {apto_info['telefono']}")
    
    st.write("#### Detalle de Gastos Comunes del Edificio")
    if not gastos_comunes.empty:
        st.dataframe(gastos_comunes[['descripcion', 'monto']].rename(columns={'descripcion': 'Descripción', 'monto': 'Monto ($)'}), use_container_width=True)
    else:
        st.caption("No hay gastos comunes cargados para este período.")
    
    if not gastos_no_comunes.empty:
        st.write("#### Gastos Individuales / No Comunes")
        st.dataframe(gastos_no_comunes[['descripcion', 'monto']].rename(columns={'descripcion': 'Descripción', 'monto': 'Monto ($)'}), use_container_width=True)

    st.markdown(f"### TOTAL A CANCELAR: ${monto_total:.2f}")
    
    col_pdf, col_wa = st.columns(2)
    with col_pdf:
        st.write("### 🖨️ Formato de Impresión / PDF")
        
        logo_html = f'<img src="{edificio["logo_url"]}" style="max-height: 50px; float: right;">' if edificio.get('logo_url') else ''
        
        html_recibo = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 15px; color: #333; }}
                .header {{ border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-bottom: 12px; }}
                .card {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 6px; margin-bottom: 12px; }}
                .total-box {{ background-color: #eff6ff; border: 2px dashed #2563eb; padding: 12px; text-align: center; border-radius: 8px; }}
                @media print {{ .no-print {{ display: none; }} }}
            </style>
        </head>
        <body>
            <div class="header">
                {logo_html}
                <h2 style="margin:0; color:#1e40af;">{edificio['nombre']}</h2>
                <small>RIF: {edificio['rif']} | Período: {periodo}</small>
            </div>
            <div class="card">
                <b>Propietario:</b> {apto_info['propietario']}<br>
                <b>Apartamento:</b> {apto_sel} | <b>Alícuota:</b> {alicuota_pct*100:.2f}%
            </div>
            <p><b>Gastos Comunes Totales:</b> ${total_comun:.2f}</p>
            <p><b>Cuota según Alícuota:</b> ${cuota_comun:.2f}</p>
            <p><b>Gastos Individuales:</b> ${total_no_comun:.2f}</p>
            <div class="total-box">
                <h3 style="color: #1e40af; margin: 0;">TOTAL A CANCELAR: ${monto_total:.2f}</h3>
            </div>
            <br>
            <button class="no-print" onclick="window.print()" style="padding: 10px 20px; background-color: #2563eb; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">🖨️ Imprimir / Guardar como PDF</button>
        </body>
        </html>
        """
        components.html(html_recibo, height=380)
        
    with col_wa:
        st.write("### 📲 Envío Directo a WhatsApp")
        msg_wa = f"🏢 *{edificio['nombre']}*\n" \
                 f"📄 *RIF:* {edificio['rif']}\n" \
                 f"🗓 *RECIBO DE CONDOMINIO — {periodo}*\n" \
                 f"----------------------------------------\n" \
                 f"👤 *Propietario:* {apto_info['propietario']}\n" \
                 f"🏠 *Apartamento:* {apto_sel}\n" \
                 f"📊 *Alícuota:* {alicuota_pct*100:.2f}%\n" \
                 f"----------------------------------------\n" \
                 f"🔹 *Gastos Comunes Totales:* ${total_comun:.2f}\n" \
                 f"🔹 *Su Cuota ({alicuota_pct*100:.2f}%):* ${cuota_comun:.2f}\n" \
                 f"🔧 *Gastos Individuales:* ${total_no_comun:.2f}\n" \
                 f"----------------------------------------\n" \
                 f"💵 *TOTAL A CANCELAR: ${monto_total:.2f}*\n" \
                 f"----------------------------------------\n" \
                 f"📌 *Estatus:* {estado_pago}\n" \
                 f"💳 Por favor enviar el comprobante de pago por este medio."

        phone_clean = str(apto_info['telefono']).replace("+", "").replace(" ", "").replace("-", "")
        encoded_msg = urllib.parse.quote(msg_wa)
        wa_url = f"https://wa.me/{phone_clean}?text={encoded_msg}"
        
        st.info("Presiona el botón para abrir el chat con la plantilla formateada:")
        st.markdown(f"[📲 Enviar Recibo a WhatsApp de {apto_info['propietario']}]({wa_url})")

# --- MÓDULO 5: PAGOS PROPIETARIOS ---
elif opcion == "5. Registrar Pago de Apartamento":
    st.header("💳 Registrar Pago Recibido de Propietario")
    
    aptos_df = get_apartamentos()
    if aptos_df.empty:
        st.warning("⚠️ Debe registrar apartamentos primero en el Módulo 1.")
        st.stop()
        
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período a pagar (Año-Mes):", "2026-05")
        apto_sel = st.selectbox("Apartamento:", aptos_df['numero'].tolist())
        fecha = st.date_input("Fecha del Pago:")
    with col2:
        monto = st.number_input("Monto Recibido ($):", min_value=0.0)
        referencia = st.text_input("Número de Referencia / Comprobante:")
        metodo = st.selectbox("Método de Pago:", ["Pago Móvil", "Transferencia", "Zelle", "Efectivo"])
        
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
        st.success(f"Pago de ${monto:.2f} registrado para el apto {apto_sel}.")

# --- MÓDULO 6: REPORTES ---
elif opcion == "6. Reportes (Morosidad y Proveedores)":
    st.header("📊 Reportes Financieros")
    
    t1, t2 = st.tabs(["Estado de Cuenta / Morosidad", "Histórico de Pagos a Proveedores"])
    
    with t1:
        st.subheader("Reporte de Morosidad por Período")
        periodo = st.text_input("Período a analizar (Año-Mes):", "2026-05")
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

    with t2:
        st.subheader("Pagos Realizados a Proveedores")
        c_i, c_f = st.columns(2)
        with c_i:
            f_inicio = st.date_input("Desde:", pd.to_datetime("2026-05-01"))
        with c_f:
            f_fin = st.date_input("Hasta:", pd.to_datetime("2026-05-31"))
            
        with get_connection() as conn:
            prov_df = pd.read_sql("SELECT fecha, proveedor, rif_proveedor, concepto, monto, num_factura FROM pagos_proveedores WHERE fecha BETWEEN ? AND ?", conn, params=(str(f_inicio), str(f_fin)))
            
        st.dataframe(prov_df, use_container_width=True)
        monto_prov = float(prov_df['monto'].sum()) if not prov_df.empty else 0.0
        st.metric("Total Egresos Proveedores", f"${monto_prov:.2f}")
