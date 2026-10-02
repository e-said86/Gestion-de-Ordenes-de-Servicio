import io
from datetime import date, timedelta
import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Gestión de Órdenes de Servicio",
    page_icon="📊",
    layout="wide",
)

# ============================================================
# REGLAS DEL ANÁLISIS
# ============================================================

CASOS = [
    "INSTALACION",
    "INSTALACION TV",
    "TRASLADO DE SERVICIO",
    "CLIENTE SIN SERVICIO",
    "CAMBIO DE PLAN",
    "OS POR REPARACIONES/INTERNAS",
]

CASO_REPARACIONES = "OS POR REPARACIONES/INTERNAS"
TIPO_OS_REPARACIONES = "OS POR REPARACIONES/INSTALACIONES INTERNAS"

PENDIENTES = {"PENDIENTE", "CONFIRMADA", "POSPUESTA", "INICIADA"}
REALIZADO = {"CERRADA"}
ANULADO = {"ANULADA"}

INTERVALOS = [
    "0–2 días", "3–5 días", "6–10 días", "11–15 días",
    "16–20 días", "21–25 días", "26–30 días", "Más de 30 días"
]

ALIASES = {
    "numero_os": ["ID Orden De Servicio", "Número OS", "Nro OS", "N° OS", "OS", "NumeroOS"],
    "fecha_creacion": [
        "Fecha Creacion", "Fecha Creación", "Fecha de Creacion",
        "Fecha de Creación", "Fecha Apertura", "Fecha de Apertura"
    ],
    "fecha_calendario": [
        "Fecha Calendario", "Fecha calendario", "FECHA CALENDARIO",
        "Calendario", "Fecha de Calendario"
    ],
    "estado": ["Estado", "ESTADO"],
    "sucursal": ["Sucursal", "SUCURSAL"],
    "caso": ["Caso Asociado", "Caso asociado", "Caso", "CASO ASOCIADO"],
    "localidad": ["Localidad", "Ciudad", "LOCALIDAD", "CIUDAD"],
    "tipo_os": ["Tipo de OS", "Tipo OS", "Tipo", "TIPO DE OS"],

        "fecha_cierre": [
        "Fecha Cierre", "Fecha Cierre OS", "Fecha de Cierre",
        "Fecha Cerrada", "Fecha Cerrado"
    ],
    "confeccionado_por": [
        "Confeccionada por", "Confeccionada por..", "Confeccionado por"
    ]
}


def norm(x):
    s = str(x).strip().lower()
    repl = str.maketrans("áéíóúüñ", "aeiouun")
    s = s.translate(repl)
    return " ".join(s.replace("_", " ").replace("-", " ").split())

def find_col(df, aliases):
    m = {norm(c): c for c in df.columns}
    for a in aliases:
        if norm(a) in m:
            return m[norm(a)]
    for c in df.columns:
        nc = norm(c)
        for a in aliases:
            na = norm(a)
            if na in nc or nc in na:
                return c
    return None

def load_file(uploaded):
    raw = uploaded.getvalue()
    name = uploaded.name.lower()
    if name.endswith(".csv"):
        for enc in ["utf-8-sig", "cp1252", "latin1"]:
            for sep in [";", ",", "\t"]:
                try:
                    df = pd.read_csv(io.BytesIO(raw), encoding=enc, sep=sep)
                    if df.shape[1] > 1:
                        return df
                except Exception:
                    pass
        raise ValueError("No se pudo leer el CSV.")
    return pd.read_excel(io.BytesIO(raw))

def age_bucket(d):
    if pd.isna(d):
        return "Sin fecha"
    d = int(d)
    if d <= 2: return "0–2 días"
    if d <= 5: return "3–5 días"
    if d <= 10: return "6–10 días"
    if d <= 15: return "11–15 días"
    if d <= 20: return "16–20 días"
    if d <= 25: return "21–25 días"
    if d <= 30: return "26–30 días"
    return "Más de 30 días"

def fmt(n):
    return f"{int(n):,}".replace(",", ".")

def safe_div(a, b):
    return a / b if b else 0

st.title("📊 Análisis y Gestión de Órdenes de Servicio")
st.caption("Análisis de trabajo real + planificación de regularización de cuadrillas")

# ============================================================
# CARGA
# ============================================================

with st.sidebar:
    st.header("📁 Archivo")
    uploaded = st.file_uploader(
        "Cargar Excel o CSV",
        type=["xlsx", "xls", "csv"]
    )

if uploaded is None:
    st.info("Cargá el Excel/CSV de órdenes de servicio para comenzar.")
    st.markdown("""
### Criterio del análisis

**Casos considerados:**
- INSTALACION
- INSTALACION TV
- TRASLADO DE SERVICIO
- CLIENTE SIN SERVICIO
- CAMBIO DE PLAN
- OS POR REPARACIONES/INTERNAS (identificado desde Tipo de OS)

**Estados:**
- Realizado = CERRADA
- Falta hacer = PENDIENTE + CONFIRMADA + POSPUESTA + INICIADA
- Anulada = ANULADA
- Otros estados = se identifican por separado

**Antigüedad:** desde Fecha Creación hasta la fecha final del período.

EQUIPO PASADO A STOCK y otros casos no incluidos quedan fuera del trabajo técnico.
""")
    st.stop()

try:
    raw = load_file(uploaded)
    if raw.columns.duplicated().any():
        cols_unicos = []
        vistos = {}
        for c in raw.columns:
            nombre = str(c)
            vistos[nombre] = vistos.get(nombre, 0) + 1
            cols_unicos.append(nombre if vistos[nombre] == 1 else f"{nombre}__dup{vistos[nombre]}")
        raw.columns = cols_unicos
except Exception as e:
    st.error(str(e))
    st.stop()

# Detect columns
col = {k: find_col(raw, v) for k, v in ALIASES.items()}

missing = [k for k in ["fecha_creacion", "estado", "sucursal", "caso"] if col[k] is None]
if missing:
    st.error("No se pudieron identificar: " + ", ".join(missing))
    st.write("Columnas del archivo:")
    st.write(list(raw.columns))
    st.stop()

df = raw.copy()
df["_estado"] = df[col["estado"]].astype(str).str.strip().str.upper()
df["_caso"] = df[col["caso"]].astype(str).str.strip().str.upper()

# OS por Reparaciones/instalaciones internas se identifica por TIPO DE OS,
# no por la columna Caso Asociado. Para el análisis se presenta como una
# categoría adicional dentro de "Caso asociado".
if col.get("tipo_os"):
    # Normalizamos el valor de Tipo de OS para que la detección no dependa
    # de mayúsculas/minúsculas, espacios, guiones o acentos.
    _tipo_os_norm = (
        df[col["tipo_os"]]
        .fillna("")
        .astype(str)
        .map(norm)
    )
    _tipo_reparaciones_norm = norm(TIPO_OS_REPARACIONES)
    df.loc[
        _tipo_os_norm == _tipo_reparaciones_norm,
        "_caso"
    ] = CASO_REPARACIONES

df["_sucursal"] = df[col["sucursal"]].astype(str).str.strip().str.upper()
df["_fecha"] = pd.to_datetime(df[col["fecha_creacion"]], errors="coerce", dayfirst=True)

if col["fecha_cierre"]:
    df["_fecha_cierre"] = pd.to_datetime(df[col["fecha_cierre"]], errors="coerce", dayfirst=True)
else:
    df["_fecha_cierre"] = pd.NaT

valid_dates = df["_fecha"].dropna()
if valid_dates.empty:
    st.error("No hay fechas válidas en la columna de creación.")
    st.stop()

min_date = valid_dates.min().date()
max_date = valid_dates.max().date()

sucs = sorted([str(x) for x in df["_sucursal"].unique() if str(x) not in ["", "nan", "NAN", "None"]])
default_suc = "CONCORDIA" if "CONCORDIA" in sucs else sucs[0]

with st.sidebar:
    st.header("📅 Período analizado")
    # Por defecto: desde el primer día del mes anteúltimo al último mes
    # disponible en el archivo, hasta la fecha más actual disponible.
    ultimo_mes = pd.Timestamp(max_date).replace(day=1)
    mes_anteultimo = (ultimo_mes - pd.DateOffset(months=1)).date()
    desde_default = max(min_date, mes_anteultimo)

    fecha_desde = st.date_input(
        "Desde",
        value=desde_default,
        min_value=min_date,
        max_value=max_date
    )
    fecha_hasta = st.date_input(
        "Hasta",
        value=max_date,
        min_value=min_date,
        max_value=max_date
    )

    if fecha_desde > fecha_hasta:
        st.error("La fecha Desde no puede ser posterior a Hasta.")
        st.stop()

    st.header("📍 Filtros")
    sucursal = st.multiselect(
        "Sucursal",
        sucs,
        default=[default_suc] if default_suc in sucs else sucs
    )

    casos = st.multiselect(
        "Caso asociado",
        CASOS,
        default=CASOS
    )

# ============================================================
# BASE AL FINAL DEL PERÍODO
# ============================================================

start = pd.Timestamp(fecha_desde).normalize()
end = pd.Timestamp(fecha_hasta).normalize()
end_exclusive = end + pd.Timedelta(days=1)

if not sucursal:
    st.warning("Seleccioná al menos una sucursal.")
    st.stop()

base = df[
    (df["_sucursal"].isin(sucursal)) &
    (df["_fecha"].notna()) &
    (df["_fecha"] >= start) &
    (df["_fecha"] < end_exclusive) &
    (df["_caso"].isin(casos))
].copy()

base["antiguedad"] = (
    pd.Timestamp(fecha_hasta) - base["_fecha"].dt.normalize()
).dt.days
base["situacion"] = base["_estado"].apply(
    lambda x:
        "Realizado" if x in REALIZADO else
        "Falta hacer" if x in PENDIENTES else
        "Anulado" if x in ANULADO else
        "Otro estado"
)

realizados = base[base["situacion"] == "Realizado"].copy()
pendientes = base[base["situacion"] == "Falta hacer"].copy()
anulados = base[base["situacion"] == "Anulado"].copy()
otros = base[base["situacion"] == "Otro estado"].copy()

pendientes["intervalo"] = pendientes["antiguedad"].apply(age_bucket)

# OS creadas durante el período: sirve para medir ingreso de nuevas órdenes
entradas_periodo = base[
    (base["_fecha"] >= start) & (base["_fecha"] < end_exclusive)
].copy()

# Si existe fecha de cierre, calculamos cierres dentro del período como indicador adicional
if col["fecha_cierre"]:
    cierres_periodo = base[
        (base["_fecha_cierre"].notna()) &
        (base["_fecha_cierre"] >= start) &
        (base["_fecha_cierre"] <= end) &
        (base["_estado"].isin(REALIZADO))
    ].copy()
else:
    cierres_periodo = pd.DataFrame()

# ============================================================
# CABECERA
# ============================================================

st.info(
    f"**Período analizado:** {fecha_desde.strftime('%d/%m/%Y')} al "
    f"{fecha_hasta.strftime('%d/%m/%Y')} | **Sucursal:** {', '.join(sucursal)}"
)

tabs = st.tabs([
    "📊 Situación actual",
    "⏳ Antigüedad",
    "📝 Detalle",
    "👷‍♂️ Planificación de cuadrillas",
    "👷‍♂️ Productividad",
    "📈 Proyección día a día",
    "📥 Exportar",
    
])

# ============================================================
# TAB 1
# ============================================================

with tabs[0]:
    st.subheader("Situación del trabajo técnico al final del período")

    a,b,c,d,e = st.columns(5)
    a.metric("✅ Realizado", fmt(len(realizados)))
    b.metric("🔴 Falta hacer", fmt(len(pendientes)))
    c.metric("❌ Anulado", fmt(len(anulados)))
    d.metric("⚠️ Otros estados", fmt(len(otros)))
    e.metric("📥 Entradas en período", fmt(len(entradas_periodo)))

    tabla = pd.crosstab(base["_caso"], base["situacion"])
    for x in ["Realizado", "Falta hacer", "Anulado", "Otro estado"]:
        if x not in tabla.columns:
            tabla[x] = 0
    tabla["Total"] = tabla.sum(axis=1)
    tabla = tabla.reset_index().rename(columns={"_caso": "Caso"})
    st.dataframe(
        tabla[["Caso","Realizado","Falta hacer","Anulado","Otro estado","Total"]],
        use_container_width=True, hide_index=True
    )

    st.subheader("Comparación visual")
    graf = tabla.set_index("Caso")[["Realizado","Falta hacer"]]
    st.bar_chart(graf)

    if col["fecha_cierre"]:
        st.subheader("Cierres dentro del período")
        st.metric("OS cerradas dentro del período", fmt(len(cierres_periodo)))

# ============================================================
# TAB 2
# ============================================================

with tabs[1]:
    st.subheader("🔴 Pendientes por antigüedad")

    cruz = pd.crosstab(pendientes["intervalo"], pendientes["_caso"])
    cruz = cruz.reindex(INTERVALOS, fill_value=0)
    for caso in casos:
        if caso not in cruz.columns:
            cruz[caso] = 0
    cruz = cruz[casos]
    cruz["TOTAL"] = cruz.sum(axis=1)

    total = cruz.sum(axis=0).to_frame().T
    total.index = ["TOTAL"]
    cruz_final = pd.concat([cruz, total])

    st.dataframe(cruz_final, use_container_width=True)

    st.bar_chart(cruz["TOTAL"])

    x1,x2,x3 = st.columns(3)
    x1.metric("> 30 días", fmt((pendientes["antiguedad"] > 30).sum()))
    x2.metric("11–30 días", fmt(((pendientes["antiguedad"] >= 11) & (pendientes["antiguedad"] <= 30)).sum()))
    x3.metric("0–10 días", fmt((pendientes["antiguedad"] <= 10).sum()))

# ============================================================
# TAB 3
# ============================================================

with tabs[2]:
    st.subheader("🔎 Detalle de órdenes pendientes")

    if pendientes.empty:
        st.success("No hay pendientes según los criterios seleccionados.")
    else:
        filtro_caso = st.selectbox("Ver caso", ["TODOS"] + casos)
        detalle = pendientes.copy()
        if filtro_caso != "TODOS":
            detalle = detalle[detalle["_caso"] == filtro_caso]

        cols_out = []
        if col["numero_os"]: cols_out.append(col["numero_os"])
        cols_out += [col["fecha_creacion"], col["estado"], col["sucursal"], col["caso"]]
        if col["localidad"]: cols_out.append(col["localidad"])
        if col["tipo_os"]: cols_out.append(col["tipo_os"])
        cols_out = list(dict.fromkeys(cols_out))

        out = detalle[cols_out].copy()
        out["Antigüedad días"] = detalle["antiguedad"].values
        out["Intervalo"] = detalle["intervalo"].values
        st.dataframe(
            out.sort_values("Antigüedad días", ascending=False),
            use_container_width=True, hide_index=True
        )

# ============================================================
# TAB 4 - PLANIFICACIÓN
# ============================================================

with tabs[3]:
    st.subheader("👷 Planificación de cuadrillas")
    st.write(
        "Esta sección transforma la cartera pendiente en un plan de regularización. "
        "Los parámetros son editables para probar distintos escenarios."
    )

    q1,q2,q3,q4 = st.columns(4)
    with q1:
        cuadrillas = st.number_input("Cantidad de cuadrillas", min_value=1, max_value=50, value=5)
    with q2:
        trabajos_dia = st.number_input(
            "Trabajos por cuadrilla/día", min_value=1, max_value=30, value=5
        )
    with q3:
        dias_trabajo_semana = st.number_input(
            "Días de trabajo por semana", min_value=1, max_value=7, value=6
        )
    with q4:
        ingreso_diario = st.number_input(
            "Nuevas OS por día", min_value=0.0, max_value=10000.0, value=0.0, step=1.0
        )

    capacidad = cuadrillas * trabajos_dia
    saldo_neto = capacidad - ingreso_diario

    st.markdown("### Capacidad")
    c1,c2,c3 = st.columns(3)
    c1.metric("Cuadrillas", cuadrillas)
    c2.metric("Capacidad diaria", fmt(capacidad))
    c3.metric("Saldo diario de reducción", fmt(saldo_neto))

    if ingreso_diario >= capacidad:
        st.warning(
            "⚠️ Con estos parámetros las nuevas OS igualan o superan la capacidad. "
            "El atraso no se elimina."
        )
    else:
        pendientes_n = len(pendientes)
        dias_teoricos = pendientes_n / saldo_neto if saldo_neto > 0 else 0
        st.success(
            f"Con {cuadrillas} cuadrillas a {trabajos_dia} trabajos/día, "
            f"y {ingreso_diario:g} nuevas OS/día, el atraso de {fmt(pendientes_n)} "
            f"se eliminaría en aproximadamente **{dias_teoricos:.1f} días operativos**."
        )

    st.markdown("### Escenarios")
    escenarios = []
    for q in [4,5,6]:
        cap = q * trabajos_dia
        net = cap - ingreso_diario
        dias = pendientes_n / net if net > 0 else None
        escenarios.append({
            "Cuadrillas": q,
            "Capacidad/día": cap,
            "Ingreso/día": ingreso_diario,
            "Reducción neta/día": max(net, 0),
            "Días para eliminar atraso": round(dias, 1) if dias is not None else "No se elimina"
        })
    st.dataframe(pd.DataFrame(escenarios), use_container_width=True, hide_index=True)

    st.markdown("### Objetivos de antigüedad")
    objetivos = []
    for limite in [30, 10, 7, 5, 2]:
        cantidad = int((pendientes["antiguedad"] > limite).sum())
        net = saldo_neto
        dias = cantidad / net if net > 0 else None
        objetivos.append({
            "Objetivo": f"≤ {limite} días",
            "OS que deben atacarse": cantidad,
            "Días operativos estimados": round(dias,1) if dias is not None else "No se elimina"
        })
    st.dataframe(pd.DataFrame(objetivos), use_container_width=True, hide_index=True)

    st.caption(
        "La proyección es un escenario matemático. No asigna una productividad diferente "
        "por tipo de trabajo ni considera feriados, ausencias, zonas, tiempos de viaje o "
        "capacidad diferenciada, salvo que se incorporen como parámetros."
    )


# =========================================================================
# TAB 5 - PRODUCTIVIDAD
# =========================================================================
with tabs[4]:
    st.subheader("👤 Productividad por Personal")
    st.write(
        "Medición de órdenes según la columna 'Fecha Calendario', "
        "independiente del período general de la barra lateral."
    )

    # ---------------------------------------------------------
    # Columnas reales detectadas
    # ---------------------------------------------------------
    col_usuario = col.get("confeccionado_por") or find_col(
        df, ["Confeccionada Por", "Confeccionada por", "Confeccionado Por"]
    )
    col_fecha_medicion = col.get("fecha_calendario") or find_col(
        df, ["Fecha Calendario", "Calendario", "Fecha de Calendario"]
    )
    col_estado_prod = col.get("estado") or find_col(df, ["Estado", "ESTADO"])
    col_sucursal_prod = col.get("sucursal") or find_col(df, ["Sucursal", "SUCURSAL"])

    if not col_fecha_medicion:
        st.error(
            "No se encontró la columna 'Fecha Calendario'. "
            "Columnas detectadas: " + ", ".join(map(str, df.columns))
        )
        st.stop()

    if not col_usuario:
        st.error("No se encontró la columna 'Confeccionada Por'.")
        st.stop()

    if not col_estado_prod:
        st.error("No se encontró la columna 'Estado'.")
        st.stop()

    if not col_sucursal_prod:
        st.error("No se encontró la columna 'Sucursal'.")
        st.stop()

    # ---------------------------------------------------------
    # Preparar base exclusiva de productividad
    # ---------------------------------------------------------
    df_prod_base = df.copy()

    df_prod_base["_fecha_productividad"] = pd.to_datetime(
        df_prod_base[col_fecha_medicion],
        errors="coerce",
        dayfirst=True
    )

    df_prod_base["_usuario_productividad"] = (
        df_prod_base[col_usuario]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    df_prod_base["_estado_productividad"] = (
        df_prod_base[col_estado_prod]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    df_prod_base["_sucursal_productividad"] = (
        df_prod_base[col_sucursal_prod]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.upper()
    )

    fechas_prod_validas = df_prod_base["_fecha_productividad"].dropna()

    if fechas_prod_validas.empty:
        st.error("La columna 'Fecha Calendario' no contiene fechas válidas.")
        st.stop()

    min_prod_date = fechas_prod_validas.min().date()
    max_prod_date = fechas_prod_validas.max().date()

    # ---------------------------------------------------------
    # Selector de período PROPIO de Productividad
    # ---------------------------------------------------------
    # La productividad tiene su propio período y NO depende del período general.
    st.markdown("### 📅 Período de productividad")

    tipo_periodo = st.radio(
        "Seleccionar período",
        ["Día", "Semana", "Mes", "Período personalizado"],
        horizontal=True,
        key="productividad_tipo_periodo"
    )

    fecha_default_prod = (
        fecha_hasta if min_prod_date <= fecha_hasta <= max_prod_date else max_prod_date
    )

    if tipo_periodo == "Día":
        fecha_elegida = st.date_input(
            "Elegir día", value=fecha_default_prod,
            min_value=min_prod_date, max_value=max_prod_date,
            key="productividad_dia"
        )
        prod_desde = fecha_elegida
        prod_hasta = fecha_elegida

    elif tipo_periodo == "Semana":
        fecha_elegida = st.date_input(
            "Elegir cualquier día de la semana", value=fecha_default_prod,
            min_value=min_prod_date, max_value=max_prod_date,
            key="productividad_semana"
        )
        prod_desde = fecha_elegida - timedelta(days=fecha_elegida.weekday())
        prod_hasta = prod_desde + timedelta(days=6)
        st.info(
            f"Semana seleccionada: **{prod_desde.strftime('%d/%m/%Y')}** "
            f"al **{prod_hasta.strftime('%d/%m/%Y')}**"
        )

    elif tipo_periodo == "Mes":
        fecha_elegida = st.date_input(
            "Elegir cualquier día del mes", value=fecha_default_prod,
            min_value=min_prod_date, max_value=max_prod_date,
            key="productividad_mes"
        )
        prod_desde = fecha_elegida.replace(day=1)
        siguiente_mes = pd.Timestamp(prod_desde) + pd.offsets.MonthBegin(1)
        prod_hasta = (siguiente_mes - pd.Timedelta(days=1)).date()
        st.info(
            f"Mes seleccionado: **{fecha_elegida.strftime('%m/%Y')}** "
            f"({prod_desde.strftime('%d/%m/%Y')} al {prod_hasta.strftime('%d/%m/%Y')})"
        )

    else:
        pc1, pc2 = st.columns(2)
        with pc1:
            prod_desde = st.date_input(
                "Desde",
                value=(fecha_desde if min_prod_date <= fecha_desde <= max_prod_date else min_prod_date),
                min_value=min_prod_date, max_value=max_prod_date,
                key="productividad_desde"
            )
        with pc2:
            prod_hasta = st.date_input(
                "Hasta",
                value=(fecha_hasta if min_prod_date <= fecha_hasta <= max_prod_date else max_prod_date),
                min_value=min_prod_date, max_value=max_prod_date,
                key="productividad_hasta"
            )
        if prod_desde > prod_hasta:
            st.error("La fecha Desde no puede ser posterior a Hasta.")
            st.stop()

    st.info(
        f"La productividad se calcula sobre el período seleccionado: "
        f"**{prod_desde.strftime('%d/%m/%Y')} al {prod_hasta.strftime('%d/%m/%Y')}**. "
        f"Se utiliza **{col_fecha_medicion}** y el estado **CERRADA**."
    )

    # ---------------------------------------------------------
    # Límites correctos: incluye TODO el último día aunque tenga hora
    # ---------------------------------------------------------
    fecha_inicio_prod = pd.Timestamp(prod_desde).normalize()
    fecha_fin_exclusiva_prod = (
        pd.Timestamp(prod_hasta).normalize() + pd.Timedelta(days=1)
    )

    # ---------------------------------------------------------
    # Filtro de Productividad
    # IMPORTANTE: NO usa start/end del período general.
    # Usa exclusivamente prod_desde/prod_hasta.
    # ---------------------------------------------------------
    criterio_prod = (
        df_prod_base["_fecha_productividad"].notna()
        & (df_prod_base["_fecha_productividad"] >= fecha_inicio_prod)
        & (df_prod_base["_fecha_productividad"] < fecha_fin_exclusiva_prod)
    )

    if sucursal:
        sucursales_norm = [str(x).strip().upper() for x in sucursal]
        criterio_prod = criterio_prod & (
            df_prod_base["_sucursal_productividad"].isin(sucursales_norm)
        )

    criterio_prod = criterio_prod & df_prod_base["_caso"].isin(casos)
    df_prod = df_prod_base.loc[criterio_prod].copy()

    # ---------------------------------------------------------
    # Conteo por operador
    # ---------------------------------------------------------
    # Productividad = órdenes CERRADAS por Fecha Calendario.
    df_prod_cerradas = df_prod[
        df_prod["_estado_productividad"] == "CERRADA"
    ].copy()

    # El usuario debe existir.
    df_prod_cerradas = df_prod_cerradas[
        df_prod_cerradas["_usuario_productividad"].ne("")
        & df_prod_cerradas["_usuario_productividad"].ne("NAN")
        & df_prod_cerradas["_usuario_productividad"].ne("NONE")
    ].copy()

    # Total de órdenes y cerradas por operador.
    totales_por_usuario = (
        df_prod.groupby("_usuario_productividad")
        .size()
        .reset_index(name="Total Órdenes")
    )

    cerradas_por_usuario = (
        df_prod_cerradas.groupby("_usuario_productividad")
        .size()
        .reset_index(name="Órdenes Cerradas")
    )

    prod_data = totales_por_usuario.merge(
        cerradas_por_usuario,
        on="_usuario_productividad",
        how="left"
    )

    prod_data["Órdenes Cerradas"] = (
        prod_data["Órdenes Cerradas"].fillna(0).astype(int)
    )

    prod_data["Efectividad Cierre (%)"] = (
        prod_data["Órdenes Cerradas"]
        .div(prod_data["Total Órdenes"].replace(0, pd.NA))
        .fillna(0)
        .mul(100)
        .round(1)
    )

    prod_data = prod_data.rename(
        columns={"_usuario_productividad": "Confeccionada Por"}
    )

    prod_data = prod_data.sort_values(
        by="Órdenes Cerradas",
        ascending=False
    )

    # ---------------------------------------------------------
    # Indicadores generales
    # ---------------------------------------------------------
    total_periodo = len(df_prod)
    total_cerradas = len(df_prod_cerradas)
    operadores_activos = len(prod_data)
    dias_periodo = (prod_hasta - prod_desde).days + 1
    promedio_dia = total_cerradas / dias_periodo if dias_periodo else 0

    st.markdown("---")
    st.info(
        f"🔎 **Productividad:** {prod_desde.strftime('%d/%m/%Y')} al "
        f"{prod_hasta.strftime('%d/%m/%Y')} | **Sucursal:** {sucursal} | "
        f"**Fecha utilizada:** {col_fecha_medicion}"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Órdenes del período", fmt(total_periodo))
    c2.metric("Órdenes cerradas", fmt(total_cerradas))
    c3.metric("Operadores activos", fmt(operadores_activos))
    c4.metric("Promedio cierres/día", f"{promedio_dia:.1f}")

    # ---------------------------------------------------------
    # Rendimiento detallado
    # ---------------------------------------------------------
    st.markdown("### 📋 Rendimiento detallado")

    if prod_data.empty:
        st.warning("No se encontraron órdenes cerradas para el período seleccionado.")
    else:
        grafico_data = prod_data.set_index("Confeccionada Por")[
            ["Total Órdenes", "Órdenes Cerradas"]
        ]
        st.bar_chart(grafico_data)
        st.dataframe(
            prod_data,
            use_container_width=True,
            hide_index=True
        )

        st.success(
            f"TOTAL DE ÓRDENES CERRADAS: **{fmt(total_cerradas)}**"
        )

    # ---------------------------------------------------------
    # Productividad día por día
    # ---------------------------------------------------------
    st.markdown("### 📅 Productividad día por día")

    rango_dias = pd.date_range(
        fecha_inicio_prod,
        fecha_fin_exclusiva_prod - pd.Timedelta(days=1),
        freq="D"
    )

    if df_prod_cerradas.empty:
        diario = pd.DataFrame({"Fecha": rango_dias, "Órdenes Cerradas": [0] * len(rango_dias)})
        st.info("No hay cierres para mostrar día por día en el período seleccionado.")
    else:
        df_prod_cerradas["_dia"] = df_prod_cerradas["_fecha_productividad"].dt.normalize()
        conteos_diarios = df_prod_cerradas.groupby("_dia").size()
        diario = pd.DataFrame({"Fecha": rango_dias})
        diario["Órdenes Cerradas"] = diario["Fecha"].map(conteos_diarios).fillna(0).astype(int)

    diario_mostrar = diario.copy()
    diario_mostrar["Fecha"] = diario_mostrar["Fecha"].dt.strftime("%d/%m/%Y")
    st.dataframe(diario_mostrar, use_container_width=True, hide_index=True)
    st.bar_chart(diario.set_index("Fecha")["Órdenes Cerradas"])

    dia_max = diario.loc[diario["Órdenes Cerradas"].idxmax()] if not diario.empty else None
    dias_con_cierre = int((diario["Órdenes Cerradas"] > 0).sum()) if not diario.empty else 0
    d1, d2, d3 = st.columns(3)
    d1.metric("Días con cierres", fmt(dias_con_cierre))
    d2.metric("Promedio en días con cierre", f"{safe_div(total_cerradas, dias_con_cierre):.1f}")
    d3.metric("Mejor día", f"{int(dia_max['Órdenes Cerradas'])} OS · {dia_max['Fecha'].strftime('%d/%m/%Y')}" if dia_max is not None else "0")

    # ---------------------------------------------------------
    # Matriz operador / día
    # ---------------------------------------------------------
    st.markdown("### 👤📅 Cierres por operador por día")

    if df_prod_cerradas.empty:
        st.info("No hay datos para construir la matriz.")
    else:
        matriz = pd.pivot_table(
            df_prod_cerradas,
            index="_usuario_productividad",
            columns="_dia",
            values="_estado_productividad",
            aggfunc="count",
            fill_value=0
        )

        matriz = matriz.reindex(
            columns=rango_dias,
            fill_value=0
        )

        matriz["TOTAL"] = matriz.sum(axis=1)
        matriz = matriz.sort_values("TOTAL", ascending=False)
        matriz = matriz.reset_index()
        matriz = matriz.rename(
            columns={"_usuario_productividad": "Confeccionada Por"}
        )

        nuevas_columnas = []
        for c in matriz.columns:
            if c == "Confeccionada Por" or c == "TOTAL":
                nuevas_columnas.append(c)
            else:
                nuevas_columnas.append(pd.Timestamp(c).strftime("%d/%m"))
        matriz.columns = nuevas_columnas

        st.dataframe(
            matriz,
            use_container_width=True,
            hide_index=True
        )

    # ---------------------------------------------------------
    # Casos de trabajo cerrados por operador
    # ---------------------------------------------------------
    st.markdown("### 🧰 Casos de trabajo cerrados por operador")

    if df_prod_cerradas.empty:
        st.info("No hay casos de trabajo cerrados para el período seleccionado.")
    else:
        # Usamos exclusivamente las columnas internas de Productividad,
        # evitando depender de nombres reales duplicados del archivo.
        df_casos_cerrados = df_prod_cerradas.copy()

        # Reforzar aquí la clasificación de reparaciones desde Tipo de OS.
        # Esto garantiza que esas OS se cuenten aunque Caso Asociado venga
        # vacío o con una variante de texto en el archivo original.
        if col.get("tipo_os") and col["tipo_os"] in df_casos_cerrados.columns:
            _tipo_prod_norm = (
                df_casos_cerrados[col["tipo_os"]]
                .fillna("")
                .astype(str)
                .map(norm)
            )
            df_casos_cerrados.loc[
                _tipo_prod_norm == norm(TIPO_OS_REPARACIONES),
                "_caso"
            ] = CASO_REPARACIONES

        # Usar la categoría interna _caso ya normalizada al cargar el archivo.
        # Esto es importante porque allí se incorporan las OS por
        # Reparaciones/Instalaciones Internas detectadas desde "Tipo de OS".
        # Si se vuelve a leer col["caso"], esas órdenes pueden tener el
        # "Caso Asociado" vacío y quedan afuera del conteo.
        df_casos_cerrados["_caso_productividad"] = (
            df_casos_cerrados["_caso"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.upper()
        )

        # Solo los tipos de casos definidos para el análisis.
        df_casos_cerrados = df_casos_cerrados[
            df_casos_cerrados["_caso_productividad"].isin(CASOS)
        ].copy()

        if df_casos_cerrados.empty:
            st.info(
                "No hay casos de trabajo de los tipos seleccionados "
                "para el período de productividad."
            )
        else:
            casos_operador = pd.crosstab(
                df_casos_cerrados["_usuario_productividad"],
                df_casos_cerrados["_caso_productividad"]
            )

            # Asegurar que aparezcan siempre las columnas de CASOS
            # en el mismo orden, aunque algún caso tenga 0.
            casos_operador = casos_operador.reindex(
                columns=CASOS,
                fill_value=0
            )

            casos_operador["TOTAL"] = casos_operador.sum(axis=1)

            casos_operador = casos_operador.sort_values(
                "TOTAL",
                ascending=False
            ).reset_index()

            casos_operador = casos_operador.rename(
                columns={
                    "_usuario_productividad": "Confeccionada Por"
                }
            )

            st.dataframe(
                casos_operador,
                use_container_width=True,
                hide_index=True
            )

            st.markdown("### 🔎 Cierres detallados por operador, día y caso")
            detalle_operador_dia_caso = (
                df_casos_cerrados
                .groupby(["_usuario_productividad", "_dia", "_caso_productividad"])
                .size()
                .reset_index(name="OS Cerradas")
                .rename(columns={
                    "_usuario_productividad": "Confeccionada Por",
                    "_dia": "Fecha",
                    "_caso_productividad": "Caso asociado"
                })
                .sort_values(["Fecha", "Confeccionada Por", "Caso asociado"])
            )
            detalle_operador_dia_caso["Fecha"] = detalle_operador_dia_caso["Fecha"].dt.strftime("%d/%m/%Y")
            st.dataframe(detalle_operador_dia_caso, use_container_width=True, hide_index=True)

            st.markdown("### 📊 Distribución de cierres por operador y caso")
            grafico_casos = casos_operador.set_index("Confeccionada Por")[CASOS]
            st.bar_chart(grafico_casos)

    # ---------------------------------------------------------
    # Control técnico específico de Productividad
    # ---------------------------------------------------------
    with st.expander("🔧 Control de Productividad"):
        st.write("Columna de fecha utilizada:", col_fecha_medicion)
        st.write("Columna de usuario utilizada:", col_usuario)
        st.write("Columna de estado utilizada:", col_estado_prod)
        st.write("Columna de sucursal utilizada:", col_sucursal_prod)
        st.write("Fecha desde:", prod_desde)
        st.write("Fecha hasta:", prod_hasta)
        st.write("Inicio real del filtro:", fecha_inicio_prod)
        st.write("Fin exclusivo real del filtro:", fecha_fin_exclusiva_prod)
        st.write("Registros encontrados en período:", len(df_prod))
        st.write("Registros CERRADA:", len(df_prod_cerradas))
        st.write("Estados dentro del período:")
        st.dataframe(
            df_prod["_estado_productividad"]
            .value_counts()
            .rename_axis("Estado")
            .reset_index(name="Cantidad"),
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# CONTROL
# ============================================================

with st.expander("🔧 Control técnico / columnas detectadas"):
    st.write(col)
    st.write("Filas originales:", len(raw))
    st.write("Filas de los casos seleccionados:", len(base))
    st.write("Realizadas:", len(realizados))
    st.write("Pendientes:", len(pendientes))
    st.write("Anuladas:", len(anulados))
    st.write("Otros estados:", len(otros))
    st.write("Estados encontrados:")
    st.dataframe(
        df["_estado"].value_counts().rename_axis("Estado").reset_index(name="Cantidad"),
        use_container_width=True, hide_index=True
    )


# ============================================================
# TAB 6 - PROYECCIÓN
# ============================================================

with tabs[5]:
    st.subheader("📈 Proyección operativa del período asignado")
    st.write(
        "La proyección parte del backlog pendiente al cierre del período elegido. "
        "El ingreso diario se calcula automáticamente como el promedio de **OS de INSTALACION "
        "que ingresaron en estado pendiente** durante el mismo período."
    )

    # La referencia de ingreso siempre se calcula sobre INSTALACION pendiente,
    # aunque el filtro de casos seleccione otros tipos para el análisis general.
    base_ingreso_instalacion = df[
        (df["_sucursal"].isin(sucursal)) &
        (df["_fecha"].notna()) &
        (df["_fecha"] >= start) &
        (df["_fecha"] < end_exclusive) &
        (df["_caso"] == "INSTALACION") &
        (df["_estado"].isin(PENDIENTES))
    ].copy()

    dias_periodo_general = (fecha_hasta - fecha_desde).days + 1
    promedio_instalaciones_pendientes_dia = safe_div(
        len(base_ingreso_instalacion), dias_periodo_general
    )

    pc1, pc2, pc3 = st.columns(3)
    pc1.metric("Backlog pendiente al cierre", fmt(len(pendientes)))
    pc2.metric("Instalaciones pendientes ingresadas", fmt(len(base_ingreso_instalacion)))
    pc3.metric("Promedio ingreso diario", f"{promedio_instalaciones_pendientes_dia:.1f} OS/día")
    st.caption(
        f"Cálculo: {fmt(len(base_ingreso_instalacion))} instalaciones pendientes ingresadas / "
        f"{fmt(dias_periodo_general)} días del período seleccionado."
    )

    p1, p2, p3 = st.columns(3)
    with p1:
        q = st.number_input("Cuadrillas para proyección", 1, 50, 5, key="pq")
    with p2:
        prod = st.number_input("Trabajos/cuadrilla/día", 1, 30, 5, key="pp")
    with p3:
        nuevos = st.number_input(
            "Nuevas OS/día (promedio automático)",
            0.0, 10000.0,
            float(round(promedio_instalaciones_pendientes_dia, 1)),
            step=1.0, key="pn"
        )

    max_dias = st.number_input("Máximo de días a proyectar", 7, 3650, 180, key="max_dias_proy")
    capacidad = q * prod
    saldo = capacidad - nuevos
    pendientes_n = len(pendientes)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Capacidad diaria", fmt(capacidad))
    c2.metric("Ingreso diario", f"{nuevos:.1f}")
    c3.metric("Reducción neta diaria", f"{max(saldo, 0):.1f}")
    c4.metric("Cobertura capacidad/ingreso", f"{safe_div(capacidad, nuevos):.2f}x" if nuevos else "∞")

    rows = []
    backlog = float(pendientes_n)
    fecha = fecha_hasta
    for i in range(1, int(max_dias) + 1):
        if backlog <= 0:
            break
        inicio = backlog
        realizadas_plan = min(capacidad, backlog)
        backlog = max(0, backlog - realizadas_plan + nuevos)
        fecha = fecha + timedelta(days=1)
        rows.append({
            "Día": i,
            "Fecha": fecha,
            "Backlog inicio": round(inicio, 1),
            "Trabajos realizados": round(realizadas_plan, 1),
            "Nuevas OS": round(nuevos, 1),
            "Backlog final": round(backlog, 1)
        })

    proj = pd.DataFrame(rows)
    if saldo <= 0:
        st.warning(
            "⚠️ La capacidad diaria no supera el ingreso promedio de instalaciones pendientes. "
            "El backlog no se reduce de forma sostenible con este escenario."
        )
    elif not proj.empty:
        st.dataframe(proj, use_container_width=True, hide_index=True)
        st.line_chart(proj.set_index("Fecha")["Backlog final"])
        fin = proj.iloc[-1]
        dias_teoricos = pendientes_n / saldo if saldo > 0 else 0
        st.info(
            f"Con los parámetros actuales, la reducción neta es de **{saldo:.1f} OS/día** y "
            f"se requieren aproximadamente **{dias_teoricos:.1f} días** para absorber el backlog "
            f"si el ingreso se mantiene en el promedio histórico."
        )
        if fin["Backlog final"] <= 0:
            st.success(f"🎯 El backlog llega a cero el **{fin['Fecha'].strftime('%d/%m/%Y')}**.")
        else:
            st.info(f"Después de {int(fin['Día'])} días quedan aproximadamente **{fmt(fin['Backlog final'])} OS**.")

    st.markdown("### 🧭 Consideraciones y propuestas")
    propuestas = []
    mayores_30 = int((pendientes["antiguedad"] > 30).sum()) if not pendientes.empty else 0
    if pendientes_n and promedio_instalaciones_pendientes_dia >= capacidad:
        propuestas.append("La capacidad no alcanza el ingreso promedio de instalaciones pendientes; se debe aumentar capacidad, productividad o ambas.")
    if mayores_30:
        propuestas.append(f"Priorizar las {fmt(mayores_30)} OS con más de 30 días con seguimiento diario hasta su cierre.")
    if total_cerradas > 0 and promedio_instalaciones_pendientes_dia > promedio_dia:
        propuestas.append("El ingreso promedio de instalaciones pendientes supera el promedio de cierres; conviene revisar capacidad y distribución del trabajo.")
    if not propuestas:
        propuestas.append("Mantener control semanal de backlog, ingreso y cierres para recalibrar la proyección con datos reales.")
    for propuesta in propuestas:
        st.markdown(f"- {propuesta}")

# ============================================================
# GENERADOR DE PDF - INFORME EJECUTIVO
# ============================================================
def generar_pdf_informe(export_desde=None, export_hasta=None):
    """Genera un informe ejecutivo integral en PDF.

    El informe respeta el período y los filtros seleccionados y toma como
    referencia la estructura del informe "ANÁLISIS Y PLANIFICACIÓN DE
    INSTALACIONES": resumen ejecutivo, indicadores, histórico, ingresos,
    antigüedad, capacidad, escenarios, plan operativo, productividad,
    cierres por operador/día/caso, proyección, observaciones, propuestas,
    tablero de seguimiento y metodología.
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
            PageBreak, KeepTogether
        )
        from reportlab.graphics.shapes import Drawing, String
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.linecharts import HorizontalLineChart
    except ImportError as e:
        raise RuntimeError(
            "Para generar PDF falta la librería reportlab. "
            "Instalala con: pip install reportlab"
        ) from e

    # ---------------------------------------------------------
    # 1. Período del PDF
    # ---------------------------------------------------------
    if export_desde is not None and export_hasta is not None:
        pdf_desde = pd.Timestamp(export_desde).normalize()
        pdf_hasta = pd.Timestamp(export_hasta).normalize()
    else:
        pdf_desde = pd.Timestamp(fecha_desde).normalize()
        pdf_hasta = pd.Timestamp(fecha_hasta).normalize()

    if pdf_desde > pdf_hasta:
        raise ValueError("El período de exportación no es válido: Desde es posterior a Hasta.")

    pdf_end_exclusive = pdf_hasta + pd.Timedelta(days=1)
    periodo_dias = (pdf_hasta.date() - pdf_desde.date()).days + 1
    suc_txt = ", ".join(sucursal) if sucursal else "Todas"
    periodo_txt = f"{pdf_desde.strftime('%d/%m/%Y')} al {pdf_hasta.strftime('%d/%m/%Y')}"
    fecha_generacion = date.today().strftime("%d/%m/%Y")

    # ---------------------------------------------------------
    # 2. Base del período exportado
    # ---------------------------------------------------------
    pdf_base = df[
        (df["_sucursal"].isin(sucursal)) &
        (df["_fecha"].notna()) &
        (df["_fecha"] >= pdf_desde) &
        (df["_fecha"] < pdf_end_exclusive) &
        (df["_caso"].isin(casos))
    ].copy()

    pdf_base["antiguedad"] = (
        pdf_hasta.normalize() - pdf_base["_fecha"].dt.normalize()
    ).dt.days.clip(lower=0)

    pdf_base["situacion"] = pdf_base["_estado"].apply(
        lambda x:
            "Realizado" if x in REALIZADO else
            "Falta hacer" if x in PENDIENTES else
            "Anulado" if x in ANULADO else
            "Otro estado"
    )

    pdf_realizados = pdf_base[pdf_base["situacion"] == "Realizado"].copy()
    pdf_pendientes = pdf_base[pdf_base["situacion"] == "Falta hacer"].copy()
    pdf_anulados = pdf_base[pdf_base["situacion"] == "Anulado"].copy()
    pdf_otros = pdf_base[pdf_base["situacion"] == "Otro estado"].copy()
    pdf_pendientes["intervalo"] = pdf_pendientes["antiguedad"].apply(age_bucket)

    total_base = len(pdf_base)
    total_realizados = len(pdf_realizados)
    total_pendientes = len(pdf_pendientes)
    total_anulados = len(pdf_anulados)
    total_otros = len(pdf_otros)
    # Porcentaje de pendientes sobre el total de OS analizadas.
    # Se calcula aquí porque el texto del punto 12 del PDF lo utiliza.
    pct_pend = (total_pendientes / total_base * 100) if total_base else 0.0

    # ---------------------------------------------------------
    # 3. Productividad: Fecha Calendario + CERRADA
    # ---------------------------------------------------------
    if not col_fecha_medicion or not col_usuario or not col_estado_prod or not col_sucursal_prod:
        raise RuntimeError(
            "No se pudieron identificar las columnas necesarias para productividad "
            "(Fecha Calendario, Confeccionada Por, Estado o Sucursal)."
        )

    pdf_prod_all = df.copy()
    pdf_prod_all["_pdf_fecha"] = pd.to_datetime(
        pdf_prod_all[col_fecha_medicion], errors="coerce", dayfirst=True
    )
    pdf_prod_all["_pdf_usuario"] = (
        pdf_prod_all[col_usuario].fillna("").astype(str).str.strip()
    )
    pdf_prod_all["_pdf_estado"] = (
        pdf_prod_all[col_estado_prod].fillna("").astype(str).str.strip().str.upper()
    )
    pdf_prod_all["_pdf_sucursal"] = (
        pdf_prod_all[col_sucursal_prod].fillna("").astype(str).str.strip().str.upper()
    )
    pdf_prod_all = pdf_prod_all[
        pdf_prod_all["_pdf_fecha"].notna()
        & (pdf_prod_all["_pdf_fecha"] >= pdf_desde)
        & (pdf_prod_all["_pdf_fecha"] < pdf_end_exclusive)
        & pdf_prod_all["_pdf_sucursal"].isin([str(x).strip().upper() for x in sucursal])
        & pdf_prod_all["_caso"].isin(casos)
    ].copy()

    pdf_prod = pdf_prod_all[
        (pdf_prod_all["_pdf_estado"] == "CERRADA")
        & pdf_prod_all["_pdf_usuario"].ne("")
        & ~pdf_prod_all["_pdf_usuario"].str.upper().isin(["NAN", "NONE"])
    ].copy()
    pdf_prod["_pdf_dia"] = pdf_prod["_pdf_fecha"].dt.normalize()

    rango_dias = pd.date_range(pdf_desde, pdf_hasta, freq="D")
    cierres_dia = pdf_prod.groupby("_pdf_dia").size() if not pdf_prod.empty else pd.Series(dtype=float)
    pdf_diario = pd.DataFrame({"Fecha": rango_dias})
    pdf_diario["OS Cerradas"] = pdf_diario["Fecha"].map(cierres_dia).fillna(0).astype(int)

    prod_cierres = len(pdf_prod)
    prod_prom_calendario = safe_div(prod_cierres, periodo_dias)
    dias_con_produccion = int((pdf_diario["OS Cerradas"] > 0).sum())
    prod_prom_produccion = safe_div(prod_cierres, dias_con_produccion)

    prod_operador = (
        pdf_prod.groupby("_pdf_usuario").size()
        .reset_index(name="Órdenes Cerradas")
        if not pdf_prod.empty else
        pd.DataFrame(columns=["_pdf_usuario", "Órdenes Cerradas"])
    )
    total_operador = (
        pdf_prod_all.groupby("_pdf_usuario").size()
        .reset_index(name="Total Órdenes")
        if not pdf_prod_all.empty else
        pd.DataFrame(columns=["_pdf_usuario", "Total Órdenes"])
    )
    pdf_prod_data = total_operador.merge(prod_operador, on="_pdf_usuario", how="left")
    if not pdf_prod_data.empty:
        pdf_prod_data["Órdenes Cerradas"] = pdf_prod_data["Órdenes Cerradas"].fillna(0).astype(int)
        pdf_prod_data["Efectividad Cierre (%)"] = (
            pdf_prod_data["Órdenes Cerradas"]
            .div(pdf_prod_data["Total Órdenes"].replace(0, pd.NA))
            .fillna(0).mul(100).round(1)
        )
        pdf_prod_data = pdf_prod_data.rename(columns={"_pdf_usuario": "Confeccionada Por"})
        pdf_prod_data = pdf_prod_data.sort_values(
            ["Órdenes Cerradas", "Confeccionada Por"], ascending=[False, True]
        )
    else:
        pdf_prod_data = pd.DataFrame(
            columns=["Confeccionada Por", "Total Órdenes", "Órdenes Cerradas", "Efectividad Cierre (%)"]
        )

    # Casos por operador.
    if not pdf_prod.empty:
        pdf_casos_operador = pd.crosstab(
            pdf_prod["_pdf_usuario"], pdf_prod["_caso"]
        ).reindex(columns=casos, fill_value=0)
        pdf_casos_operador["TOTAL"] = pdf_casos_operador.sum(axis=1)
        pdf_casos_operador = (
            pdf_casos_operador.sort_values("TOTAL", ascending=False)
            .reset_index().rename(columns={"_pdf_usuario": "Confeccionada Por"})
        )
    else:
        pdf_casos_operador = pd.DataFrame(columns=["Confeccionada Por"] + list(casos) + ["TOTAL"])

    # ---------------------------------------------------------
    # 4. Ingreso de instalaciones pendientes para la proyección
    # ---------------------------------------------------------
    ingreso_inst = df[
        (df["_sucursal"].isin(sucursal)) &
        (df["_fecha"].notna()) &
        (df["_fecha"] >= pdf_desde) &
        (df["_fecha"] < pdf_end_exclusive) &
        (df["_caso"] == "INSTALACION") &
        (df["_estado"].isin(PENDIENTES))
    ].copy()
    ingreso_inst_dia = (
        ingreso_inst.groupby(ingreso_inst["_fecha"].dt.normalize()).size()
        if not ingreso_inst.empty else pd.Series(dtype=float)
    )
    ingreso_prom_calendario = safe_div(len(ingreso_inst), periodo_dias)
    ingreso_dias_con_pedidos = int((ingreso_inst_dia > 0).sum())
    ingreso_prom_dias_con_pedidos = safe_div(len(ingreso_inst), ingreso_dias_con_pedidos)

    # ---------------------------------------------------------
    # 5. Proyección y escenarios
    # ---------------------------------------------------------
    q_pdf = int(st.session_state.get("pq", 5))
    prod_pdf = int(st.session_state.get("pp", 5))
    dias_trabajo_pdf = int(dias_trabajo_semana) if "dias_trabajo_semana" in globals() else 6
    capacidad_pdf = q_pdf * prod_pdf
    saldo_pdf = capacidad_pdf - ingreso_prom_calendario
    max_dias_pdf = int(max_dias) if "max_dias" in globals() else 180

    proj_rows = []
    backlog = float(total_pendientes)
    fecha_proj = pdf_hasta.date()
    for i in range(1, max_dias_pdf + 1):
        if backlog <= 0:
            break
        inicio = backlog
        realizadas_plan = min(capacidad_pdf, backlog)
        backlog = max(0, backlog - realizadas_plan + ingreso_prom_calendario)
        fecha_proj += timedelta(days=1)
        proj_rows.append({
            "Día": i,
            "Fecha": fecha_proj,
            "Backlog inicio": round(inicio, 1),
            "Trabajos realizados": round(realizadas_plan, 1),
            "Nuevas OS": round(ingreso_prom_calendario, 1),
            "Backlog final": round(backlog, 1),
        })
    pdf_proj = pd.DataFrame(proj_rows)

    def fecha_suma_dias_laborables(fecha_inicio, dias, dias_semana=6):
        """Suma días operativos lunes-sábado o lunes-viernes según parámetro."""
        if dias <= 0:
            return fecha_inicio
        fecha = pd.Timestamp(fecha_inicio).normalize()
        acumulados = 0
        while acumulados < int(dias):
            fecha += pd.Timedelta(days=1)
            # 6 = lunes-sábado; 5 = lunes-viernes; cualquier otro usa días hábiles estándar.
            es_laborable = fecha.weekday() < (6 if dias_semana >= 6 else 5)
            if es_laborable:
                acumulados += 1
        return fecha.date()

    def escenario(capacidad_dia):
        neto = capacidad_dia - ingreso_prom_calendario
        if neto <= 0:
            return {"cap": capacidad_dia, "net": neto, "dias": None, "fecha": None}
        dias = int(__import__("math").ceil(total_pendientes / neto)) if total_pendientes else 0
        fecha = fecha_suma_dias_laborables(pdf_hasta.date(), dias, dias_trabajo_pdf)
        return {"cap": capacidad_dia, "net": neto, "dias": dias, "fecha": fecha}

    escenarios_pdf = [escenario(x) for x in [15.8, 18, 20, 22, 25]]

    # ---------------------------------------------------------
    # 6. Antigüedad
    # ---------------------------------------------------------
    edad_prom = pdf_pendientes["antiguedad"].mean() if not pdf_pendientes.empty else 0
    edad_mediana = pdf_pendientes["antiguedad"].median() if not pdf_pendientes.empty else 0
    edad_max = pdf_pendientes["antiguedad"].max() if not pdf_pendientes.empty else 0
    pendientes_10 = int((pdf_pendientes["antiguedad"] >= 10).sum()) if not pdf_pendientes.empty else 0
    pendientes_30 = int((pdf_pendientes["antiguedad"] > 30).sum()) if not pdf_pendientes.empty else 0

    # ---------------------------------------------------------
    # 7. Estilos y utilidades PDF
    # ---------------------------------------------------------
    azul = colors.HexColor("#1F4E79")
    azul_claro = colors.HexColor("#D9EAF7")
    gris = colors.HexColor("#666666")
    gris_claro = colors.HexColor("#F2F2F2")
    negro = colors.HexColor("#111111")
    blanco = colors.white
    verde = colors.HexColor("#548235")
    rojo = colors.HexColor("#C00000")

    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=A4,
        rightMargin=1.45 * cm,
        leftMargin=1.45 * cm,
        topMargin=1.35 * cm,
        bottomMargin=1.35 * cm,
        title="Análisis y Gestión de Órdenes de Servicio",
        author="Gestión de Órdenes de Servicio",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name="TituloInforme", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=18, leading=22, alignment=TA_CENTER, textColor=negro, spaceAfter=8
    ))
    styles.add(ParagraphStyle(
        name="SubtituloInforme", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=14, alignment=TA_CENTER, textColor=negro, spaceAfter=7
    ))
    styles.add(ParagraphStyle(
        name="FechaInforme", parent=styles["Normal"], fontName="Helvetica-Oblique",
        fontSize=9.5, leading=12, alignment=TA_CENTER, textColor=gris, spaceAfter=16
    ))
    styles.add(ParagraphStyle(
        name="SeccionInforme", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=13, leading=16, textColor=azul, spaceBefore=5, spaceAfter=7
    ))
    styles.add(ParagraphStyle(
        name="SubseccionInforme", parent=styles["Heading3"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=13, textColor=azul, spaceBefore=5, spaceAfter=5
    ))
    styles.add(ParagraphStyle(
        name="TextoInforme", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9.2, leading=13, textColor=negro, spaceAfter=7
    ))
    styles.add(ParagraphStyle(
        name="TextoNegrita", parent=styles["BodyText"], fontName="Helvetica-Bold",
        fontSize=9.2, leading=13, textColor=negro, spaceAfter=7
    ))
    styles.add(ParagraphStyle(
        name="PieInforme", parent=styles["Normal"], fontName="Helvetica",
        fontSize=7.5, leading=9, textColor=gris
    ))

    def P(text, style="TextoInforme"):
        return Paragraph(str(text), styles[style])

    def moneyless(n):
        try:
            return fmt(n)
        except Exception:
            return str(n)

    def table_pdf(data, widths=None, font_size=7.5, header=True):
        if not data:
            return Table([[""]])
        converted = []
        for r, row in enumerate(data):
            cells = []
            for i, v in enumerate(row):
                txt = "" if pd.isna(v) else str(v)
                cells.append(Paragraph(
                    txt,
                    ParagraphStyle(
                        name=f"celda_{id(data)}_{r}_{i}",
                        fontName="Helvetica-Bold" if header and r == 0 else "Helvetica",
                        fontSize=font_size,
                        leading=font_size + 2,
                        textColor=blanco if header and r == 0 else negro,
                    )
                ))
            converted.append(cells)
        t = Table(converted, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
        commands = [
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#888888")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if header:
            commands += [("BACKGROUND", (0, 0), (-1, 0), azul), ("TEXTCOLOR", (0, 0), (-1, 0), blanco)]
            if len(converted) > 1:
                commands.append(("ROWBACKGROUNDS", (0, 1), (-1, -1), [blanco, gris_claro]))
        t.setStyle(TableStyle(commands))
        return t

    def grafico_barras(labels, valores, titulo, ancho=17 * cm, alto=7 * cm):
        d = Drawing(ancho, alto)
        chart = VerticalBarChart()
        chart.x = 42
        chart.y = 28
        chart.width = ancho - 58
        chart.height = alto - 50
        vals = [float(x) for x in valores]
        chart.data = [vals]
        chart.categoryAxis.categoryNames = [str(x)[:20] for x in labels]
        chart.valueAxis.valueMin = 0
        max_val = max(vals, default=1)
        chart.valueAxis.valueMax = max(1, max_val * 1.18)
        chart.valueAxis.valueStep = max(1, round(chart.valueAxis.valueMax / 5))
        chart.bars[0].fillColor = azul
        chart.bars[0].strokeColor = azul
        chart.categoryAxis.labels.fontName = "Helvetica"
        chart.categoryAxis.labels.fontSize = 6.3
        chart.categoryAxis.labels.angle = 35
        chart.valueAxis.labels.fontName = "Helvetica"
        chart.valueAxis.labels.fontSize = 7
        chart.valueAxis.strokeColor = colors.HexColor("#999999")
        chart.categoryAxis.strokeColor = colors.HexColor("#999999")
        d.add(chart)
        d.add(String(ancho / 2, 8, str(titulo), fontName="Helvetica",
                      fontSize=9, fillColor=negro, textAnchor="middle"))
        return d

    def grafico_linea(fechas, valores, titulo, ancho=17 * cm, alto=7 * cm):
        d = Drawing(ancho, alto)
        chart = HorizontalLineChart()
        chart.x = 42
        chart.y = 28
        chart.width = ancho - 58
        chart.height = alto - 50
        vals = [float(x) for x in valores]
        chart.data = [vals]
        chart.categoryAxis.categoryNames = [pd.Timestamp(x).strftime("%d/%m") for x in fechas]
        chart.categoryAxis.labels.fontName = "Helvetica"
        chart.categoryAxis.labels.fontSize = 5.8
        chart.categoryAxis.labels.angle = 45
        chart.valueAxis.labels.fontName = "Helvetica"
        chart.valueAxis.labels.fontSize = 7
        chart.valueAxis.valueMin = 0
        chart.valueAxis.valueMax = max(1, max(vals, default=1) * 1.15)
        chart.lines[0].strokeColor = azul
        chart.lines[0].strokeWidth = 1.8
        d.add(chart)
        d.add(String(ancho / 2, 8, str(titulo), fontName="Helvetica",
                      fontSize=9, fillColor=negro, textAnchor="middle"))
        return d

    def pie_pagina(canvas, doc_obj):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D0D0D0"))
        canvas.line(doc_obj.leftMargin, 0.95 * cm, A4[0] - doc_obj.rightMargin, 0.95 * cm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(gris)
        canvas.drawString(doc_obj.leftMargin, 0.58 * cm, "Gestión de Órdenes de Servicio")
        canvas.drawRightString(A4[0] - doc_obj.rightMargin, 0.58 * cm, f"Página {doc_obj.page}")
        canvas.restoreState()

    # ---------------------------------------------------------
    # Construcción del informe - ORDEN SOLICITADO
    # ---------------------------------------------------------
    story = [
        P("ANÁLISIS Y GESTIÓN DE ÓRDENES DE SERVICIO", "TituloInforme"),
        P(
            f"Informe de productividad y gestión operativa | Período: {periodo_txt} | Sucursal/es: {suc_txt}",
            "SubtituloInforme"
        ),
        P(f"Generado el {fecha_generacion}", "FechaInforme"),
    ]

    # 1. Productividad por personal
    story.append(P("1. Productividad por personal", "SeccionInforme"))
    story.append(P(
        f"El análisis comprende el período <b>{periodo_txt}</b>. La productividad se calcula "
        f"utilizando <b>{col_fecha_medicion}</b>, considerando únicamente órdenes en estado "
        f"<b>CERRADA</b>, las sucursales seleccionadas y los casos seleccionados."
    ))
    story.append(P(
        f"Durante el período se registraron <b>{moneyless(prod_cierres)}</b> OS cerradas, "
        f"con un promedio de <b>{prod_prom_calendario:.1f} OS por día calendario</b> y "
        f"<b>{prod_prom_produccion:.1f} OS por día efectivo de producción</b>."
    ))
    if not pdf_prod_data.empty:
        rows_prod = [["Confeccionada Por", "Total Órdenes", "OS Cerradas", "Efectividad"]]
        for _, r in pdf_prod_data.iterrows():
            rows_prod.append([
                r["Confeccionada Por"], moneyless(r["Total Órdenes"]),
                moneyless(r["Órdenes Cerradas"]), f"{float(r['Efectividad Cierre (%)']):.1f}%"
            ])
        story.append(table_pdf(rows_prod, widths=[6.0*cm, 3.0*cm, 3.0*cm, 4.0*cm], font_size=7.2))
        top = pdf_prod_data.head(15)
        story.append(Spacer(1, 7))
        story.append(grafico_barras(
            top["Confeccionada Por"].tolist(),
            top["Órdenes Cerradas"].tolist(),
            "OS cerradas por operador"
        ))
    else:
        story.append(P("No se encontraron cierres con responsable en el período seleccionado."))

    # 2. Cierres por operador por día
    story.append(P("2. Cierres por operador por día", "SeccionInforme"))
    if not pdf_prod.empty:
        mat = pd.crosstab(pdf_prod["_pdf_usuario"], pdf_prod["_pdf_dia"]).reindex(columns=rango_dias, fill_value=0)
        mat = mat.reset_index().rename(columns={"_pdf_usuario": "Confeccionada Por"})
        mat["TOTAL"] = mat.drop(columns=["Confeccionada Por"]).sum(axis=1)
        # Para períodos largos se muestran bloques de 15 días.
        if len(rango_dias) <= 15:
            rows = [["Confeccionada Por"] + [d.strftime("%d/%m") for d in rango_dias] + ["TOTAL"]]
            for _, r in mat.iterrows():
                rows.append([r["Confeccionada Por"]] + [moneyless(r[d]) for d in rango_dias] + [moneyless(r["TOTAL"])])
            story.append(table_pdf(rows, font_size=6.0))
        else:
            story.append(P("Para mantener la legibilidad, el período se divide en bloques de hasta 15 días."))
            for ini in range(0, len(rango_dias), 15):
                bloque = rango_dias[ini:ini+15]
                r2 = [["Confeccionada Por"] + [d.strftime("%d/%m") for d in bloque] + ["TOTAL BLOQUE"]]
                for _, r in mat.iterrows():
                    r2.append([
                        r["Confeccionada Por"],
                        *[moneyless(r[d]) for d in bloque],
                        moneyless(sum(r[d] for d in bloque))
                    ])
                story.append(Spacer(1, 5))
                story.append(table_pdf(r2, font_size=5.8))
    else:
        story.append(P("No hay cierres para mostrar."))

    # 3. Casos de trabajo cerrados por operador
    story.append(P("3. Casos de trabajo cerrados por operador", "SeccionInforme"))
    if not pdf_casos_operador.empty:
        rows_casos = [list(pdf_casos_operador.columns)] + [list(map(str, r)) for r in pdf_casos_operador.astype(str).values]
        story.append(table_pdf(rows_casos, font_size=6.4))
        totales_caso = [pdf_casos_operador[c].sum() for c in casos]
        story.append(Spacer(1, 6))
        story.append(grafico_barras(casos, totales_caso, "Distribución total de cierres por caso"))
    else:
        story.append(P("No hay casos de trabajo cerrados para el período seleccionado."))

    # 4. Detalle individual de cierres por operador, día y caso
    story.append(P("4. Detalle individual de cierres por operador, día y caso", "SeccionInforme"))
    story.append(P(
        "Se presenta un cuadro independiente para cada operador. Cada cuadro contiene solamente "
        "los días en los que registró cierres y desglosa la cantidad por caso, evitando repetir "
        "innecesariamente el nombre del operador en cada fila."
    ))
    if not pdf_prod.empty:
        operadores = sorted(
            [x for x in pdf_prod["_pdf_usuario"].dropna().astype(str).str.strip().unique()
             if x and x.upper() not in ("NAN", "NONE")],
            key=str.lower
        )
        for operador in operadores:
            op = pdf_prod[pdf_prod["_pdf_usuario"].astype(str).str.strip() == operador].copy()
            tabla_op = pd.crosstab(op["_pdf_dia"], op["_caso"]).reindex(columns=casos, fill_value=0)
            tabla_op = tabla_op.loc[tabla_op.sum(axis=1) > 0]
            if tabla_op.empty:
                continue
            tabla_op.insert(0, "Fecha", tabla_op.index)
            tabla_op = tabla_op.reset_index(drop=True)
            tabla_op["TOTAL"] = tabla_op[casos].sum(axis=1)
            tabla_op["Fecha"] = pd.to_datetime(tabla_op["Fecha"]).dt.strftime("%d/%m/%Y")
            op_rows = [["Fecha"] + list(casos) + ["TOTAL"]]
            for _, r in tabla_op.iterrows():
                op_rows.append([r["Fecha"]] + [moneyless(r[c]) for c in casos] + [moneyless(r["TOTAL"])])
            story.append(Spacer(1, 6))
            story.append(P(f"Operador: <b>{operador}</b>", "SubseccionInforme"))
            story.append(table_pdf(op_rows, font_size=6.0))
    else:
        story.append(P("No hay cierres para el detalle individual."))

    # 5. Productividad día por día
    story.append(P("5. Productividad día por día", "SeccionInforme"))
    story.append(P(
        f"El comportamiento diario se analiza sobre los <b>{moneyless(periodo_dias)} días</b> "
        f"comprendidos en el período seleccionado. Hubo <b>{moneyless(dias_con_produccion)}</b> días "
        f"con al menos un cierre y <b>{moneyless(periodo_dias - dias_con_produccion)}</b> días sin cierres."
    ))
    diario_rows = [["Fecha", "OS Cerradas"]]
    for _, r in pdf_diario.iterrows():
        diario_rows.append([pd.Timestamp(r["Fecha"]).strftime("%d/%m/%Y"), moneyless(r["OS Cerradas"])])
    story.append(table_pdf(diario_rows, widths=[6*cm, 4*cm], font_size=7.2))
    story.append(Spacer(1, 7))
    if not pdf_diario.empty:
        story.append(grafico_linea(
            pdf_diario["Fecha"].tolist(),
            pdf_diario["OS Cerradas"].tolist(),
            "Evolución diaria de cierres"
        ))

    # 6. Antigüedad de las instalaciones pendientes
    story.append(P("6. Antigüedad de las instalaciones pendientes", "SeccionInforme"))
    story.append(P(
        f"Al cierre del período quedan <b>{moneyless(total_pendientes)}</b> OS pendientes. "
        f"La antigüedad promedio es de <b>{edad_prom:.1f} días</b>, la mediana de "
        f"<b>{edad_mediana:.0f} días</b> y la máxima de <b>{edad_max:.0f} días</b>. "
        f"Hay <b>{moneyless(pendientes_10)}</b> OS con 10 días o más y "
        f"<b>{moneyless(pendientes_30)}</b> con más de 30 días."
    ))
    cruz_pdf = pd.crosstab(pdf_pendientes["intervalo"], pdf_pendientes["_caso"]) if not pdf_pendientes.empty else pd.DataFrame()
    cruz_pdf = cruz_pdf.reindex(INTERVALOS, fill_value=0)
    for c in casos:
        if c not in cruz_pdf.columns:
            cruz_pdf[c] = 0
    if not cruz_pdf.empty:
        cruz_pdf = cruz_pdf[casos]
        cruz_pdf["TOTAL"] = cruz_pdf.sum(axis=1)
        cruz_total = cruz_pdf.sum(axis=0).to_frame().T
        cruz_total.index = ["TOTAL"]
        cruz_pdf_final = pd.concat([cruz_pdf, cruz_total])
        edad_rows = [["Intervalo"] + list(casos) + ["TOTAL"]]
        for idx, row in cruz_pdf_final.iterrows():
            edad_rows.append([idx] + [moneyless(row.get(c, 0)) for c in casos] + [moneyless(row.get("TOTAL", 0))])
        story.append(table_pdf(edad_rows, font_size=6.2))

    # 7. Capacidad de las cuadrillas
    story.append(P("7. Capacidad de las cuadrillas", "SeccionInforme"))
    story.append(P(
        f"El escenario operativo utiliza <b>{q_pdf} cuadrillas</b> y una referencia de "
        f"<b>{prod_pdf} trabajos por cuadrilla/día</b>, equivalente a una capacidad teórica "
        f"de <b>{capacidad_pdf} OS/día</b>. La producción observada fue de "
        f"<b>{prod_prom_produccion:.1f} OS/día</b> en los días con actividad."
    ))
    story.append(P(
        f"Con {q_pdf} cuadrillas, la referencia histórica equivale a aproximadamente "
        f"<b>{safe_div(prod_prom_produccion, q_pdf):.1f} OS por cuadrilla/día</b>. "
        "Esta cifra es una referencia agregada y no una asignación individual de cuadrillas."
    ))

    # 8. Ingreso de nuevas instalaciones
    story.append(P("8. Ingreso de nuevas instalaciones", "SeccionInforme"))
    story.append(P(
        f"Durante el período ingresaron <b>{moneyless(len(ingreso_inst))}</b> OS de INSTALACION "
        f"que quedaron en estado pendiente. El promedio de ingreso fue de "
        f"<b>{ingreso_prom_calendario:.1f} OS/día calendario</b> y, considerando solamente los "
        f"días con ingreso, de <b>{ingreso_prom_dias_con_pedidos:.1f} OS/día</b>."
    ))
    if not ingreso_inst_dia.empty:
        story.append(P(
            f"El máximo diario observado fue de <b>{moneyless(int(ingreso_inst_dia.max()))} OS</b> "
            f"y la mediana de los días con ingreso fue de <b>{float(ingreso_inst_dia.median()):.1f} OS/día</b>."
        ))

    # 9. Escenarios de recuperación
    story.append(P("9. Escenarios de recuperación", "SeccionInforme"))
    escenarios_rows = [["Escenario", "Capacidad/día", "Reducción neta/día", "Días operativos", "Fecha estimada"]]
    nombres_esc = [
        "Capacidad 15,8/día", "18 instalaciones/día", "20 instalaciones/día",
        "22 instalaciones/día", "25 instalaciones/día"
    ]
    for nombre, esc in zip(nombres_esc, escenarios_pdf):
        escenarios_rows.append([
            nombre, f"{esc['cap']:.1f}", f"{esc['net']:.1f}",
            str(esc["dias"]) if esc["dias"] is not None else "No se reduce",
            esc["fecha"].strftime("%d/%m/%Y") if esc["fecha"] else "—"
        ])
    story.append(table_pdf(
        escenarios_rows,
        widths=[4.2*cm, 2.8*cm, 3.3*cm, 3.0*cm, 3.2*cm],
        font_size=7.0
    ))
    story.append(P(
        "Los escenarios son referencias de gestión. Su resultado depende de sostener la capacidad "
        "y el nivel de ingreso promedio; no constituyen una fecha comprometida."
    ))

    # 10. Plan operativo recomendado
    story.append(P("10. Plan operativo recomendado", "SeccionInforme"))
    plan = [
        "Sostener una producción diaria superior al ingreso promedio de nuevas instalaciones.",
        "Priorizar las OS de mayor antigüedad y aplicar FIFO dentro de cada zona o recorrido.",
        "Controlar diariamente ingreso, cierres, pendientes y antigüedad máxima.",
        "Comparar semanalmente capacidad efectiva contra ingreso real y corregir desvíos.",
        f"Reducir la cartera actual de {moneyless(total_pendientes)} OS hacia una zona de seguridad que permita absorber variaciones de demanda.",
        "Una vez recuperado el plazo, mantener capacidad de reserva para picos de ingreso."
    ]
    for item in plan:
        story.append(P("• " + item))

    # 11. Proyección operativa (SIN GRÁFICO)
    story.append(P("11. Proyección operativa", "SeccionInforme"))
    story.append(P(
        f"La proyección parte de <b>{moneyless(total_pendientes)} OS pendientes</b> al cierre del "
        f"período y utiliza un ingreso automático de <b>{ingreso_prom_calendario:.1f} instalaciones "
        f"pendientes/día</b>, calculado exclusivamente con el período seleccionado."
    ))
    story.append(P(
        f"Escenario configurado: <b>{q_pdf} cuadrillas × {prod_pdf} trabajos/cuadrilla/día = "
        f"{capacidad_pdf} OS/día</b>. Reducción neta estimada: <b>{max(saldo_pdf, 0):.1f} OS/día</b>."
    ))
    if not pdf_proj.empty:
        fin = pdf_proj.iloc[-1]
        if float(fin["Backlog final"]) <= 0:
            story.append(P(
                f"<b>Resultado:</b> bajo este escenario el backlog llega a cero aproximadamente el "
                f"<b>{pd.Timestamp(fin['Fecha']).strftime('%d/%m/%Y')}</b>."
            ))
        else:
            story.append(P(
                f"<b>Resultado:</b> después de <b>{moneyless(fin['Día'])} días</b> proyectados "
                f"quedarían aproximadamente <b>{moneyless(fin['Backlog final'])} OS</b>."
            ))
        # Tabla resumida, sin gráfico.
        proj_rows = [["Día", "Fecha", "Backlog inicio", "Trabajos realizados", "Nuevas OS", "Backlog final"]]
        muestra = pdf_proj if len(pdf_proj) <= 30 else pd.concat([pdf_proj.head(15), pdf_proj.tail(15)])
        for _, r in muestra.iterrows():
            proj_rows.append([
                moneyless(r["Día"]), pd.Timestamp(r["Fecha"]).strftime("%d/%m/%Y"),
                r["Backlog inicio"], r["Trabajos realizados"], r["Nuevas OS"], r["Backlog final"]
            ])
        story.append(table_pdf(
            proj_rows,
            widths=[1.2*cm, 3.0*cm, 3.0*cm, 3.1*cm, 2.5*cm, 3.0*cm],
            font_size=6.2
        ))
    else:
        story.append(P(
            "No existe reducción sostenible con los parámetros configurados o no existe backlog pendiente."
        ))

    # 12. Observaciones y oportunidades de mejora
    story.append(P("12. Observaciones y oportunidades de mejora", "SeccionInforme"))
    observaciones = []
    if total_pendientes:
        observaciones.append(
            f"La cartera termina con {moneyless(total_pendientes)} OS pendientes, equivalente al {pct_pend:.1f}% de las OS analizadas."
        )
    if pendientes_10:
        observaciones.append(
            f"Existen {moneyless(pendientes_10)} OS con 10 días o más; deben tratarse como prioridad operativa."
        )
    if pendientes_30:
        observaciones.append(
            f"Hay {moneyless(pendientes_30)} OS con más de 30 días; se recomienda un plan específico de recuperación y seguimiento diario."
        )
    if ingreso_prom_calendario > prod_prom_calendario and prod_cierres > 0:
        observaciones.append(
            "El ingreso promedio de instalaciones pendientes supera la producción promedio diaria; si esta relación continúa, el backlog tenderá a crecer."
        )
    if prod_cierres and dias_con_produccion < periodo_dias:
        observaciones.append(
            f"Se detectaron {moneyless(periodo_dias - dias_con_produccion)} días sin cierres; conviene revisar disponibilidad, asignación, materiales, movilidad y causas de jornada sin producción."
        )
    if not pdf_prod_data.empty and len(pdf_prod_data) > 1:
        top_cierre = int(pdf_prod_data.iloc[0]["Órdenes Cerradas"])
        med_cierre = float(pdf_prod_data["Órdenes Cerradas"].median())
        if top_cierre > med_cierre * 1.8 and med_cierre > 0:
            observaciones.append(
                "Existe dispersión importante en los cierres por operador; conviene revisar balance de carga, complejidad de casos y disponibilidad de trabajo."
            )
    if not observaciones:
        observaciones.append("No se detectaron alertas críticas con los indicadores disponibles; mantener seguimiento periódico.")
    for obs in observaciones:
        story.append(P("• " + obs))

    # 13. Consideraciones y propuestas
    story.append(P("13. Consideraciones y propuestas", "SeccionInforme"))
    propuestas = [
        "Mantener un control diario de ingreso, cierres y backlog.",
        "Priorizar las OS antiguas y realizar seguimiento específico de las que superen los 10 días.",
        "Utilizar la productividad por operador, día y caso para equilibrar cargas y detectar desvíos.",
        "Revisar la distribución de casos para identificar dónde se concentra la demanda y dónde existen oportunidades de especialización.",
        "Ajustar cuadrillas o productividad cuando la capacidad neta sea insuficiente para reducir la cartera.",
        "Actualizar periódicamente la proyección utilizando el promedio real de ingreso de instalaciones pendientes.",
        "Investigar y documentar jornadas de baja o nula producción para corregir causas repetitivas.",
        "Una vez normalizada la antigüedad, conservar capacidad de reserva para absorber picos de demanda."
    ]
    for prop in propuestas:
        story.append(P("• " + prop))

    doc.build(story, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()


# ============================================================
# TAB 7 - EXPORTAR
# ============================================================

with tabs[6]:
    st.subheader("📥 Exportar resultados")
    st.write(
        "Elegí el período que querés incluir en la exportación. "
        "Este período es independiente del período general de la barra lateral."
    )

    tipo_periodo_export = st.radio(
        "Período de exportación",
        ["Período analizado", "Período personalizado"],
        horizontal=True,
        key="tipo_periodo_export"
    )

    if tipo_periodo_export == "Período analizado":
        export_desde = fecha_desde
        export_hasta = fecha_hasta
        st.info(
            f"Se exportará el período analizado: **{export_desde.strftime('%d/%m/%Y')}** "
            f"al **{export_hasta.strftime('%d/%m/%Y')}**."
        )
    else:
        ec1, ec2 = st.columns(2)
        with ec1:
            export_desde = st.date_input(
                "Desde",
                value=fecha_desde,
                min_value=min_date,
                max_value=max_date,
                key="export_desde_personalizado"
            )
        with ec2:
            export_hasta = st.date_input(
                "Hasta",
                value=fecha_hasta,
                min_value=min_date,
                max_value=max_date,
                key="export_hasta_personalizado"
            )

        if export_desde > export_hasta:
            st.error("La fecha Desde no puede ser posterior a Hasta.")
            st.stop()

        st.success(
            f"Período personalizado seleccionado: **{export_desde.strftime('%d/%m/%Y')}** "
            f"al **{export_hasta.strftime('%d/%m/%Y')}**."
        )

    # ---------------------------------------------------------
    # Construir los datos de exportación para el período elegido
    # ---------------------------------------------------------
    export_start = pd.Timestamp(export_desde)
    export_end = pd.Timestamp(export_hasta)

    base_export = df[
        (df["_sucursal"].isin(sucursal)) &
        (df["_fecha"].notna()) &
        (df["_fecha"] >= export_start.normalize()) &
        (df["_fecha"] < (export_end.normalize() + pd.Timedelta(days=1))) &
        (df["_caso"].isin(casos))
    ].copy()

    base_export["antiguedad"] = (export_end - base_export["_fecha"]).dt.days
    base_export["situacion"] = base_export["_estado"].apply(
        lambda x:
            "Realizado" if x in REALIZADO else
            "Falta hacer" if x in PENDIENTES else
            "Anulado" if x in ANULADO else
            "Otro estado"
    )

    realizados_export = base_export[base_export["situacion"] == "Realizado"].copy()
    pendientes_export = base_export[base_export["situacion"] == "Falta hacer"].copy()
    anulados_export = base_export[base_export["situacion"] == "Anulado"].copy()
    otros_export = base_export[base_export["situacion"] == "Otro estado"].copy()
    pendientes_export["intervalo"] = pendientes_export["antiguedad"].apply(age_bucket)

    entradas_export = base_export.copy()

    tabla_export = pd.crosstab(base_export["_caso"], base_export["situacion"])
    for estado_export in ["Realizado", "Falta hacer", "Anulado", "Otro estado"]:
        if estado_export not in tabla_export.columns:
            tabla_export[estado_export] = 0
    tabla_export["Total"] = tabla_export.sum(axis=1)
    tabla_export = tabla_export.reset_index().rename(columns={"_caso": "Caso"})
    tabla_export = tabla_export[["Caso", "Realizado", "Falta hacer", "Anulado", "Otro estado", "Total"]]

    cruz_export = pd.crosstab(pendientes_export["intervalo"], pendientes_export["_caso"])
    cruz_export = cruz_export.reindex(INTERVALOS, fill_value=0)
    for caso_export in casos:
        if caso_export not in cruz_export.columns:
            cruz_export[caso_export] = 0
    cruz_export = cruz_export[casos]
    cruz_export["TOTAL"] = cruz_export.sum(axis=1)
    total_export = cruz_export.sum(axis=0).to_frame().T
    total_export.index = ["TOTAL"]
    cruz_final_export = pd.concat([cruz_export, total_export])

    # ---------------------------------------------------------
    # Productividad para el mismo período de exportación
    # ---------------------------------------------------------
    export_prod = df.copy()
    export_prod["_fecha_prod_export"] = pd.to_datetime(export_prod[col_fecha_medicion], errors="coerce", dayfirst=True)
    export_prod["_usuario_prod_export"] = export_prod[col_usuario].fillna("").astype(str).str.strip()
    export_prod["_estado_prod_export"] = export_prod[col_estado_prod].fillna("").astype(str).str.strip().str.upper()
    export_prod["_sucursal_prod_export"] = export_prod[col_sucursal_prod].fillna("").astype(str).str.strip().str.upper()
    export_prod = export_prod[
        export_prod["_fecha_prod_export"].notna()
        & (export_prod["_fecha_prod_export"] >= export_start.normalize())
        & (export_prod["_fecha_prod_export"] < export_end.normalize() + pd.Timedelta(days=1))
        & export_prod["_sucursal_prod_export"].isin([str(x).strip().upper() for x in sucursal])
        & export_prod["_caso"].isin(casos)
    ].copy()
    export_prod_cerradas = export_prod[
        (export_prod["_estado_prod_export"] == "CERRADA")
        & export_prod["_usuario_prod_export"].ne("")
        & export_prod["_usuario_prod_export"].str.upper().ne("NAN")
        & export_prod["_usuario_prod_export"].str.upper().ne("NONE")
    ].copy()
    export_prod_cerradas["_dia_prod_export"] = export_prod_cerradas["_fecha_prod_export"].dt.normalize()

    prod_export_operador = export_prod.groupby("_usuario_prod_export").size().reset_index(name="Total Órdenes") if not export_prod.empty else pd.DataFrame(columns=["_usuario_prod_export", "Total Órdenes"])
    cerradas_export_operador = export_prod_cerradas.groupby("_usuario_prod_export").size().reset_index(name="Órdenes Cerradas") if not export_prod_cerradas.empty else pd.DataFrame(columns=["_usuario_prod_export", "Órdenes Cerradas"])
    prod_export_operador = prod_export_operador.merge(cerradas_export_operador, on="_usuario_prod_export", how="left")
    if not prod_export_operador.empty:
        prod_export_operador["Órdenes Cerradas"] = prod_export_operador["Órdenes Cerradas"].fillna(0).astype(int)
        prod_export_operador["Efectividad Cierre (%)"] = prod_export_operador["Órdenes Cerradas"].div(prod_export_operador["Total Órdenes"].replace(0, pd.NA)).fillna(0).mul(100).round(1)
        prod_export_operador = prod_export_operador.rename(columns={"_usuario_prod_export": "Confeccionada Por"}).sort_values("Órdenes Cerradas", ascending=False)

    cierres_export_dia = pd.DataFrame({"Fecha": pd.date_range(export_start.normalize(), export_end.normalize(), freq="D")})
    conteos_export_dia = export_prod_cerradas.groupby("_dia_prod_export").size() if not export_prod_cerradas.empty else pd.Series(dtype=float)
    cierres_export_dia["Órdenes Cerradas"] = cierres_export_dia["Fecha"].map(conteos_export_dia).fillna(0).astype(int)

    casos_export_operador = pd.crosstab(export_prod_cerradas["_usuario_prod_export"], export_prod_cerradas["_caso"]).reindex(columns=casos, fill_value=0) if not export_prod_cerradas.empty else pd.DataFrame(columns=casos)
    if not casos_export_operador.empty:
        casos_export_operador["TOTAL"] = casos_export_operador.sum(axis=1)
        casos_export_operador = casos_export_operador.sort_values("TOTAL", ascending=False).reset_index().rename(columns={"_usuario_prod_export": "Confeccionada Por"})
    else:
        casos_export_operador = pd.DataFrame(columns=["Confeccionada Por"] + casos + ["TOTAL"])

    detalle_export_odc = (
        export_prod_cerradas.groupby(["_usuario_prod_export", "_dia_prod_export", "_caso"]).size()
        .reset_index(name="OS Cerradas")
        .rename(columns={"_usuario_prod_export": "Confeccionada Por", "_dia_prod_export": "Fecha", "_caso": "Caso asociado"})
        .sort_values(["Fecha", "Confeccionada Por", "Caso asociado"])
        if not export_prod_cerradas.empty else
        pd.DataFrame(columns=["Confeccionada Por", "Fecha", "Caso asociado", "OS Cerradas"])
    )

    # ---------------------------------------------------------
    # Excel
    # ---------------------------------------------------------
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        tabla_export.to_excel(writer, sheet_name="Resumen", index=False)
        cruz_final_export.to_excel(writer, sheet_name="Antiguedad")

        if not pendientes_export.empty:
            det = pendientes_export.copy()
            export_cols = []
            if col["numero_os"]:
                export_cols.append(col["numero_os"])
            export_cols += [
                col["fecha_creacion"], col["estado"],
                col["sucursal"], col["caso"]
            ]
            if col["localidad"]:
                export_cols.append(col["localidad"])
            if col["tipo_os"]:
                export_cols.append(col["tipo_os"])
            export_cols = list(dict.fromkeys(export_cols))
            det[export_cols + ["antiguedad", "intervalo"]].to_excel(
                writer, sheet_name="Pendientes", index=False
            )

        if not realizados_export.empty:
            realizados_export.to_excel(writer, sheet_name="Realizados", index=False)

        if not base_export.empty:
            base_export.to_excel(writer, sheet_name="Datos período", index=False)

        prod_export_operador.to_excel(writer, sheet_name="Productividad operador", index=False)
        cierres_export_dia.to_excel(writer, sheet_name="Cierres por día", index=False)
        casos_export_operador.to_excel(writer, sheet_name="Casos por operador", index=False)
        detalle_export_odc.to_excel(writer, sheet_name="Operador día caso", index=False)

    st.download_button(
        "⬇️ Descargar análisis completo en Excel",
        data=buffer.getvalue(),
        file_name=(
            f"analisis_OS_{'_'.join(sucursal)}_"
            f"{export_desde.strftime('%Y%m%d')}_"
            f"{export_hasta.strftime('%Y%m%d')}.xlsx"
        ),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="download_excel_export"
    )

    st.caption(
        f"Exportación preparada para {export_desde.strftime('%d/%m/%Y')} "
        f"al {export_hasta.strftime('%d/%m/%Y')} | "
        f"Sucursal/es: {', '.join(sucursal)}"
    )

    st.markdown("---")
    st.subheader("📄 Informe ejecutivo en PDF")
    st.write(
        "Genera un informe PDF con el mismo período elegido arriba, "
        "manteniendo el estilo del informe ejecutivo."
    )

    try:
        pdf_bytes = generar_pdf_informe(export_desde, export_hasta)
        st.download_button(
            "📄 Descargar informe ejecutivo en PDF",
            data=pdf_bytes,
            file_name=(
                f"informe_OS_{'_'.join(sucursal)}_"
                f"{export_desde.strftime('%Y%m%d')}_"
                f"{export_hasta.strftime('%Y%m%d')}.pdf"
            ),
            mime="application/pdf",
            key="download_pdf_informe"
        )
    except Exception as e:
        st.error(f"No se pudo generar el PDF: {e}")

