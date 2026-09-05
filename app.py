from datetime import datetime, date
import io
import urllib.parse
from PIL import Image
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import requests
from sqlalchemy import create_engine, text
import streamlit as st

# -----------------------------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA E ICONO PERSONALIZADO
# -----------------------------------------------------------------------------
try:
  logo_img = Image.open("logo.jpg")
except Exception:
  logo_img = "🏢"

st.set_page_config(
    page_title="Sistema de Gestión de Condominios YS",
    page_icon=logo_img,
    layout="wide",
)

UNIDADES_DEFECTO = [
    ("1A", 6.00),
    ("1B", 6.00),
    ("2", 12.00),
    ("3A", 6.00),
    ("3B", 6.00),
    ("4A", 6.00),
    ("4B", 6.00),
    ("5A", 6.00),
    ("5B", 6.00),
    ("6A", 6.00),
    ("6B", 6.00),
    ("7", 12.00),
    ("PH", 16.00),
]


# -----------------------------------------------------------------------------
# FUNCIONES AUXILIARES DE FECHA
# -----------------------------------------------------------------------------
def obtener_mes_anterior():
  hoy = datetime.now()
  if hoy.month == 1:
    return f"{hoy.year - 1}-12"
  else:
    return f"{hoy.year}-{hoy.month - 1:02d}"


def obtener_mes_actual():
  return datetime.now().strftime("%Y-%m")


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
        url, connect_args={"prepare_threshold": None}, pool_pre_ping=True
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
      conn.execute(
          text("""
                CREATE TABLE IF NOT EXISTS configuracion_edificio (
                    id INT PRIMARY KEY DEFAULT 1,
                    nombre VARCHAR(150) NOT NULL,
                    rif VARCHAR(30) NOT NULL,
                    direccion TEXT NOT NULL
                );
            """)
      )

      res_ed = conn.execute(
          text("SELECT COUNT(*) FROM configuracion_edificio")
      ).scalar()
      if res_ed == 0:
        conn.execute(
            text("""
                    INSERT INTO configuracion_edificio (id, nombre, rif, direccion)
                    VALUES (1, 'Residencias El Condominio', 'J-12345678-0', 'Calle Principal, Edificio Central')
                """)
        )

      conn.execute(
          text("""
                CREATE TABLE IF NOT EXISTS unidades (
                    unidad VARCHAR(10) PRIMARY KEY,
                    alicuota NUMERIC(5,2) NOT NULL,
                    propietario VARCHAR(100) DEFAULT 'Sin Asignar',
                    telefono VARCHAR(30) DEFAULT ''
                );
            """)
      )

      try:
        conn.execute(
            text(
                "ALTER TABLE unidades ADD COLUMN IF NOT EXISTS propietario"
                " VARCHAR(100) DEFAULT 'Sin Asignar'"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE unidades ADD COLUMN IF NOT EXISTS telefono"
                " VARCHAR(30) DEFAULT ''"
            )
        )
      except Exception:
        pass

      res_u = conn.execute(text("SELECT COUNT(*) FROM unidades")).scalar()
      if res_u == 0:
        for u, a in UNIDADES_DEFECTO:
          conn.execute(
              text(
                  "INSERT INTO unidades (unidad, alicuota, propietario,"
                  " telefono) VALUES (:u, :a, 'Propietario', '')"
              ),
              {"u": u, "a": a},
          )

      conn.execute(
          text("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    usuario VARCHAR(20) PRIMARY KEY,
                    clave VARCHAR(100) NOT NULL,
                    rol VARCHAR(20) NOT NULL
                );
            """)
      )

      admin_pwd = st.secrets.get("ADMIN_PASSWORD", "admin123")
      if not conn.execute(
          text("SELECT usuario FROM usuarios WHERE usuario = 'admin'")
      ).fetchone():
        conn.execute(
            text(
                "INSERT INTO usuarios (usuario, clave, rol) VALUES ('admin',"
                " :p, 'admin')"
            ),
            {"p": admin_pwd},
        )

      for u, _ in UNIDADES_DEFECTO:
        if not conn.execute(
            text("SELECT usuario FROM usuarios WHERE usuario = :u"), {"u": u}
        ).fetchone():
          conn.execute(
              text(
                  "INSERT INTO usuarios (usuario, clave, rol) VALUES (:u,"
                  " '1234', 'propietario')"
              ),
              {"u": u},
          )

      # TABLA DE TASA DE CAMBIO DIARIA
      conn.execute(
          text("""
                CREATE TABLE IF NOT EXISTS tasa_cambio (
                    fecha DATE PRIMARY KEY,
                    tasa NUMERIC(12, 4) NOT NULL
                );
            """)
      )

      conn.execute(
          text("""
                CREATE TABLE IF NOT EXISTS gastos (
                    id SERIAL PRIMARY KEY,
                    periodo VARCHAR(7),
                    mes_anio VARCHAR(7) NOT NULL,
                    concepto VARCHAR(200) NOT NULL,
                    monto NUMERIC(12,2) NOT NULL,
                    estatus VARCHAR(20) DEFAULT 'Pendiente',
                    fecha DATE DEFAULT CURRENT_DATE,
                    tipo VARCHAR(50) DEFAULT 'Comun',
                    proveedor VARCHAR(100) DEFAULT 'N/A'
                );
            """)
      )

      try:
        conn.execute(
            text(
                "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS tipo VARCHAR(50)"
                " DEFAULT 'Comun'"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS proveedor"
                " VARCHAR(100) DEFAULT 'N/A'"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE gastos ADD COLUMN IF NOT EXISTS fecha DATE DEFAULT"
                " CURRENT_DATE"
            )
        )
      except Exception:
        pass

      conn.execute(
          text("""
                CREATE TABLE IF NOT EXISTS cargos_individuales (
                    id SERIAL PRIMARY KEY,
                    apartamento VARCHAR(10) NOT NULL,
                    mes_anio VARCHAR(7) NOT NULL,
                    concepto VARCHAR(200) NOT NULL,
                    monto NUMERIC(12,2) NOT NULL,
                    fecha DATE DEFAULT CURRENT_DATE
                );
            """)
      )

      conn.execute(
          text("""
                CREATE TABLE IF NOT EXISTS cuotas_extraordinarias (
                    id SERIAL PRIMARY KEY,
                    concepto VARCHAR(200) NOT NULL,
                    monto_total NUMERIC(12,2) NOT NULL,
                    fecha_emision DATE DEFAULT CURRENT_DATE,
                    estatus VARCHAR(20) DEFAULT 'Pendiente'
                );
            """)
      )

      # PAGOS REPORTADOS ADAPTADOS A MULTIDIVISA
      conn.execute(
          text("""
                CREATE TABLE IF NOT EXISTS pagos_reportados (
                    id SERIAL PRIMARY KEY,
                    apartamento VARCHAR(10) NOT NULL,
                    tipo_pago VARCHAR(30) DEFAULT 'Mensualidad',
                    mes_anio VARCHAR(7),
                    monto_original NUMERIC(12, 2) NOT NULL,
                    moneda VARCHAR(10) DEFAULT 'USD',
                    tasa_aplicada NUMERIC(12, 4) DEFAULT 1.0,
                    monto_usd NUMERIC(12, 2) NOT NULL,
                    metodo_pago VARCHAR(50) NOT NULL,
                    referencia VARCHAR(100) NOT NULL,
                    fecha_pago DATE NOT NULL,
                    estatus VARCHAR(20) DEFAULT 'Pendiente',
                    fecha_reporte TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
      )

      try:
        conn.execute(
            text(
                "ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS"
                " monto_original NUMERIC(12,2) DEFAULT 0"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS moneda"
                " VARCHAR(10) DEFAULT 'USD'"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS"
                " tasa_aplicada NUMERIC(12,4) DEFAULT 1.0"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE pagos_reportados ADD COLUMN IF NOT EXISTS"
                " monto_usd NUMERIC(12,2) DEFAULT 0"
            )
        )
      except Exception:
        pass

      conn.commit()
  except Exception:
    pass


inicializar_tablas()


# -----------------------------------------------------------------------------
# FUNCIONES AUTOMÁTICAS DE TASA Y AUXILIARES
# -----------------------------------------------------------------------------
def verificar_y_actualizar_tasa_hoy(eng):
  hoy = date.today()
  if not eng:
    return 36.00
  try:
    with eng.connect() as conn:
      tasa_existente = conn.execute(
          text("SELECT tasa FROM tasa_cambio WHERE fecha = :f"), {"f": hoy}
      ).scalar()

      if tasa_existente:
        return float(tasa_existente)

      response = requests.get(
          "https://pydolarvenezuela-api.vercel.app/api/v1/dollar?monitor=bcv",
          timeout=5,
      )
      if response.status_code == 200:
        data = response.json()
        tasa_bcv = float(
            data.get("sources", {}).get("bcv", {}).get("price", 0.0)
        )

        if tasa_bcv > 0:
          conn.execute(
              text("""
                        INSERT INTO tasa_cambio (fecha, tasa)
                        VALUES (:f, :t)
                        ON CONFLICT (fecha) DO UPDATE SET tasa = EXCLUDED.tasa
                    """),
              {"f": hoy, "t": tasa_bcv},
          )
          conn.commit()
          return tasa_bcv

  except Exception:
    pass

  try:
    with eng.connect() as conn:
      ultima_tasa = conn.execute(
          text("SELECT tasa FROM tasa_cambio ORDER BY fecha DESC LIMIT 1")
      ).scalar()
      if ultima_tasa:
        return float(ultima_tasa)
  except Exception:
    pass

  return 36.00


def obtener_datos_edificio():
  if not engine:
    return {
        "nombre": "Residencias Condominio",
        "rif": "J-00000000-0",
        "direccion": "Ciudad",
    }
  try:
    with engine.connect() as conn:
      row = conn.execute(
          text(
              "SELECT nombre, rif, direccion FROM configuracion_edificio WHERE"
              " id = 1"
          )
      ).fetchone()
      if row:
        return {"nombre": row[0], "rif": row[1], "direccion": row[2]}
  except Exception:
    pass
  return {
      "nombre": "Residencias Condominio",
      "rif": "J-00000000-0",
      "direccion": "Ciudad",
  }


def obtener_unidades_df():
  if not engine:
    return pd.DataFrame(UNIDADES_DEFECTO, columns=["unidad", "alicuota"])
  try:
    with engine.connect() as conn:
      return pd.read_sql(
          text(
              "SELECT unidad, alicuota, propietario, telefono FROM unidades"
              " ORDER BY unidad ASC"
          ),
          conn,
      )
  except Exception:
    return pd.DataFrame(UNIDADES_DEFECTO, columns=["unidad", "alicuota"])


def obtener_tasa_por_fecha(fecha_buscada):
  if not engine:
    return 1.0
  try:
    with engine.connect() as conn:
      res = conn.execute(
          text("SELECT tasa FROM tasa_cambio WHERE fecha = :f"),
          {"f": fecha_buscada},
      ).scalar()
      if res:
        return float(res)

      res_cercana = conn.execute(
          text(
              "SELECT tasa FROM tasa_cambio WHERE fecha <= :f ORDER BY fecha"
              " DESC LIMIT 1"
          ),
          {"f": fecha_buscada},
      ).scalar()
      if res_cercana:
        return float(res_cercana)
  except Exception:
    pass
  return 1.0


def generar_enlace_whatsapp(telefono, mensaje):
  num_limpio = "".join(filter(str.isdigit, str(telefono or "")))
  msg_enc = urllib.parse.quote(mensaje)
  if num_limpio:
    return f"https://wa.me/{num_limpio}?text={msg_enc}"
  return f"https://wa.me/?text={msg_enc}"


def generar_pdf_recibo(apt, periodo, total_cuota, detalles_gastos, alicuota):
  datos_ed = obtener_datos_edificio()
  buffer = io.BytesIO()
  doc = SimpleDocTemplate(
      buffer,
      pagesize=letter,
      rightMargin=36,
      leftMargin=36,
      topMargin=36,
      bottomMargin=36,
  )
  styles = getSampleStyleSheet()

  story = []

  title_style = ParagraphStyle(
      "DocTitle",
      parent=styles["Heading1"],
      fontSize=16,
      leading=20,
      alignment=1,
      textColor=colors.HexColor("#1E3A8A"),
  )

  story.append(Paragraph(f"<b>{datos_ed['nombre']}</b>", title_style))
  story.append(
      Paragraph(
          f"RIF: {datos_ed['rif']} | {datos_ed['direccion']}", styles["Normal"]
      )
  )
  story.append(Spacer(1, 15))

  story.append(
      Paragraph(f"<b>AVISO DE COBRO - PERIODO: {periodo}</b>", styles["Heading2"])
  )
  story.append(
      Paragraph(
          f"<b>Unidad:</b> {apt} | <b>Alícuota Aplicada:</b> {alicuota}%",
          styles["Normal"],
      )
  )
  story.append(Spacer(1, 15))

  tabla_datos = [["Concepto / Descripción", "Monto Base ($)", "Cuota Parte ($)"]]
  for item in detalles_gastos:
    tabla_datos.append(
        [item["concepto"], f"${item['base']:,.2f}", f"${item['monto']:,.2f}"]
    )

  tabla_datos.append(["TOTAL A PAGAR", "", f"${total_cuota:,.2f}"])

  t = Table(tabla_datos, colWidths=[280, 110, 110])
  t.setStyle(
      TableStyle([
          ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
          ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
          ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
          ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
          ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
          ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#E2E8F0")),
          ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
          ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
      ])
  )

  story.append(t)
  story.append(Spacer(1, 20))
  story.append(
      Paragraph(
          "Por favor realice su pago y repórtelo en la plataforma indicando su"
          " referencia.",
          styles["Italic"],
      )
  )

  doc.build(story)
  buffer.seek(0)
  return buffer


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


tasa_del_dia_auto = verificar_y_actualizar_tasa_hoy(engine)

# -----------------------------------------------------------------------------
# 1. PORTAL DE ACCESO
# -----------------------------------------------------------------------------
if not st.session_state.usuario_logueado:
  st.markdown(
      "<h2 style='text-align: center;'>🔒 Portal de Acceso</h2>",
      unsafe_allow_html=True,
  )
  st.markdown(
      "<p style='text-align: center; color: gray;'>Ingresa tus credenciales"
      " para continuar.</p>",
      unsafe_allow_html=True,
  )

  if error_conexion:
    st.error(f"⚠️ Error de conexión: {error_conexion}")

  with st.form("form_login"):
    usuario_input = st.text_input("Usuario (ej. 1A, PH o admin)").strip()
    clave_input = st.text_input("Contraseña", type="password").strip()
    bot_login = st.form_submit_button(
        "Ingresar", type="primary", use_container_width=True
    )

    if bot_login:
      if not usuario_input or not clave_input:
        st.error("Por favor completa los campos.")
      elif not engine:
        st.error("Base de datos no disponible.")
      else:
        try:
          with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT usuario, clave, rol FROM usuarios WHERE"
                    " LOWER(usuario) = LOWER(:u)"
                ),
                {"u": usuario_input},
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
  datos_ed = obtener_datos_edificio()
  df_u = obtener_unidades_df()
  row_u = df_u[df_u["unidad"] == user_actual]
  prop_nombre = (
      row_u["propietario"].values[0] if not row_u.empty else "Propietario"
  )
  prop_tel = row_u["telefono"].values[0] if not row_u.empty else ""
  pct_user = float(row_u["alicuota"].values[0]) if not row_u.empty else 6.0

  col_head, col_out = st.columns([3, 1])
  with col_head:
    st.title(f"🏢 {datos_ed['nombre']} - Unidad {user_actual}")
    st.caption(f"Propietario: {prop_nombre} | Alícuota: {pct_user}%")
  with col_out:
    st.write("")
    if st.button("🚪 Cerrar Sesión", use_container_width=True):
      cerrar_sesion()

  st.write("---")

  t_p1, t_p2, t_p3 = st.tabs(
      ["📄 Estado de Cuenta", "💳 Reportar Pago", "📋 Mis Pagos Reportados"]
  )

  with t_p1:
    st.subheader("📊 Mis Deudas y Recibos")

    mes_vencido_defecto = obtener_mes_anterior()
    mes_actual = st.text_input(
        "Periodo a Consultar (AAAA-MM):",
        value=mes_vencido_defecto,
        key="prop_consulta_mes",
    )

    try:
      with engine.connect() as conn:
        gastos_aprob = (
            conn.execute(
                text(
                    "SELECT SUM(monto) FROM gastos WHERE mes_anio = :m AND estatus"
                    " = 'Aprobado'"
                ),
                {"m": mes_actual},
            ).scalar()
            or 0
        )

        cargos_ind = (
            conn.execute(
                text(
                    "SELECT SUM(monto) FROM cargos_individuales WHERE"
                    " apartamento = :u AND mes_anio = :m"
                ),
                {"u": user_actual, "m": mes_actual},
            ).scalar()
            or 0
        )

      cuota_comun = float(gastos_aprob) * (pct_user / 100.0)
      total_mes = cuota_comun + float(cargos_ind)

      c1, c2, c3 = st.columns(3)
      c1.metric("Cuota Común Estimada", f"${cuota_comun:,.2f}")
      c2.metric("Cargos No Comunes / Extra", f"${float(cargos_ind):,.2f}")
      c3.metric(f"Total Periodo ({mes_actual})", f"${total_mes:,.2f}")

      st.write("---")
      st.subheader("📥 Descargar Recibo / Compartir por WhatsApp")

      detalles = [
          {
              "concepto": "Gastos Comunes del Edificio",
              "base": float(gastos_aprob),
              "monto": cuota_comun,
          },
          {
              "concepto": "Cargos Indiv. No Comunes / Cuotas Extras",
              "base": float(cargos_ind),
              "monto": float(cargos_ind),
          },
      ]
      pdf_bytes = generar_pdf_recibo(
          user_actual, mes_actual, total_mes, detalles, pct_user
      )

      msg_ws = (
          f"🏢 *{datos_ed['nombre']}*\n📄 *AVISO DE COBRO"
          f" ({mes_actual})*\nUnidad: {user_actual}\nTotal a Pagar:"
          f" ${total_mes:,.2f}\n\nPor favor reportar el pago a través de la"
          " app."
      )
      link_ws = generar_enlace_whatsapp(prop_tel, msg_ws)

      col_pdf, col_ws = st.columns(2)
      with col_pdf:
        st.download_button(
            f"📄 Descargar Recibo PDF ({mes_actual})",
            data=pdf_bytes,
            file_name=f"recibo_{user_actual}_{mes_actual}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
      with col_ws:
        st.link_button(
            "📲 Compartir por WhatsApp", link_ws, use_container_width=True
        )

    except Exception as e:
      st.error(f"Error consultando estado de cuenta: {e}")

  with t_p2:
    st.subheader("📝 Formulario de Reporte de Pago (Bolívares o Dólares)")
    st.info(
        "ℹ️ Si pagas en Bolívares (VES), ingresa el monto en Bs. La aplicación"
        " buscará automáticamente la tasa del dólar oficial BCV correspondiente"
        " a la fecha de tu pago y lo convertirá a dólares ($)."
    )

    with st.form("form_reportar_pago"):
      tipo_p = st.selectbox(
          "Tipo de Pago", ["Mensualidad", "Cuota Extraordinaria"]
      )
      mes_p = st.text_input(
          "Periodo / Mes-Año a Pagar (AAAA-MM)", value=obtener_mes_anterior()
      )

      col_mon1, col_mon2 = st.columns(2)
      with col_mon1:
        moneda = st.selectbox("Moneda del Pago", ["USD ($)", "VES (Bs.)"])
      with col_mon2:
        fecha_p = st.date_input("Fecha de Realización del Pago", datetime.now())

      monto_input = st.number_input(
          "Monto Pagado (en la moneda seleccionada)", min_value=0.01, step=0.01
      )

      metodo = st.selectbox(
          "Método de Pago",
          [
              "Pago Móvil",
              "Transferencia VES",
              "Efectivo USD",
              "Zelle",
              "Binance / Crypto",
          ],
      )
      ref = st.text_input("Número de Referencia / Comprobante")

      btn_pago = st.form_submit_button("Enviar Reporte de Pago", type="primary")

      if btn_pago:
        if not ref:
          st.error("Debes ingresar el número de referencia o comprobante.")
        else:
          try:
            tasa_usada = 1.0
            monto_en_usd = monto_input

            if "VES" in moneda:
              tasa_usada = obtener_tasa_por_fecha(fecha_p)
              if tasa_usada <= 1.0:
                st.warning(
                    f"⚠️ No se encontró tasa registrada para la fecha {fecha_p}."
                    " Se usará 1.0 por defecto."
                )
              else:
                monto_en_usd = monto_input / tasa_usada

            with engine.connect() as conn:
              conn.execute(
                  text("""
                                    INSERT INTO pagos_reportados (
                                        apartamento, tipo_pago, mes_anio, monto_original, moneda, 
                                        tasa_aplicada, monto_usd, metodo_pago, referencia, fecha_pago, estatus
                                    )
                                    VALUES (:u, :tp, :m, :mo_orig, :mon, :tasa, :mo_usd, :met, :ref, :f, 'Pendiente')
                                """),
                  {
                      "u": user_actual,
                      "tp": tipo_p,
                      "m": mes_p,
                      "mo_orig": monto_input,
                      "mon": "VES" if "VES" in moneda else "USD",
                      "tasa": tasa_usada,
                      "mo_usd": monto_en_usd,
                      "met": metodo,
                      "ref": ref,
                      "f": fecha_p,
                  },
              )
              conn.commit()
            st.success(
                f"✅ Pago reportado con éxito. Equivalente calculado:"
                f" ${monto_en_usd:,.2f} USD (Tasa: {tasa_usada:,.4f}). Queda en"
                " espera de verificación."
            )
            st.rerun()
          except Exception as e:
            st.error(f"Error al registrar pago: {e}")

  with t_p3:
    st.subheader("📋 Historial de Mis Reportes")
    try:
      with engine.connect() as conn:
        df_mis_pagos = pd.read_sql(
            text("""
                        SELECT fecha_pago, tipo_pago, mes_anio, monto_original, moneda, tasa_aplicada, monto_usd, metodo_pago, referencia, estatus 
                        FROM pagos_reportados 
                        WHERE apartamento = :u 
                        ORDER BY id DESC
                    """),
            conn,
            params={"u": user_actual},
        )

      if df_mis_pagos.empty:
        st.info("No has registrado ningún pago hasta el momento.")
      else:
        st.dataframe(df_mis_pagos, use_container_width=True)
    except Exception as e:
      st.error(f"Error cargando el historial: {e}")

# -----------------------------------------------------------------------------
# 3. VISTA DE ADMINISTRACIÓN
# -----------------------------------------------------------------------------
elif st.session_state.rol_logueado == "admin":
  datos_ed = obtener_datos_edificio()

  col_head, col_out = st.columns([3, 1])
  with col_head:
    st.title("⚙️ Módulo de Administración")
    st.caption(f"{datos_ed['nombre']} | RIF: {datos_ed['rif']}")
  with col_out:
    st.write("")
    if st.button("🚪 Cerrar Sesión", use_container_width=True):
      cerrar_sesion()

  st.write("---")

  t1, t2, t3, t4, t5, t6, t7, t8, t9 = st.tabs([
      "📊 Gastos Comunes",
      "🛠️ Gastos No Comunes",
      "⭐ Cuotas Extras",
      "💱 Tasas de Cambio",
      "✅ Validar Pagos",
      "🏢 Alícuotas y Unidades",
      "🚨 Morosidad y Recibos",
      "⚙️ Datos Edificio",
      "💱 Conciliación de Pagos en Bolívares (Tasa BCV)"
  ])

  with t1:
    st.subheader("➕ Cargar Nuevo Gasto Común")
    with st.form("form_gasto"):
      col_g1, col_g2 = st.columns(2)
      with col_g1:
        mes = st.text_input(
            "Mes / Año del Gasto (AAAA-MM)", value=obtener_mes_anterior()
        )
        concepto = st.text_input("Descripción del Gasto Común")
      with col_g2:
        proveedor = st.text_input("Proveedor", value="N/A")
        monto = st.number_input("Monto Total ($)", min_value=0.01, step=0.01)

      btn = st.form_submit_button(
          "Cargar para Previsualizar/Aprobar", type="primary"
      )

      if btn and concepto:
        try:
          with engine.connect() as conn:
            conn.execute(
                text("""
                                INSERT INTO gastos (periodo, mes_anio, concepto, monto, estatus, fecha, tipo, proveedor) 
                                VALUES (:m, :m, :c, :mo, 'Pendiente', CURRENT_DATE, 'Comun', :p)
                            """),
                {
                    "m": mes,
                    "c": concepto,
                    "mo": monto,
                    "p": proveedor if proveedor.strip() else "N/A",
                },
            )
            conn.commit()
          st.success("Gasto guardado en estado pendiente de aprobación.")
          st.rerun()
        except Exception as e:
          st.error(f"Error registrando gasto: {e}")

    st.write("---")
    st.subheader("🔍 Previsualizar y Aprobar Gastos Comunes")
    mes_filtro = st.text_input(
        "Filtrar gastos por periodo (AAAA-MM):",
        value=obtener_mes_anterior(),
        key="filtro_gastos_admin",
    )

    try:
      with engine.connect() as conn:
        df_gastos_pendientes = pd.read_sql(
            text(
                "SELECT id, concepto, monto, estatus, mes_anio FROM gastos WHERE"
                " mes_anio = :m ORDER BY id DESC"
            ),
            conn,
            params={"m": mes_filtro},
        )

      if df_gastos_pendientes.empty:
        st.info(f"No hay gastos registrados para el periodo {mes_filtro}.")
      else:
        for _, r_gasto in df_gastos_pendientes.iterrows():
          c_detalles, c_acciones = st.columns([3, 2])
          with c_detalles:
            badge_estatus = (
                "🟡 Pendiente"
                if r_gasto["estatus"] == "Pendiente"
                else "🟢 Aprobado"
            )
            st.markdown(
                f"**Concepto:** {r_gasto['concepto']} | **Monto:**"
                f" ${float(r_gasto['monto']):,.2f} | **Estatus:**"
                f" {badge_estatus}"
            )

          with c_acciones:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
              if r_gasto["estatus"] == "Pendiente":
                if st.button(
                    "✅ Aprobar",
                    key=f"app_gasto_{r_gasto['id']}",
                    type="primary",
                ):
                  with engine.connect() as conn:
                    conn.execute(
                        text(
                            "UPDATE gastos SET estatus = 'Aprobado' WHERE id ="
                            " :id"
                        ),
                        {"id": r_gasto["id"]},
                    )
                    conn.commit()
                  st.success("Gasto aprobado.")
                  st.rerun()
            with btn_col2:
              if st.button(
                  "❌ Eliminar",
                  key=f"del_gasto_{r_gasto['id']}",
                  type="secondary",
              ):
                with engine.connect() as conn:
                  conn.execute(
                      text("DELETE FROM gastos WHERE id = :id"),
                      {"id": r_gasto["id"]},
                  )
                  conn.commit()
                st.success("Gasto eliminado.")
                st.rerun()
          st.markdown(
              "<hr style='margin: 5px 0;'>", unsafe_allow_html=True
          )

    except Exception as e:
      st.error(f"Error consultando gastos: {e}")

  with t2:
    st.subheader("🛠️ Cargar Gasto No Común (Cargo Individual)")
    df_unidades_list = obtener_unidades_df()

    with st.form("form_cargo_ind"):
      c_nc1, c_nc2 = st.columns(2)
      with c_nc1:
        apt_destino = st.selectbox(
            "Apartamento / Unidad Destino", df_unidades_list["unidad"].tolist()
        )
        mes_nc = st.text_input(
            "Periodo de Facturación (AAAA-MM)",
            value=obtener_mes_anterior(),
            key="nc_mes",
        )
      with c_nc2:
        concepto_nc = st.text_input(
            "Concepto (ej. Llave de portón, Reparación tubería)"
        )
        monto_nc = st.number_input(
            "Monto ($)", min_value=0.01, step=0.01, key="nc_monto"
        )

      btn_nc = st.form_submit_button("Asignar Cargo Individual", type="primary")

      if btn_nc and concepto_nc:
        try:
          with engine.connect() as conn:
            conn.execute(
                text("""
                                INSERT INTO cargos_individuales (apartamento, mes_anio, concepto, monto, fecha)
                                VALUES (:a, :m, :c, :mo, CURRENT_DATE)
                            """),
                {"a": apt_destino, "m": mes_nc, "c": concepto_nc, "mo": monto_nc},
            )
            conn.commit()
          st.success(
              f"Cargo no común cargado exitosamente a la unidad {apt_destino}."
          )
          st.rerun()
        except Exception as e:
          st.error(f"Error registrando cargo individual: {e}")

    st.write("---")
    st.subheader("📋 Cargos No Comunes Registrados")
    try:
      with engine.connect() as conn:
        df_cargos_nc = pd.read_sql(
            text(
                "SELECT id, apartamento, mes_anio, concepto, monto, fecha FROM"
                " cargos_individuales ORDER BY id DESC"
            ),
            conn,
        )
      if df_cargos_nc.empty:
        st.info("No hay cargos individuales registrados.")
      else:
        st.dataframe(df_cargos_nc, use_container_width=True)
    except Exception as e:
      st.error(f"Error listando cargos: {e}")

  with t3:
    st.subheader("⭐ Cargar Nueva Cuota Extraordinaria")
    with st.form("form_cuota_extra"):
      col_ce1, col_ce2 = st.columns(2)
      with col_ce1:
        concepto_ce = st.text_input(
            "Proyecto / Concepto (ej. Pintura Fachada, Reparación Ascensor)"
        )
      with col_ce2:
        monto_ce = st.number_input(
            "Monto Total del Proyecto ($)", min_value=0.01, step=0.01
        )

      btn_ce = st.form_submit_button(
          "Crear Cuota Extraordinaria (Pendiente)", type="primary"
      )

      if btn_ce and concepto_ce:
        try:
          with engine.connect() as conn:
            conn.execute(
                text("""
                                INSERT INTO cuotas_extraordinarias (concepto, monto_total, fecha_emision, estatus)
                                VALUES (:c, :m, CURRENT_DATE, 'Pendiente')
                            """),
                {"c": concepto_ce, "m": monto_ce},
            )
            conn.commit()
          st.success("Cuota extraordinaria creada.")
          st.rerun()
        except Exception as e:
          st.error(f"Error al guardar cuota extra: {e}")

    st.write("---")
    st.subheader("🔍 Previsualizar, Aprobar y Distribuir")
    try:
      with engine.connect() as conn:
        df_ce = pd.read_sql(
            text(
                "SELECT id, concepto, monto_total, fecha_emision, estatus FROM"
                " cuotas_extraordinarias ORDER BY id DESC"
            ),
            conn,
        )

      if df_ce.empty:
        st.info("No hay cuotas extraordinarias registradas.")
      else:
        mes_dist = st.text_input(
            "Periodo en el que se cobrará al aprobar (AAAA-MM):",
            value=obtener_mes_anterior(),
            key="ce_mes_dist",
        )

        for _, r_ce in df_ce.iterrows():
          c_det, c_act = st.columns([3, 2])
          with c_det:
            badge_st = (
                "🟡 Pendiente"
                if r_ce["estatus"] == "Pendiente"
                else "🟢 Aprobada y Distribuida"
            )
            st.markdown(
                f"**PROYECTO #{r_ce['id']}:** {r_ce['concepto']} | **Monto"
                f" Total:** ${float(r_ce['monto_total']):,.2f}"
            )
            st.caption(
                f"Fecha Emisión: {r_ce['fecha_emision']} | **Estatus:**"
                f" {badge_st}"
            )

          with c_act:
            if r_ce["estatus"] == "Pendiente":
              if st.button(
                  "✅ Aprobar y Distribuir",
                  key=f"app_ce_{r_ce['id']}",
                  type="primary",
              ):
                try:
                  with engine.connect() as conn:
                    unidades_res = conn.execute(
                        text("SELECT unidad, alicuota FROM unidades")
                    ).fetchall()
                    monto_tot = float(r_ce["monto_total"])
                    for u_row in unidades_res:
                      u_cod = u_row[0]
                      u_alic = float(u_row[1])
                      monto_apto = monto_tot * (u_alic / 100.0)

                      conn.execute(
                          text("""
                                        INSERT INTO cargos_individuales (apartamento, mes_anio, concepto, monto, fecha)
                                        VALUES (:a, :m, :c, :mo, CURRENT_DATE)
                                    """),
                          {
                              "a": u_cod,
                              "m": mes_dist,
                              "c": f"Cuota Extra: {r_ce['concepto']}",
                              "mo": monto_apto,
                          },
                      )

                    conn.execute(
                        text(
                            "UPDATE cuotas_extraordinarias SET estatus ="
                            " 'Aprobada' WHERE id = :id"
                        ),
                        {"id": r_ce["id"]},
                    )
                    conn.commit()

                  st.success(
                      f"🎉 Cuota distribuida exitosamente para el periodo"
                      f" {mes_dist}."
                  )
                  st.rerun()
                except Exception as e_dist:
                  st.error(f"Error al distribuir la cuota: {e_dist}")
    except Exception as e:
      st.error(f"Error cargando cuotas extraordinarias: {e}")

  with t4:
    st.subheader(
        "💱 Actualización Automática y Registro de Tasas de Cambio (BCV)"
    )
    st.info(
        f"ℹ️ La tasa actual obtenida automáticamente hoy es:"
        f" **{tasa_del_dia_auto:,.4f} VES/USD**."
    )

    with st.form("form_tasa"):
      c_t1, c_t2 = st.columns(2)
      with c_t1:
        fecha_tasa = st.date_input("Fecha de la Tasa", datetime.now())
      with c_t2:
        valor_tasa = st.number_input(
            "Valor del Dólar (VES / USD)",
            value=float(tasa_del_dia_auto),
            min_value=0.01,
            step=0.0001,
            format="%.4f",
        )

      btn_tasa = st.form_submit_button(
          "Guardar / Forzar Tasa para esta Fecha", type="primary"
      )

      if btn_tasa:
        try:
          with engine.connect() as conn:
            conn.execute(
                text("""
                                INSERT INTO tasa_cambio (fecha, tasa)
                                VALUES (:f, :t)
                                ON CONFLICT (fecha) DO UPDATE SET tasa = EXCLUDED.tasa
                            """),
                {"f": fecha_tasa, "t": valor_tasa},
            )
            conn.commit()
          st.success(
              f"✅ Tasa registrada correctamente para el {fecha_tasa}:"
              f" {valor_tasa:,.4f} VES/USD."
          )
          st.rerun()
        except Exception as e:
          st.error(f"Error guardando la tasa: {e}")

    st.write("---")
    st.subheader("📋 Historial de Tasas Registradas en Base de Datos")
    try:
      with engine.connect() as conn:
        df_tasas = pd.read_sql(
            text(
                "SELECT fecha, tasa FROM tasa_cambio ORDER BY fecha DESC LIMIT"
                " 30"
            ),
            conn,
        )
      if df_tasas.empty:
        st.info("No hay tasas de cambio registradas todavía.")
      else:
        st.dataframe(df_tasas, use_container_width=True)
    except Exception as e:
      st.error(f"Error cargando tasas: {e}")

  with t5:
    st.subheader("✅ Conciliación de Pagos Reportados")
    try:
      with engine.connect() as conn:
        df_pagos_rep = pd.read_sql(
            text("""
                        SELECT id, apartamento, tipo_pago, mes_anio, monto_original, moneda, 
                               tasa_aplicada, monto_usd, metodo_pago, referencia, fecha_pago, estatus 
                        FROM pagos_reportados 
                        ORDER BY id DESC
                    """),
            conn,
        )

      if df_pagos_rep.empty:
        st.info("No hay pagos reportados.")
      else:
        for _, r_p in df_pagos_rep.iterrows():
          c_info, c_btn = st.columns([3, 1])
          with c_info:
            if r_p["moneda"] == "VES":
              detalle_monto = (
                  f"Bs. {float(r_p['monto_original']):,.2f} (Tasa:"
                  f" {float(r_p['tasa_aplicada']):,.4f}) ➔ **Equivalente:"
                  f" ${float(r_p['monto_usd']):,.2f} USD**"
              )
            else:
              detalle_monto = f"**${float(r_p['monto_usd']):,.2f} USD**"

            st.markdown(
                f"**Apto:** {r_p['apartamento']} | **Tipo:**"
                f" {r_p['tipo_pago']} ({r_p['mes_anio']})"
            )
            st.markdown(f"Monto Pagado: {detalle_monto}")
            st.caption(
                f"Método: {r_p['metodo_pago']} | Ref: {r_p['referencia']} |"
                f" Fecha: {r_p['fecha_pago']} | **Estatus:** {r_p['estatus']}"
            )
          with c_btn:
            if r_p["estatus"] == "Pendiente":
              if st.button(
                  "Aprobar / Conciliar",
                  key=f"aprobar_pago_{r_p['id']}",
                  type="primary",
              ):
                with engine.connect() as conn:
                  conn.execute(
                      text(
                          "UPDATE pagos_reportados SET estatus = 'Aprobado'"
                          " WHERE id = :id"
                      ),
                      {"id": r_p["id"]},
                  )
                  conn.commit()
                st.success("Pago conciliado y aprobado con éxito.")
                st.rerun()
          st.markdown("<hr style='margin: 5px 0;'>", unsafe_allow_html=True)
    except Exception as e:
      st.error(f"Error al cargar pagos reportados: {e}")

  with t6:
    st.subheader("🏢 Configuración de Unidades y Alícuotas")
    try:
      df_unidades_act = obtener_unidades_df()
      suma_total_alicuotas = df_unidades_act["alicuota"].sum()

      if abs(suma_total_alicuotas - 100.0) < 0.01:
        st.success(
            f"✅ Suma total de alícuotas: {suma_total_alicuotas:.2f}%"
            " (Correcto)"
        )
      else:
        st.warning(
            f"⚠️ La suma actual de alícuotas es {suma_total_alicuotas:.2f}%."
            " Debe sumar exactamente 100%."
        )

      with st.form("form_editar_unidades"):
        edited_df = st.data_editor(
            df_unidades_act, use_container_width=True, num_rows="fixed"
        )
        btn_guardar_unidades = st.form_submit_button(
            "Guardar Cambios de Propietarios / Alícuotas", type="primary"
        )

        if btn_guardar_unidades:
          with engine.connect() as conn:
            for _, row in edited_df.iterrows():
              conn.execute(
                  text("""
                                    UPDATE unidades 
                                    SET alicuota = :a, propietario = :p, telefono = :t 
                                    WHERE unidad = :u
                                """),
                  {
                      "a": float(row["alicuota"]),
                      "p": str(row["propietario"]),
                      "t": str(row["telefono"]),
                      "u": str(row["unidad"]),
                  },
              )
            conn.commit()
          st.success("✅ Datos de las unidades actualizados correctamente.")
          st.rerun()
    except Exception as e:
      st.error(f"Error gestionando unidades: {e}")

    with t7:
      st.subheader("🚨 Recibos y Envíos a WhatsApp")
      mes_recibo_gral = st.text_input(
      "Periodo del Recibo (AAAA-MM):",
      value=obtener_mes_anterior(),
      key="input_mes_recibo_gen",
      )

  try:
    with engine.connect() as conn:
      # Consulta robusta asegurando nombres de columnas
      gastos_mes_df = pd.read_sql(
          text(
              "SELECT concepto, monto FROM gastos WHERE mes_anio = :m AND"
              " (estatus = 'Aprobado' OR estatus = 'APROBADO')"
          ),
          conn,
          params={"m": mes_recibo_gral},
      )
      total_gastos_comunes = (
          gastos_mes_df["monto"].sum() if not gastos_mes_df.empty else 0.0
      )

      unidades_df = pd.read_sql(
          text(
              "SELECT unidad, alicuota, propietario, telefono FROM unidades"
              " ORDER BY unidad ASC"
          ),
          conn,
      )

    # Diagnóstico visual rápido en pantalla para verificar que los gastos se leyeron
    if gastos_mes_df.empty:
      st.warning(
          f"⚠️ No se encontraron gastos aprobados para el periodo"
          f" {mes_recibo_gral}. Por eso el desglose sale vacío."
      )
    else:
      st.success(
          f"✅ Se cargaron {len(gastos_mes_df)} gastos comunes para el periodo"
          f" {mes_recibo_gral}."
      )

    st.markdown("### 👤 Recibos Individuales por Propietario (WhatsApp)")
    for _, u_row in unidades_df.iterrows():
      u_cod = u_row["unidad"]
      u_prop = u_row["propietario"]
      u_tel = u_row["telefono"]
      u_alic = float(u_row["alicuota"])
      u_alic_decimal = u_alic / 100.0

      cuota_comun_apt = float(total_gastos_comunes) * u_alic_decimal

      with engine.connect() as conn:
        cargos_apt = (
            conn.execute(
                text(
                    "SELECT SUM(monto) FROM cargos_individuales WHERE"
                    " apartamento = :u AND mes_anio = :m"
                ),
                {"u": u_cod, "m": mes_recibo_gral},
            ).scalar()
            or 0.0
        )

      total_apt = cuota_comun_apt + float(cargos_apt)

      with st.expander(f"🔹 Apt {u_cod} - {u_prop} (Total: ${total_apt:,.2f})"):
        # --- MENSAJE INDIVIDUAL DESGLOSADO ---
        msg_ind = f"  *{datos_ed['nombre']}*\n"
        msg_ind += f"  *AVISO DE COBRO - {mes_recibo_gral}*\n"
        msg_ind += f"Estimado(a) *{u_prop}* (Unidad {u_cod})\n"
        msg_ind += f"Alícuota: {u_alic:.1f}%\n"
        msg_ind += f"----------------------------------------\n"
        msg_ind += f"  *Desglose de Gastos Comunes:*\n"

        if not gastos_mes_df.empty:
          for _, g_row in gastos_mes_df.iterrows():
            # Asegurar manejo flexible de nombres de columnas por si vienen en mayúsculas/minúsculas
            g_concepto = (
                g_row["concepto"]
                if "concepto" in g_row
                else g_row.get("CONCEPTO", "Gasto")
            )
            g_monto_total = float(
                g_row["monto"] if "monto" in g_row else g_row.get("MONTO", 0.0)
            )
            g_monto_apto = g_monto_total * u_alic_decimal
            msg_ind += f"• {g_concepto}: ${g_monto_apto:,.2f}\n"
        else:
          msg_ind += "• (Sin gastos comunes registrados para este mes)\n"

        msg_ind += f"----------------------------------------\n"
        msg_ind += f"• Subtotal Cuota Común: ${cuota_comun_apt:,.2f}\n"

        if float(cargos_apt) > 0:
          msg_ind += (
              f"• Cargos Extras / No Comunes: ${float(cargos_apt):,.2f}\n"
          )

        msg_ind += f"----------------------------------------\n"
        msg_ind += f"  *TOTAL A PAGAR: ${total_apt:,.2f}*\n\n"
        msg_ind += (
            "Por favor realizar su pago y reportarlo en la plataforma. ¡Gracias!"
        )

        st.text_area(
            f"Mensaje WhatsApp Apt {u_cod}:",
            msg_ind,
            height=200,
            key=f"txt_msg_{u_cod}",
        )
        enlace_wa_apt = generar_enlace_whatsapp(u_tel, msg_ind)
        st.link_button(
            f"📲 Enviar WhatsApp a Apt {u_cod} ({u_tel or 'Sin teléfono'})",
            enlace_wa_apt,
            use_container_width=True,
        )

    st.write("---")
    st.markdown("### 📢 Recibo General para Grupo / Difusión")

    if not gastos_mes_df.empty:
      # --- CONSTRUCCIÓN DEL RECIBO GENERAL CON ALÍCUOTAS ---
      texto_ws = f"🏢 *{datos_ed['nombre']}*\n"
      texto_ws += f"📄 *RESUMEN DE GASTOS Y COBRANZA - {mes_recibo_gral}*\n\n"
      texto_ws += f"  *Gastos Comunes del Edificio:*\n"

      for _, g in gastos_mes_df.iterrows():
        g_concepto = (
            g["concepto"] if "concepto" in g else g.get("CONCEPTO", "Gasto")
        )
        g_monto_total = float(g["monto"] if "monto" in g else g.get("MONTO", 0.0))
        texto_ws += f"• {g_concepto}: ${g_monto_total:,.2f}\n"

      texto_ws += (
          f"----------------------------------------\n"
          f"💰 *TOTAL GASTOS COMUNES:* *${float(total_gastos_comunes):,.2f}*\n"
          f"----------------------------------------\n"
          f"  *Distribución por Apartamentos:*\n"
      )

      for _, u_row in unidades_df.iterrows():
        u_cod = u_row["unidad"]
        u_alic = float(u_row["alicuota"])
        cuota_apt_gral = float(total_gastos_comunes) * (u_alic / 100.0)
        texto_ws += f"• Apto {u_cod} ({u_alic:.1f}%): ${cuota_apt_gral:,.2f}\n"

      texto_ws += (
          f"----------------------------------------\n"
          "🙏 Por favor realizar sus pagos correspondientes y reportarlos en"
          " la plataforma. ¡Gracias!"
      )

      st.text_area(
          "Vista Previa Recibo General:",
          texto_ws,
          height=220,
          key="txt_msg_general_grupo",
      )

      enlace_wa_general = f"https://wa.me/?text={urllib.parse.quote(texto_ws)}"
      st.link_button(
          "📲 Abrir WhatsApp con el Recibo General Completo",
          enlace_wa_general,
          use_container_width=True,
      )

  except Exception as e:
    st.error(f"Error generando recibos: {e}")

  with t8:
    st.subheader("⚙️ Configuración General del Edificio")
    datos_actuales = obtener_datos_edificio()

    with st.form("form_config_edificio"):
      nombre_ed = st.text_input(
          "Nombre del Edificio / Residencias", value=datos_actuales["nombre"]
      )
      rif_ed = st.text_input("RIF", value=datos_actuales["rif"])
      dir_ed = st.text_area("Dirección", value=datos_actuales["direccion"])

      btn_act_ed = st.form_submit_button("Actualizar Datos", type="primary")

      if btn_act_ed:
        try:
          with engine.connect() as conn:
            conn.execute(
                text("""
                                UPDATE configuracion_edificio 
                                SET nombre = :n, rif = :r, direccion = :d 
                                WHERE id = 1
                            """),
                {"n": nombre_ed, "r": rif_ed, "d": dir_ed},
            )
            conn.commit()
          st.success("✅ Datos del edificio actualizados con éxito.")
          st.rerun()
        except Exception as e:
          st.error(f"Error actualizando configuración: {e}")
    with t9:
      st.subheader("💱 Conciliación de Pagos en Bolívares (Tasa BCV)")
      st.markdown(
      "Este módulo toma la tasa oficial registrada en el sistema para el periodo"
      " y compara las transferencias en bolívares de los propietarios."
      )

  # 1. Selector de Periodo
  mes_conciliacion = st.text_input(
      "Periodo a Conciliar (AAAA-MM):",
      value=obtener_mes_anterior(),
      key="input_mes_conciliacion",
  )

  try:
    with engine.connect() as conn:
      # Buscar la tasa de cambio registrada en la base de datos para este periodo o mes
      # (Ajusta el nombre de la tabla o columna si en tu app se llama diferente, ej: 'tasas_bcv' o 'configuracion')
      tasa_query = conn.execute(
          text(
              "SELECT tasa FROM tasas_cambio WHERE mes_anio = :m LIMIT 1"
          ),  # O la estructura que uses para guardar las tasas
          {"m": mes_conciliacion},
      ).scalar()

      # Si no encuentra una tasa específica para el mes, intentamos buscar la última o usamos un respaldo
      if not tasa_query:
        # Intento alternativo buscando en una tabla general o configuración si aplica
        tasa_query = 36.50  # Valor predeterminado por seguridad si no existe registro previo

      tasa_bcv = float(tasa_query)

      # Obtener gastos y unidades
      gastos_mes_df = pd.read_sql(
          text(
              "SELECT monto FROM gastos WHERE mes_anio = :m AND (estatus ="
              " 'Aprobado' OR estatus = 'APROBADO')"
          ),
          conn,
          params={"m": mes_conciliacion},
      )
      total_gastos_comunes = (
          gastos_mes_df["monto"].sum() if not gastos_mes_df.empty else 0.0
      )

      unidades_df = pd.read_sql(
          text(
              "SELECT unidad, alicuota, propietario FROM unidades ORDER BY"
              " unidad ASC"
          ),
          conn,
      )

    st.markdown("---")
    st.markdown(
        f"📊 **Gasto Común Total:** ${total_gastos_comunes:,.2f} USD | 💱 **Tasa"
        f" BCV del Sistema (Periodo {mes_conciliacion}):** Bs. {tasa_bcv:,.2f}"
    )
    st.markdown("---")

    # 2. Listado y Conciliación por Apartamento
    for _, u_row in unidades_df.iterrows():
      u_cod = u_row["unidad"]
      u_prop = u_row["propietario"]
      u_alic = float(u_row["alicuota"])
      u_alic_decimal = u_alic / 100.0

      cuota_comun_apt = float(total_gastos_comunes) * u_alic_decimal

      with engine.connect() as conn:
        cargos_apt = (
            conn.execute(
                text(
                    "SELECT SUM(monto) FROM cargos_individuales WHERE"
                    " apartamento = :u AND mes_anio = :m"
                ),
                {"u": u_cod, "m": mes_conciliacion},
            ).scalar()
            or 0.0
        )

      total_usd = cuota_comun_apt + float(cargos_apt)
      total_bs_teorico = total_usd * tasa_bcv

      with st.container():
        col_c1, col_c2, col_c3, col_c4 = st.columns([1, 2, 2, 2])

        col_c1.markdown(f"**Apto {u_cod}**")
        col_c2.markdown(f"{u_prop}")
        col_c3.markdown(
            f"Deuda: **${total_usd:,.2f} USD**<br>💱 Eq. Tasa Oficial: *Bs."
            f" {total_bs_teorico:,.2f}*",
            unsafe_allow_html=True,
        )

        with col_c4:
          estatus_actual = st.selectbox(
              f"Estatus Apto {u_cod}",
              ["🟡 Pendiente", "🟢 Conciliado (Aprobado)"],
              key=f"select_conciliacion_{u_cod}",
          )

        with st.expander(
            f"📝 Registrar / Verificar Pago en Bs - Apt {u_cod}"
        ):
          ref_pago = st.text_input(
              f"Nro. Referencia / Banco (Apt {u_cod}):",
              key=f"ref_pago_{u_cod}",
          )

          monto_reportado_bs = st.number_input(
              f"Monto real pagado en Bs (según comprobante):",
              min_value=0.0,
              value=total_bs_teorico,
              step=1.0,
              format="%.2f",
              key=f"monto_bs_{u_cod}",
          )

          if total_usd > 0 and monto_reportado_bs > 0:
            diferencia_bs = monto_reportado_bs - total_bs_teorico

            if abs(diferencia_bs) < 5.0:
              st.success(
                  "✅ El monto en Bs cubre exactamente la deuda con la tasa"
                  " oficial registrada."
              )
            elif monto_reportado_bs > total_bs_teorico:
              st.info(
                  f"🟢 El propietario pagó de más por un monto de Bs."
                  f" {diferencia_bs:,.2f}"
              )
            else:
              st.warning(
                  f"⚠️ El monto reportado es menor a la cuota. Faltan Bs."
                  f" {abs(diferencia_bs):,.2f} según la tasa oficial."
              )

        st.markdown("---")

  except Exception as e:
    st.error(
        f"Error en la conciliación (verifica que la tabla de tasas exista o"
        f" esté accesible): {e}"
    )
