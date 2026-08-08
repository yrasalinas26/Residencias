import streamlit as st
import sqlite3
import pandas as pd
import urllib.parse
import streamlit.components.v1 as components

st.set_page_config(page_title="Gestión de Condominio", page_icon="🏢", layout="wide")

DB_NAME = 'condominio.db'

# --- INICIALIZACIÓN AUTOMÁTICA DE BASE DE DATOS ---
def inicializar_bd():
    conn = sqlite3.connect(DB_NAME)
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

    conn.commit()
    conn.close()

inicializar_bd()

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

conn = get_connection()

def get_edificio():
    df = pd.read_sql("SELECT * FROM edificio WHERE id=1", conn)
    return df.iloc[0] if not df.empty else {"nombre": "Condominio", "rif": "J-00000000-0", "direccion": "N/A"}

def get_apartamentos():
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
            cursor = conn.cursor()
            cursor.execute("INSERT INTO gastos (periodo, descripcion, monto, es_comun, apto_no_comun) VALUES (?,?,?,?,?)",
                           (periodo, descripcion, monto, es_comun, apto_destino))
            conn.commit()
            st.success("Gasto registrado con éxito.")
        else:
            st.warning("Escriba una descripción para el gasto.")

    st.subheader(f"Gastos Registrados en {periodo}")
    st.dataframe(pd.read_sql("SELECT * FROM gastos WHERE periodo = ?", conn, params=(periodo,)), use_container_width=True)

# --- MÓDULO 2: RECIBOS & WHATSAPP / IMPRESIÓN PDF ---
elif opcion == "2. Generar Recibo & WhatsApp / PDF":
    st.header("📄 Generador de Recibos de Condominio")
    
    col1, col2 = st.columns(2)
    with col1:
        periodo = st.text_input("Período a consultar (Año-Mes):", "2026-05")
    with col2:
        aptos_df = get_apartamentos()
        apto_sel = st.selectbox("Seleccionar Apartamento:", aptos_df['numero'].tolist())
        
    if not aptos_df.empty:
        apto_info = aptos_df[aptos_df['numero'] == apto_sel].iloc[0]
        
        gastos_comunes = pd.read_sql("SELECT * FROM gastos WHERE periodo = ? AND es_comun = 1", conn, params=(periodo,))
        gastos_no_comunes = pd.read_sql("SELECT * FROM gastos WHERE periodo = ? AND es_comun = 0 AND apto_no_comun = ?", conn, params=(periodo, apto_sel))
        
        total_comun = gastos_comunes['monto'].sum() if not gastos_comunes.empty else 0.0
        cuota_comun = total_comun * apto_info['alicuota']
        total_no_comun = gastos_no_comunes['monto'].sum() if not gastos_no_comunes.empty else 0.0
        
        monto_total = cuota_comun + total_no_comun

        pago_registrado = pd.read_sql("SELECT * FROM pagos_propietarios WHERE apartamento = ? AND periodo = ?", conn, params=(apto_sel, periodo))
        estado_pago = "PAGADO" if not pago_registrado.empty else "PENDIENTE"
        
        st.markdown("---")
        st.subheader(f"🏢 {edificio['nombre']} — RIF: {edificio['rif']}")
        st.write(f"**Propietario:** {apto_info['propietario']} | **Apartamento:** {apto_sel} | **Alícuota:** {apto_info['alicuota']*100:.1f}%")
        st.write(f"**Teléfono:** {apto_info['telefono']} | **Estatus:** `{estado_pago}`")
        
        st.write("### Gastos Comunes del Edificio")
        if not gastos_comunes.empty:
            st.dataframe(gastos_comunes[['descripcion', 'monto']], use_container_width=True)
        else:
            st.info("No hay gastos comunes registrados para este período.")
        
        if not gastos_no_comunes.empty:
            st.write("### Gastos No Comunes")
            st.dataframe(gastos_no_comunes[['descripcion', 'monto']], use_container_width=True)
            
        # Recuadro resaltado del monto a pagar
        st.markdown(f'''
            <div style="background-color: #eff6ff; border: 2px dashed #2563eb; padding: 18px; border-radius: 8px; text-align: center; margin: 15px 0;">
                <h4 style="color: #1e40af; margin: 0;">MONTO TOTAL A CANCELAR ({apto_sel})</h4>
                <h1 style="color: #1d4ed8; margin: 5px 0;">${monto_total:.2f}</h1>
            </div>
        ''', unsafe_allow_html=True)
        
        col_pdf, col_wa = st.columns(2)
        
        with col_pdf:
            html_recibo = f"""
            <html>
            <head>
                <style>
                    body {{ font-family: Arial, sans-serif; padding: 15px; }}
                    .box {{ background-color: #eff6ff; border: 2px dashed #2563eb; padding: 15px; text-align: center; border-radius: 8px; margin-top: 15px; }}
                </style>
            </head>
            <body>
                <h2>{edificio['nombre']} - RIF: {edificio['rif']}</h2>
                <p><b>Propietario:</b> {apto_info['propietario']} | <b>Apartamento:</b> {apto_sel} | <b>Alícuota:</b> {apto_info['alicuota']*100:.1f}%</p>
                <p><b>Período:</b> {periodo}</p>
                <p><b>Cuota de Gastos Comunes:</b> ${cuota_comun:.2f}</p>
                <p><b>Gastos No Comunes:</b> ${total_no_comun:.2f}</p>
                <div class="box">
                    <h3 style="color: #1e40af; margin: 0;">TOTAL A CANCELAR: ${monto_total:.2f}</h3>
                </div>
                <br>
                <button onclick="window.print()" style="padding: 10px 20px; background-color: #2563eb; color: white; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">🖨️ Imprimir / Guardar en PDF</button>
            </body>
            </html>
            """
            components.html(html_recibo, height=350)
            
        with col_wa:
            msg_wa = f'''🏢 *{edificio["nombre"]}*
📄 *RIF:* {edificio["rif"]}
🗓 *Recibo de Condominio - {periodo}*
----------------------------------------
👤 *Propietario:* {apto_info["propietario"]}
🏠 *Apartamento:* {apto_sel} | 📊 *Alícuota:* {apto_info["alicuota"]*100:.1f}%
📞 *Teléfono:* {apto_info["telefono"]}
----------------------------------------
🔹 *Gastos Comunes Total:* ${total_comun:.2f}
🔹 *Tu Cuota por Alícuota:* ${cuota_comun:.2f}
🔧 *Gastos No Comunes:* ${total_no_comun:.2f}
----------------------------------------
┌──────────────────────────────────────┐
│ 💵 *TOTAL A CANCELAR:* *${monto_total:.2f}*
└──────────────────────────────────────┘
----------------------------------------
💳 Por favor remita su comprobante por este chat.'''

            phone_clean = str(apto_info['telefono']).replace("+", "").replace(" ", "")
            encoded_msg = urllib.parse.quote(msg_wa)
            wa_url = f"https://wa.me/{phone_clean}?text={encoded_msg}"
            st.markdown(f"[📲 Enviar por WhatsApp]({wa_url})", unsafe_allow_html=True)

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
    
    # Consulta segura de total de gastos comunes
    res_gastos = pd.read_sql("SELECT SUM(monto) as total FROM gastos WHERE periodo = ? AND es_comun = 1", conn, params=(periodo,))
    gastos_comunes = res_gastos.iloc[0]['total'] if not res_gastos.empty and res_gastos.iloc[0]['total'] is not None else 0.0
    
    # Consulta segura de pagos realizados
    pagos_df = pd.read_sql("SELECT apartamento, SUM(monto) as pagado FROM pagos_propietarios WHERE periodo = ? GROUP BY apartamento", conn, params=(periodo,))
    
    reporte = []
    for _, row in aptos_df.iterrows():
        a_num = row['numero']
        alicuota = row['alicuota']
        cuota = gastos_comunes * alicuota
        
        res_nocom = pd.read_sql("SELECT SUM(monto) as total FROM gastos WHERE periodo = ? AND es_comun = 0 AND apto_no_comun = ?", conn, params=(periodo, a_num))
        no_com = res_nocom.iloc[0]['total'] if not res_nocom.empty and res_nocom.iloc[0]['total'] is not None else 0.0
        
        deben = cuota + no_com
        
        pagado_row = pagos_df[pagos_df['apartamento'] == a_num] if not pagos_df.empty else pd.DataFrame()
        pagado = pagado_row.iloc[0]['pagado'] if not pagado_row.empty else 0.0
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
        
    prov_df = pd.read_sql("SELECT fecha, proveedor, rif_proveedor, concepto, monto, num_factura FROM pagos_proveedores WHERE fecha BETWEEN ? AND ?", conn, params=(str(f_inicio), str(f_fin)))
    st.dataframe(prov_df, use_container_width=True)
    monto_prov = prov_df['monto'].sum() if not prov_df.empty else 0.0
    st.metric("Total Pagado a Proveedores", f"${monto_prov:.2f}")
