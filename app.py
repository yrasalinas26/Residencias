import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
import streamlit.components.v1 as components

st.set_page_config(page_title="Gestión de Condominio", page_icon="🏢", layout="wide")

DB_NAME = 'condominio.db'

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

# --- INICIALIZACIÓN Y MIGRACIÓN AUTOMÁTICA DE BASE DE DATOS ---
def inicializar_bd():
    with get_connection() as conn:
        cursor = conn.cursor()
        
        cursor.executescript("""
        CREATE TABLE IF NOT EXISTS edificio (
            id INTEGER PRIMARY KEY,
            nombre TEXT,
            rif TEXT,
            direccion TEXT
        );

        CREATE TABLE IF NOT EXISTS apartamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero TEXT UNIQUE,
            propietario TEXT,
            telefono TEXT,
            alicuota REAL
        );

        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo TEXT,
            descripcion TEXT,
            monto REAL,
            es_comun INTEGER,
            apto_no_comun TEXT
        );

        CREATE TABLE IF NOT EXISTS pagos_propietarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            periodo TEXT,
            mes INTEGER,
            anio INTEGER,
            apartamento_id INTEGER,
            apartamento TEXT,
            monto REAL,
            referencia TEXT,
            metodo TEXT,
            estado TEXT
        );

        CREATE TABLE IF NOT EXISTS pagos_proveedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            proveedor TEXT,
            rif_proveedor TEXT,
            concepto TEXT,
            monto REAL,
            num_factura TEXT
        );
        """)

        cursor.execute("PRAGMA table_info(gastos)")
        columnas = [col[1] for col in cursor.fetchall()]
        if 'apto_no_comun' not in columnas:
            cursor.execute("ALTER TABLE gastos ADD COLUMN apto_no_comun TEXT")

        cursor.execute("SELECT COUNT(*) FROM edificio")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO edificio VALUES (1, 'RESIDENCIAS EL PARQUE', 'J-12345678-9', 'Av. Principal, Calle 4')")

        cursor.execute("SELECT COUNT(*) FROM apartamentos")
        if cursor.fetchone()[0] == 0:
            aptos_data = [
                ('1A', 'Carlos Mendoza', '+584141234567', 0.06),
                ('1B', 'María Rodríguez', '+584122345678', 0.06),
                ('2',  'Alejandro Silva', '+584163456789', 0.12),
                ('3A', 'Patricia Gómez',  '+584244567890', 0.06),
                ('3B', 'Roberto Fernández','+584145678901', 0.06),
                ('4A', 'Elena Benítez',   '+584126789012', 0.06),
                ('4B', 'Javier Morales',  '+584167890123', 0.06),
                ('5A', 'Carmen Castillo', '+584248901234', 0.06),
                ('5B', 'Diego Torres',    '+584149012345', 0.06),
                ('6A', 'Sofía Vargas',    '+584120123456', 0.06),
                ('6B', 'Gabriel Ruiz',    '+584161234567', 0.06),
                ('7',  'Ricardo Alarcón', '+584242345678', 0.12),
                ('PH', 'Fernando Delgado','+584143456789', 0.16)
            ]
            cursor.executemany("INSERT INTO apartamentos (numero, propietario, telefono, alicuota) VALUES (?, ?, ?, ?)", aptos_data)

inicializar_bd()

def get_edificio():
    with get_connection() as conn:
        df = pd.read_sql("SELECT * FROM edificio WHERE id=1", conn)
    return df.iloc[0] if not df.empty else {"nombre": "Condominio", "rif": "J-00000000-0", "direccion": "N/A"}

def get_apartamentos():
    with get_connection() as conn:
        return pd.read_sql("SELECT * FROM apartamentos ORDER BY id", conn)

# --- SISTEMA DE AUTENTICACIÓN (LOGIN) ---
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
            st.error("❌ Clave incorrecta para el perfil seleccionado.")
    st.stop()

# --- MENÚ SEGÚN ROL ---
st.sidebar.title("🏢 Menú Condominio")
st.sidebar.write(f"**Usuario:** {st.session_state['rol']}")

if st.sidebar.button("🚪 Cerrar Sesión"):
    st.session_state['autenticado'] = False
    st.session_state['rol'] = None
    st.rerun()

if st.session_state['rol'] == "Admin":
    opcion = st.sidebar.radio("Navegación:", [
        "1. Registrar Gastos del Mes",
        "2. Generar Recibo & WhatsApp / PDF",
        "3. Registrar Pago de Apartamento",
        "4. Reporte de Morosidad",
        "5. Reporte de Proveedores"
    ])
else:
    opcion = st.sidebar.radio("Navegación:", [
        "2. Generar Recibo & WhatsApp / PDF",
        "4. Reporte de Morosidad"
    ])

edificio = get_edificio()

# --- MÓDULO 1: GASTOS ---
if opcion == "1. Registrar Gastos del Mes":
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
            aptos = get_apartamentos()['numero'].tolist()
            apto_destino = st.selectbox("Apartamento Responsable:", aptos)
            
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

    st.subheader(f"Gastos Registrados en {periodo}")
    with get_connection() as conn:
        df_gastos = pd.read_sql("SELECT * FROM gastos WHERE periodo = ?", conn, params=(periodo,))
    st.dataframe(df_gastos, use_container_width=True)

# --- MÓDULO 2: RECIBOS & WHATSAPP / IMPRESIÓN PDF ---
elif opcion == "2. Generar Recibo & WhatsApp / PDF":
    st.header("📄 Generador de Recibos de Condominio")
    
    col_p, col_a = st.columns(2)
    with col_p:
        periodo = st.text_input("Período a consultar (Año-Mes):", "2026-05")
    with col_a:
        aptos_df = get_apartamentos()
        apto_sel = st.selectbox("Seleccionar Apartamento:", aptos_df['numero'].tolist())
        
    if not aptos_df.empty:
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

        st.info(f"**Propietario:** {apto_info['propietario']}  |  **Apto:** {apto_sel}  |  **Alícuota:** {alicuota_pct*100:.2f}%  |  **Teléfono:** {apto_info['telefono']}")
        
        st.write("#### 1. Gastos Comunes del Edificio")
        if not gastos_comunes.empty:
            st.dataframe(gastos_comunes[['descripcion', 'monto']].rename(columns={'descripcion': 'Descripción', 'monto': 'Monto ($)'}), use_container_width=True)
        else:
            st.caption("No existen gastos comunes registrados para este período.")
        
        if not gastos_no_comunes.empty:
            st.write("#### 2. Gastos Individuales / No Comunes")
            st.dataframe(gastos_no_comunes[['descripcion', 'monto']].rename(columns={'descripcion': 'Descripción', 'monto': 'Monto ($)'}), use_container_width=True)

        st.markdown(f"""
            <div style="background-color: #f0fdf4; border: 2px solid #16a34a; padding: 15px; border-radius: 10px; text-align: center; margin: 15px 0;">
                <h4 style="color: #15803d; margin: 0;">TOTAL A CANCELAR — APTO {apto_sel}</h4>
                <h1 style="color: #166534; margin: 5px 0;">${monto_total:.2f}</h1>
                <p style="color: #4b5563; font-size: 13px; margin: 0;">(Cuota Común: ${cuota_comun:.2f} + Gastos No Comunes: ${total_no_comun:.2f})</p>
            </div>
        """, unsafe_allow_html=True)
        
        col_pdf, col_wa = st.columns(2)
        
        with col_pdf:
            st.write("### 🖨️ Formato de Impresión / PDF")
            html_recibo = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <style>
                    body {{ font-family: 'Helvetica', 'Arial', sans-serif; padding: 10px; color: #333; }}
                    .header {{ border-bottom: 2px solid #2563eb; padding-bottom: 8px; margin-bottom: 12px; }}
                    .card {{ background: #f8fafc; border: 1px solid #e2e8f0; padding: 10px; border-radius: 6px; margin-bottom: 12px; }}
                    .total-box {{ background-color: #eff6ff; border: 2px dashed #2563eb; padding: 12px; text-align: center; border-radius: 8px; }}
                    @media print {{
                        .no-print {{ display: none; }}
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h2 style="margin:0; color:#1e40af;">{edificio['nombre']}</h2>
                    <small>RIF: {edificio['rif']} | Período: {periodo}</small>
                </div>
                <div class="card">
                    <b>Propietario:</b> {apto_info['propietario']}<br>
                    <b>Apartamento:</b> {apto_sel} | <b>Alícuota:</b> {alicuota_pct*100:.2f}%
                </div>
                <p><b>Total Gastos Comunes:</b> ${total_comun:.2f}</p>
                <p><b>Cuota según Alícuota:</b> ${cuota_comun:.2f}</p>
                <p><b>Gastos No Comunes:</b> ${total_no_comun:.2f}</p>
                <div class="total-box">
                    <h3 style="color: #1e40af; margin: 0;">TOTAL A CANCELAR: ${monto_total:.2f}</h3>
                </div>
                <br>
                <button class="no-print" onclick="window.print()" style="padding: 8px 16px; background-color: #2563eb; color: white; border: none; border-radius: 4px; cursor: pointer; font-weight: bold;">🖨️ Imprimir / Guardar PDF</button>
            </body>
            </html>
            """
            components.html(html_recibo, height=360)
            
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
                     f"🔧 *Gastos No Comunes:* ${total_no_comun:.2f}\n" \
                     f"----------------------------------------\n" \
                     f"💵 *TOTAL A CANCELAR: ${monto_total:.2f}*\n" \
                     f"----------------------------------------\n" \
                     f"📌 *Estatus:* {estado_pago}\n" \
                     f"💳 Favor enviar el comprobante de pago por este medio."

            phone_clean = str(apto_info['telefono']).replace("+", "").replace(" ", "").replace("-", "")
            encoded_msg = urllib.parse.quote(msg_wa)
            wa_url = f"https://wa.me/{phone_clean}?text={encoded_msg}"
            
            st.info("Presiona el botón para abrir WhatsApp con la plantilla prellenada:")
            st.markdown(f"""
                <a href="{wa_url}" target="_blank" style="text-decoration: none;">
                    <div style="background-color: #25D366; color: white; padding: 12px; border-radius: 8px; text-align: center; font-weight: bold;">
                        📲 Enviar Recibo vía WhatsApp
                    </div>
                </a>
            """, unsafe_allow_html=True)

# --- MÓDULO 3: REGISTRO DE PAGOS ---
elif opcion == "3. Registrar Pago de Apartamento":
    st.header("💳 Registrar Pago Recibido")
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período a pagar (Año-Mes):", "2026-05")
        aptos_df = get_apartamentos()
        apto_sel = st.selectbox("Apartamento:", aptos_df['numero'].tolist())
        fecha = st.date_input("Fecha del Pago")
    with col2:
        monto = st.number_input("Monto Recibido ($):", min_value=0.0)
        referencia = st.text_input("Número de Referencia:")
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
        st.success("Pago registrado con éxito.")

# --- MÓDULO 4: REPORTE DE MOROSIDAD ---
elif opcion == "4. Reporte de Morosidad":
    st.header("📊 Reporte de Morosidad")
    periodo = st.text_input("Filtrar por Período (Año-Mes):", "2026-05")
    
    aptos_df = get_apartamentos()
    
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
                "Alícuota": f"{alicuota*100:.1f}%",
                "Monto Facturado": round(deben, 2),
                "Monto Pagado": round(pagado, 2),
                "Saldo Pendiente": round(saldo, 2),
                "Estatus": estatus
            })
        
    st.dataframe(pd.DataFrame(reporte), use_container_width=True)

# --- MÓDULO 5: PROVEEDORES ---
elif opcion == "5. Reporte de Proveedores":
    st.header("💸 Reporte de Pagos a Proveedores por Período")
    col1, col2 = st.columns(2)
    with col1:
        f_inicio = st.date_input("Fecha Desde:", pd.to_datetime("2026-05-01"))
    with col2:
        f_fin = st.date_input("Fecha Hasta:", pd.to_datetime("2026-05-31"))
        
    with get_connection() as conn:
        prov_df = pd.read_sql("SELECT fecha, proveedor, rif_proveedor, concepto, monto, num_factura FROM pagos_proveedores WHERE fecha BETWEEN ? AND ?", conn, params=(str(f_inicio), str(f_fin)))
        
    st.dataframe(prov_df, use_container_width=True)
    monto_prov = float(prov_df['monto'].sum()) if not prov_df.empty else 0.0
    st.metric("Total Pagado a Proveedores", f"${monto_prov:.2f}")
