[README.txt](https://github.com/user-attachments/files/34192951/README.txt)

ANALIZADOR / GESTOR DE ORDENES DE SERVICIO
==========================================

Esta versión incluye:

1. PERIODO ANALIZADO
   - Desde
   - Hasta
   Reemplaza el concepto anterior de "día de corte".

2. CASOS
   - INSTALACION
   - INSTALACION TV
   - TRASLADO DE SERVICIO
   - CLIENTE SIN SERVICIO
   - CAMBIO DE PLAN

3. ESTADOS
   - Realizado = CERRADA
   - Falta hacer = PENDIENTE + CONFIRMADA + POSPUESTA + INICIADA
   - Anulada = ANULADA
   - Otros estados = identificados aparte

4. ANTIGÜEDAD
   Se calcula desde Fecha Creación hasta la fecha HASTA del período.
   Intervalos:
   - 0–2 días
   - 3–5 días
   - 6–10 días
   - 11–15 días
   - 16–20 días
   - 21–25 días
   - 26–30 días
   - Más de 30 días

5. ETAPA 2 - PLANIFICACION
   Se pueden ingresar:
   - Cantidad de cuadrillas
   - Trabajos por cuadrilla/día
   - Días de trabajo por semana
   - Nuevas OS por día

   Calcula:
   - Capacidad diaria
   - Reducción neta diaria
   - Días estimados para eliminar atraso
   - Escenarios con 4, 5 y 6 cuadrillas
   - Objetivos de <=30, <=10, <=7, <=5 y <=2 días

6. PROYECCION DIA A DIA
   Permite simular:
   - Backlog inicial
   - Trabajos diarios
   - Nuevas OS que ingresan
   - Evolución diaria
   - Fecha estimada de eliminación del backlog

7. ANALISIS DE HORAS EXTRAS REALIZADAS
   Permite analizar las horas extras efectivamente realizadas a partir de la fecha y hora de modificación de las órdenes de servicio.

   Considera las siguientes franjas horarias:
   - Lunes a viernes: desde las 16:00.
   - Sábados: desde las 12:00.
   - Domingos: desde las 00:00.

   Incluye:
   - Identificación de órdenes modificadas fuera del horario habitual.
   - Cálculo de minutos y horas extras.
   - Filtros por período, día de la semana, cuadrilla y estado de la orden.
   - Identificación de operadores asociados a cada registro.
   - Asignación editable de operadores a sus respectivas cuadrillas.
   - Identificación de registros sin cuadrilla asignada.
   - Cálculo de horas extras acumuladas por cuadrilla.
   - Cantidad de órdenes con horas extras por cuadrilla.
   - Redondeo de horas extras en intervalos de 30 minutos.

   El resumen de impacto por cuadrilla permite consultar:
   - Órdenes con horas extras.
   - Minutos extras acumulados.
   - Horas extras acumuladas en formato horas:minutos.
   - Horas extras redondeadas en formato horas:minutos.

   También incorpora:
   - Gráficos de horas extras por cuadrilla.
   - Distribución por día de la semana.
   - Distribución por hora de modificación.
   - Detalle de órdenes y horas extras calculadas.
   - Resumen por cuadrilla y día.

8. ANALISIS DE EJECUCION REAL
   Cuando
