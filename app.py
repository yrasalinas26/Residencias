import streamlit as st
from sqlalchemy import create_engine

# 1. Obtener la URL desde st.secrets
db_url = st.secrets["postgres"]["url"]

# 2. Corregir el prefijo si Supabase entrega "postgres://" en lugar de "postgresql://"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

# 3. Crear el motor de conexión con caché para evitar saturar el pooler
@st.cache_resource
def get_engine():
    return create_engine(
        db_url,
        pool_pre_ping=True,  # Verifica que la conexión siga viva antes de usarla
        pool_recycle=300     # Reorganiza conexiones cada 5 minutos
    )

try:
    engine = get_engine()
    # Prueba rápida de conexión
    with engine.connect() as conn:
        st.success("¡Conexión exitosa a Supabase!")
except Exception as e:
    st.error(f"Error al conectar con la base de datos: {e}")
