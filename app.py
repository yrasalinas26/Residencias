import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text
from datetime import datetime
import io
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Sistema de Administración de Condominio",
    page_icon="🏢",
    layout="wide"
)

# Estructura por defecto de las 13 unidades
UNIDADES_DEFECTO = [
    ("1A", 6.00), ("1B", 6.00),
    ("2", 12.00),
    ("3A", 6.00), ("3B", 6.00),
    ("4A", 6.00), ("4B", 6.00),
    ("5A", 6.00), ("5B", 6.00),
    ("6A", 6.00), ("6B", 6.00),
    ("7", 12.00),
    ("PH", 16.00)
]

# -----------------------------------------------------------------------------
# CONEXIÓN Y BASE DE DATOS
# -----------------------------------------------------------------------------
@st.cache_resource
def obtener_engine():
    try:
        if "DATABASE_URL" in st.secrets:
            url = st.secrets["DATABASE_URL"]
        else:
            return None, "No se encontró DATABASE_URL en Secrets."

        engine = create_engine(
            url,
            connect_args={"prepare_threshold": None},
            pool_pre_ping=True
        )
        return engine, None
    except Exception as e:
        return None, str(e)

engine, error_conexion = obtener_engine()

def inicializar_tablas():
    if not engine:
        return
    try:
        with engine.connect() as conn:
            # Tabla de Unidades / Alícuotas
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS unidades (
                    unidad VARCHAR(10) PRIMARY KEY,
                    alicuota NUMERIC(5,2) NOT NULL
                );
            """))

            # Poblar unidades por defecto si la tabla está vacía
            res_u = conn.execute(text("SELECT COUNT(*) FROM unidades")).scalar()
            if res_u == 0:
                for u, a in UNIDADES_DEFECTO:
                    conn.execute(text("INSERT INTO unidades (unidad, alicuota) VALUES (:u, :a)"), {"u": u, "a": a})

            # Tabla de Usuarios
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    usuario VARCHAR(20) PRIMARY KEY,
                    clave VARCHAR(100) NOT NULL,
                    rol VARCHAR(20) NOT NULL
                );
            """))

            # Poblar usuarios si no existen
            admin_pwd = st.secrets.get("ADMIN_PASSWORD", "admin123")
            if not conn.execute(text("SELECT usuario FROM usuarios WHERE usuario = 'admin'")).fetchone():
                conn.execute(text("INSERT INTO usuarios (usuario, clave, rol) VALUES ('admin', :p, 'admin')"), {"p": admin_pwd})

            for u, _ in UNIDADES_DEFECTO:
                if not conn.execute(text("SELECT usuario FROM usuarios WHERE usuario = :u"), {"u": u}).fetchone():
                    conn.execute(text("INSERT INTO usuarios (usuario, clave, rol) VALUES (:u, '1234', 'propietario')"), {"u": u})

            # Tabla de Gastos Comunes
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS gastos (
                    id SERIAL PRIMARY KEY,
                    mes_anio VARCHAR(7) NOT NULL,
                    concepto VARCHAR(200) NOT NULL,
                    monto NUMERIC(12,2) NOT NULL,
                    estatus VARCHAR(20) DEFAULT 'Aprobado',
                    fecha DATE DEFAULT CURRENT_DATE
                );
            """))

            # Tabla de Cuotas Extraordinarias
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS cuotas_extraordinarias (
                    id SERIAL PRIMARY KEY,
                    concepto VARCHAR(200) NOT NULL,
                    monto_total NUMERIC(12,2) NOT NULL,
                    fecha_emision DATE DEFAULT CURRENT_DATE,
                    estatus VARCHAR(20) DEFAULT 'Activa'
                );
            """))

            # Tabla de Pagos Reportados
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS pagos_reportados (
                    id SERIAL PRIMARY KEY,
                    apartamento VARCHAR(10) NOT NULL,
                    tipo_pago VARCHAR(30) DEFAULT 'Mensualidad',
                    mes_anio VARCHAR(7),
                    id_cuota_extra INT,
                    monto NUMERIC(12, 2) NOT NULL,
                    metodo_pago VARCHAR(50) NOT NULL,
                    referencia VARCHAR(100) NOT NULL,
                    fecha_pago DATE NOT NULL,
                    comprobante_nombre VARCHAR(255),
                    estatus VARCHAR(20) DEFAULT 'Pendiente',
                    fecha_reporte TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """))

            conn.commit()
    except Exception:
        pass

inicializar_tablas()

def obtener_alicuotas_db():
    """Obtiene el diccionario de unidades y alícuotas desde la base de datos."""
    if not engine:
        return dict(UNIDADES_DEFECTO)
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text("SELECT unidad, alicuota FROM unidades ORDER BY unidad ASC"), conn)
            if not df.empty:
                return dict(zip(df['unidad'], df['alicuota'].astype(float)))
    except Exception:
        pass
    return dict(UNIDADES_DEFECTO)

# -----------------------------------------------------------------------------
# CÁLCULOS FINANCIEROS
# -----------------------------------------------------------------------------
def calcular_estado_cuenta(apartamento, mes_hasta):
    alicuotas = obtener_alicuotas_db()
    pct = alicuotas.get(apartamento, 6.00) / 100.0

    if not engine:
        return {"mes_actual": 0.0, "deuda_anterior": 0.0, "pagos_mes": 0.0, "total_deber": 0.0}

    try:
        with engine.connect() as conn:
            df_gastos = pd.read_sql(
                text("SELECT mes_anio, COALESCE(SUM(monto), 0) as total_gasto FROM gastos WHERE estatus = 'Aprobado' AND mes_anio <= :m GROUP BY mes_anio ORDER BY mes_anio ASC"),
                conn, params={"m": mes_hasta}
            )
            df_pagos = pd.read_sql(
                text("SELECT mes_anio, COALESCE(SUM(monto), 0) as total_pago FROM pagos_reportados WHERE apartamento = :ap AND tipo_pago = 'Mensualidad' AND estatus = 'Aprobado' AND mes_anio <= :m GROUP BY mes_anio"),
                conn, params={"ap": apartamento, "m": mes_hasta}
            )

        pagos_dict = dict(zip(df_pagos['mes_anio'], df_pagos['total_pago'])) if not df_pagos.empty else {}
        deuda_anterior, cuota_mes_actual, pagos_mes_actual = 0.0, 0.0, 0.0

        if not df_gastos.empty:
            for _, row in df_gastos.iterrows():
                m = row['mes_anio']
                cuota = round(float(row['total_gasto']) * pct, 2)
                pago = float(pagos_dict.get(m, 0.0))

                if m == mes_hasta:
                    cuota_mes_actual = cuota
                    pagos_mes_actual = pago
                else:
                    deuda_anterior += (cuota - pago)

        total_adeudado = round(deuda_anterior + cuota_mes_actual - pagos_mes_actual, 2)
        return {
            "mes_actual": cuota_mes_actual,
            "deuda_anterior": round(deuda_anterior, 2),
            "pagos_mes": pagos_mes_actual,
            "total_deber": total_adeudado
        }
    except Exception:
        return {"mes_actual": 0.0, "deuda_anterior": 0.0, "pagos_mes": 0.0, "total_deber": 0.0}

# -----------------------------------------------------------------------------
# CONTROL DE SESIÓN
# -----------------------------------------------------------------------------
if "usuario_logueado" not in st.session_state:
    st.session_state.usuario_logueado = None
if "rol_logueado" not in st.session_state:
    st.session_state.rol_logueado = None

def cerrar_sesion():
    st.session_state.usuario_logueado = None
    st.session_state.rol_logueado = None
    st.rerun()

# -----------------------------------------------------------------------------
# 1. PORTAL DE ACCESO NEUTRO
# -----------------------------------------------------------------------------
if not st.session_state.usuario_logueado:
    st.markdown("<h2 style='text-align: center;'>🔒 Portal de Acceso</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: gray;'>Ingresa tus credenciales para continuar.</p>", unsafe_allow_html=True)

    if error_conexion:
        st.error(f"⚠️ Error de conexión: {error_conexion}")

    with st.form("form_login"):
        usuario_input = st.text_input("Usuario (ej. 1A, PH o admin)").strip()
        clave_input = st.text_input("Contraseña", type="password").strip()
        bot_login = st.form_submit_button("Ingresar", type="primary", use_container_width=True)

        if bot_login:
            if not usuario_input or not clave_input:
                st.error("Por favor completa todos los campos.")
            elif not engine:
                st.error("Base de datos no disponible.")
            else:
                try:
                    with engine.connect() as conn:
                        row = conn.execute(
                            text("SELECT usuario, clave, rol FROM usuarios WHERE LOWER(usuario) = LOWER(:u)"),
                            {"u": usuario_input}
                        ).fetchone()

                    if row and row[1] == clave_input:
                        st.session_state.usuario_logueado = row[0]
                        st.session_state.rol_logueado = row[2]
                        st.rerun()
                    else:
                        st.error("❌ Credenciales incorrectas.")
                except Exception as e:
                    st.error(f"Error al ingresar: {e}")

# -----------------------------------------------------------------------------
# 2. VISTA DE PROPIETARIOS
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "propietario":
    user_actual = st.session_state.usuario_logueado
    alicuotas = obtener_alicuotas_db()
    pct_user = alicuotas.get(user_actual, 6.00)

    col_head, col_out = st.columns([3, 1])
    with col_head:
        st.title(f"🏢 Apartamento {user_actual} (Alícuota: {pct_user}%)")
    with col_out:
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cerrar_sesion()

    st.write("---")

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Recibo del Mes", "⭐ Cuotas Extraordinarias", "📥 Reportar Pago", "📋 Mis Pagos"])

    # --- TAB 1: GASTOS COMUNES ---
    with tab1:
        mes_filtro = st.text_input("Consulta de mes (AAAA-MM):", value=datetime.now().strftime("%Y-%m"))
        datos = calcular_estado_cuenta(user_actual, mes_filtro)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Morosidad Anterior", f"${datos['deuda_anterior']:,.2f}")
        c2.metric("Cuota Mes Actual", f"${datos['mes_actual']:,.2f}")
        c3.metric("Pagos Validados", f"${datos['pagos_mes']:,.2f}")
        c4.metric("TOTAL A PAGAR", f"${datos['total_deber']:,.2f}", delta=-datos['total_deber'] if datos['total_deber'] > 0 else 0)

    # --- TAB 2: CUOTAS EXTRAORDINARIAS ---
    with tab2:
        st.subheader("Cuotas Extraordinarias Asignadas")
        try:
            with engine.connect() as conn:
                df_ce = pd.read_sql(text("SELECT id, concepto, monto_total, fecha_emision, estatus FROM cuotas_extraordinarias WHERE estatus = 'Activa' ORDER BY id DESC"), conn)

            if df_ce.empty:
                st.info("No hay cuotas extraordinarias activas en este momento.")
            else:
                filas_ce = []
                for _, r in df_ce.iterrows():
                    m_total = float(r['monto_total'])
                    m_corresponde = round(m_total * (pct_user / 100.0), 2)

                    # Verificar pagos para esta cuota extra
                    with engine.connect() as conn:
                        pagado = conn.execute(
                            text("SELECT COALESCE(SUM(monto),0) FROM pagos_reportados WHERE apartamento = :a AND id_cuota_extra = :id AND estatus = 'Aprobado'"),
                            {"a": user_actual, "id": r['id']}
                        ).scalar()

                    saldo_ce = round(m_corresponde - float(pagado), 2)
                    filas_ce.append({
                        "ID": r['id'],
                        "Concepto": r['concepto'],
                        "Monto Total Fondo ($)": f"${m_total:,.2f}",
                        "Mi Cuota por Alícuota ($)": f"${m_corresponde:,.2f}",
                        "Abonado ($)": f"${float(pagado):,.2f}",
                        "Pendiente ($)": f"${saldo_ce:,.2f}",
                        "Estatus": "🟢 Pagado" if saldo_ce <= 0 else "🔴 Pendiente"
                    })
                st.dataframe(pd.DataFrame(filas_ce), use_container_width=True)
        except Exception as e:
            st.error(f"Error consultando cuotas extraordinarias: {e}")

    # --- TAB 3: REPORTAR PAGO ---
    with tab3:
        st.subheader("Reportar Comprobante de Pago")
        tipo_p = st.radio("Tipo de Cobro a Cancelar:", ["Mensualidad de Condominio", "Cuota Extraordinaria"])

        id_ce_sel = None
        if tipo_p == "Cuota Extraordinaria":
            try:
                with engine.connect() as conn:
                    df_ce_opts = pd.read_sql(text("SELECT id, concepto FROM cuotas_extraordinarias WHERE estatus = 'Activa'"), conn)
                if df_ce_opts.empty:
                    st.warning("No hay cuotas extraordinarias registradas para abonar.")
                else:
                    opcion = st.selectbox("Selecciona la Cuota Extraordinaria:", df_ce_opts.apply(lambda x: f"#{x['id']} - {x['concepto']}", axis=1))
                    id_ce_sel = int(opcion.split(" - ")[0].replace("#", ""))
            except Exception as e:
                st.error(f"Error al cargar lista de cuotas: {e}")

        with st.form("form_pago", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                st.text_input("Apartamento", value=user_actual, disabled=True)
                mes_pago = st.text_input("Mes Relacionado (AAAA-MM)", value=datetime.now().strftime("%Y-%m"))
                monto = st.number_input("Monto Pagado ($)", min_value=0.01, step=0.01)
            with c2:
                metodo = st.selectbox("Método de Pago", ["Transferencia Bancaria", "Pago Móvil", "Zelle", "Efectivo $"])
                referencia = st.text_input("Número de Referencia")
                fecha_pago = st.date_input("Fecha de Pago", value=datetime.now().date())

            comprobante = st.file_uploader("Adjuntar Comprobante", type=["png", "jpg", "jpeg", "pdf"])
            btn_subir = st.form_submit_button("🚀 Registrar Pago", type="primary")

            if btn_subir:
                if not referencia.strip():
                    st.error("Por favor ingresa la referencia de pago.")
                else:
                    nombre_file = comprobante.name if comprobante else "Sin comprobante"
                    tipo_str = "Extraordinaria" if tipo_p == "Cuota Extraordinaria" else "Mensualidad"
                    try:
                        with engine.connect() as conn:
                            conn.execute(text("""
                                INSERT INTO pagos_reportados (apartamento, tipo_pago, mes_anio, id_cuota_extra, monto, metodo_pago, referencia, fecha_pago, comprobante_nombre, estatus)
                                VALUES (:apto, :tipo, :mes, :id_ce, :monto, :metodo, :ref, :fecha, :comp, 'Pendiente')
                            """), {
                                "apto": user_actual, "tipo": tipo_str, "mes": mes_pago, "id_ce": id_ce_sel,
                                "monto": monto, "metodo": metodo, "ref": referencia, "fecha": fecha_pago, "comp": nombre_file
                            })
                            conn.commit()
                        st.success("✅ Pago registrado para validación de administración.")
                    except Exception as e:
                        st.error(f"Error registrando el pago: {e}")

    # --- TAB 4: MIS PAGOS ---
    with tab4:
        try:
            with engine.connect() as conn:
                df_mis_p = pd.read_sql(
                    text("SELECT tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago, estatus FROM pagos_reportados WHERE apartamento = :a ORDER BY id DESC"),
                    conn, params={"a": user_actual}
                )
            if df_mis_p.empty:
                st.info("Sin pagos registrados.")
            else:
                st.dataframe(df_mis_p, use_container_width=True)
        except Exception as e:
            st.error(f"Error consultando historial: {e}")

# -----------------------------------------------------------------------------
# 3. VISTA DE ADMINISTRACIÓN
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "admin":
    col_head, col_out = st.columns([3, 1])
    with col_head:
        st.title("⚙️ Módulo de Administración")
    with col_out:
        st.write("")
        if st.button("🚪 Cerrar Sesión", use_container_width=True):
            cerrar_sesion()

    st.write("---")

    t1, t2, t3, t4, t5 = st.tabs(["📊 Gastos del Mes", "⭐ Cuotas Extras", "✅ Validar Pagos", "🏢 Alícuotas", "🚨 Morosidad"])

    # GASTOS MENSUALES
    with t1:
        st.subheader("Registrar Gasto Común del Mes")
        with st.form("form_gasto"):
            mes = st.text_input("Mes / Año (AAAA-MM)", value=datetime.now().strftime("%Y-%m"))
            concepto = st.text_input("Descripción del Gasto")
            monto = st.number_input("Monto Total ($)", min_value=0.01, step=0.01)
            btn = st.form_submit_button("Guardar Gasto", type="primary")

            if btn and concepto:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("INSERT INTO gastos (mes_anio, concepto, monto, estatus) VALUES (:m, :c, :mo, 'Aprobado')"),
                            {"m": mes, "c": concepto, "mo": monto}
                        )
                        conn.commit()
                    st.success("Gasto guardado exitosamente.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error registrando gasto: {e}")

    # CUOTAS EXTRAORDINARIAS
    with t2:
        st.subheader("Crear Cuota Extraordinaria (Fuera de Recibo Mensual)")
        with st.form("form_ce"):
            concepto_ce = st.text_input("Concepto o Motivo (ej. Reparación de Ascensor)")
            monto_ce = st.number_input("Monto Total del Fondo ($)", min_value=0.01, step=0.01)
            btn_ce = st.form_submit_button("Crear Cuota Extraordinaria", type="primary")

            if btn_ce and concepto_ce:
                try:
                    with engine.connect() as conn:
                        conn.execute(
                            text("INSERT INTO cuotas_extraordinarias (concepto, monto_total) VALUES (:c, :m)"),
                            {"c": concepto_ce, "m": monto_ce}
                        )
                        conn.commit()
                    st.success("Cuota extraordinaria registrada.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Error al crear cuota: {e}")

        st.write("---")
        st.subheader("Cuotas Extraordinarias Registradas")
        try:
            with engine.connect() as conn:
                df_ce_admin = pd.read_sql(text("SELECT * FROM cuotas_extraordinarias ORDER BY id DESC"), conn)
            st.dataframe(df_ce_admin, use_container_width=True)
        except Exception as e:
            st.error(f"Error consultando cuotas extras: {e}")

    # VALIDAR PAGOS
    with t3:
        st.subheader("Pagos Pendientes por Validar")
        try:
            with engine.connect() as conn:
                df_p = pd.read_sql(
                    text("SELECT id, apartamento, tipo_pago, mes_anio, monto, metodo_pago, referencia, fecha_pago FROM pagos_reportados WHERE estatus = 'Pendiente' ORDER BY id ASC"),
                    conn
                )
            if df_p.empty:
                st.info("No hay pagos pendientes.")
            else:
                st.dataframe(df_p, use_container_width=True)
                pid = st.selectbox("ID de Pago a Procesar:", df_p["id"].tolist())
                ca, cr = st.columns(2)
                with ca:
                    if st.button("✅ Aprobar Pago", use_container_width=True):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Aprobado' WHERE id = :i"), {"i": pid})
                            conn.commit()
                        st.success(f"Pago #{pid} Aprobado.")
                        st.rerun()
                with cr:
                    if st.button("❌ Rechazar Pago", use_container_width=True):
                        with engine.connect() as conn:
                            conn.execute(text("UPDATE pagos_reportados SET estatus = 'Rechazado' WHERE id = :i"), {"i": pid})
                            conn.commit()
                        st.warning(f"Pago #{pid} Rechazado.")
                        st.rerun()
        except Exception as e:
            st.error(f"Error procesando pagos: {e}")

    # ALÍCUOTAS / UNIDADES
    with t4:
        st.subheader("Configuración de Alícuotas por Apartamento")
        try:
            with engine.connect() as conn:
                df_alic = pd.read_sql(text("SELECT unidad as \"Inmueble\", alicuota as \"Alícuota (%)\" FROM unidades ORDER BY unidad ASC"), conn)

            st.dataframe(df_alic, use_container_width=True)
            st.info(f"Suma Total de Alícuotas: {df_alic['Alícuota (%)'].sum():.2f}%")

            st.write("---")
            st.markdown("<b>Actualizar Alícuota de una Unidad:</b>", unsafe_allow_html=True)
            u_sel = st.selectbox("Selecciona Inmueble:", df_alic["Inmueble"].tolist())
            nueva_alic = st.number_input("Nueva Alícuota (%)", min_value=0.01, max_value=100.00, value=6.00, step=0.01)
            if st.button("Guardar Cambios de Alícuota"):
                with engine.connect() as conn:
                    conn.execute(text("UPDATE unidades SET alicuota = :a WHERE unidad = :u"), {"a": nueva_alic, "u": u_sel})
                    conn.commit()
                st.success(f"Alícuota de {u_sel} actualizada a {nueva_alic}%.")
                st.rerun()
        except Exception as e:
            st.error(f"Error cargando alícuotas: {e}")

    # MOROSIDAD
    with t5:
        st.subheader("Estado de Morosidad General")
        mes_eval = st.text_input("Mes de Evaluación (AAAA-MM):", value=datetime.now().strftime("%Y-%m"))
        alicuotas_map = obtener_alicuotas_db()

        filas_m = []
        total_m = 0.0

        for apto in alicuotas_map.keys():
            res = calcular_estado_cuenta(apto, mes_eval)
            deuda = res["total_deber"]
            total_m += deuda
            filas_m.append({
                "Inmueble": apto,
                "Alícuota": f"{alicuotas_map[apto]}%",
                "Deuda Anterior": f"${res['deuda_anterior']:,.2f}",
                "Cuota Mes": f"${res['mes_actual']:,.2f}",
                "Abonado": f"${res['pagos_mes']:,.2f}",
                "Deuda Total": f"${deuda:,.2f}",
                "Estatus": "🟢 Al día" if deuda <= 0 else "🔴 Pendiente"
            })

        st.metric("Deuda Total del Condominio", f"${total_m:,.2f}")
        st.dataframe(pd.DataFrame(filas_m), use_container_width=True)
