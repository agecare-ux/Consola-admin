"""Datos de demostración compartidos por los dos seeds.

scripts/seed.py siembra el esquema del prototipo y scripts/seed_canonico.py el
esquema canónico. Los dos usan estos mismos textos para que la demo se vea igual
mire quien la mire, y para que cambiar un chiste o una cuidadora no haya que
hacerlo en dos sitios.

Se mantiene aparte, y no dentro de uno de los seeds, porque el del prototipo
desaparecerá al terminar la migración.
"""

subjects = [
    ("Wearable no sincroniza desde ayer", "wearable_sync", "high", "in_progress", "family"),
    ("No llegan las alertas de medicamentos", "alerts_push", "critical", "in_progress", "caregiver"),
    ("Error al digitalizar receta (OCR)", "medications", "medium", "open", "caregiver"),
    ("Cambio de plan Dorado → Platino", "billing_plans", "medium", "resolved", "family"),
    ("El médico no puede editar el plan", "account_access", "medium", "resolved", "doctor"),
    ("Audio del Director Musical no sube", "other", "low", "resolved", "caregiver"),
]

CATS = ["account_access"] * 32 + ["wearable_sync"] * 24 + ["alerts_push"] * 14 + \
       ["billing_plans"] * 12 + ["medications"] * 9 + ["other"] * 9

HILOS = {
    "wearable_sync": ("El reloj dejó de mandar datos ayer por la tarde y la app sigue "
                      "mostrando la última medición del mediodía.",
                      "Gracias por avisar. Vemos que el dispositivo perdió el vínculo Bluetooth. "
                      "Abre Ajustes › Dispositivos y pulsa «Volver a vincular»; si sigue igual, "
                      "reinicia el reloj manteniendo el botón lateral 10 segundos."),
    "alerts_push": ("No me llegan las notificaciones de medicamentos al teléfono, aunque en la "
                    "app aparecen como programadas.",
                    "Revisamos tu cuenta: las alertas se generan correctamente en nuestro lado. "
                    "El problema está en los permisos del sistema. Entra en Ajustes de Android › "
                    "Aplicaciones › AgeCare › Notificaciones y activa «Permitir alertas»."),
    "medications": ("Al fotografiar la receta, la app reconoce mal las dosis y me pone 2 "
                    "comprimidos donde dice 1.",
                    "El lector de recetas tiene dificultades con la letra manuscrita. "
                    "Puedes corregir la dosis a mano pulsando sobre el medicamento. "
                    "Hemos pasado el caso al equipo del OCR con tu ejemplo."),
    "billing_plans": ("Quiero cambiar del plan Dorado al Platino, pero no encuentro dónde hacerlo.",
                      "El cambio se hace desde Perfil › Mi plan › Cambiar. El cobro se prorratea: "
                      "solo pagas la diferencia de los días que quedan del mes en curso."),
    "account_access": ("El médico que invitamos no puede modificar el plan de medicamentos, "
                       "solo verlo.",
                       "Es el comportamiento previsto: la invitación se envió con rol de lectura. "
                       "Desde Perfil › Círculo de cuidado puedes cambiarle el rol a «Médico», "
                       "que sí permite prescribir."),
    "other": ("Grabé una canción en el Director Musical y no aparece en la galería de la familia.",
              "La sincronización del Director Musical es offline-first: la canción se sube cuando "
              "la tablet vuelve a tener wifi. Ya la vemos en nuestro lado, debería aparecer en "
              "unos minutos."),
}

CHISTES = [
    ("El loro políglota", "—Doctor, mi loro habla tres idiomas. —¿Y cuál prefiere? "
                          "—El silencio, cuando le toca la siesta.", ["humor blanco"]),
    ("La receta de la abuela", "La nieta le pregunta a la abuela por la receta secreta de sus "
                               "empanadas. —Fácil: se hacen con calma y se comen con familia.",
     ["humor blanco", "familia"]),
    ("El reloj de don Ernesto", "—Mi reloj nuevo me avisa de todo. —¿Y qué te dijo hoy? "
                                "—Que me levantara. Le hice caso a la tercera.", ["humor blanco"]),
    ("Memoria de elefante", "—Abuelo, ¿te acuerdas de cuando nos conocimos? —Claro, mijita, "
                            "fue el mismo día que naciste.", ["humor blanco", "familia"]),
    ("El bastón elegante", "Don Manuel se compró un bastón con empuñadura de plata. Dice que "
                           "no lo necesita, pero que combina con todo.", ["humor blanco"]),
    ("Clase de tecnología", "—Abuela, esto se llama «la nube». —¿Y ahí guardan mis fotos? "
                            "—Sí. —Entonces que no llueva.", ["humor blanco", "tecnología"]),
]

NOTICIAS = [
    ("Chile lidera adopción de telemedicina en la región",
     "Un estudio regional destaca el crecimiento de las consultas a distancia entre personas "
     "mayores de 60 años, con foco en el seguimiento de enfermedades crónicas.", ["actualidad", "salud"]),
    ("Caminar 30 minutos al día reduce el riesgo cardiovascular",
     "Una revisión de la Sociedad Chilena de Cardiología confirma que la caminata diaria moderada "
     "mejora la presión arterial y el descanso nocturno en mayores de 65 años.", ["salud", "ejercicio"]),
    ("Nuevo programa municipal de talleres de memoria",
     "Doce comunas de la Región Metropolitana ofrecerán talleres gratuitos de estimulación "
     "cognitiva a partir del próximo mes.", ["actualidad", "comunidad"]),
    ("La música en la tercera edad: qué dice la evidencia",
     "Investigaciones recientes asocian la práctica musical activa con mejoras en el ánimo y "
     "en la memoria de trabajo de adultos mayores.", ["salud", "música"]),
    ("Recomendaciones para la ola de calor",
     "Hidratación frecuente, evitar la exposición al sol entre las 12 y las 17 horas y revisar "
     "la medicación diurética son las claves señaladas por el Minsal.", ["actualidad", "salud"]),
    ("Cómo preparar la casa para prevenir caídas",
     "Retirar alfombras sueltas, mejorar la iluminación de los pasillos e instalar barras de "
     "apoyo en el baño reducen a la mitad el riesgo de caída doméstica.", ["salud", "hogar"]),
    ("Vacunación contra la influenza: fechas y lugares",
     "La campaña comienza este mes para mayores de 65 años en todos los centros de atención "
     "primaria del país.", ["actualidad", "salud"]),
    ("Aplicaciones que ayudan a recordar la medicación",
     "Un repaso a las herramientas disponibles para no olvidar las tomas, con consejos para "
     "configurar recordatorios eficaces.", ["tecnología", "salud"]),
]

CUIDADORAS = [
    ("María Torres", "Providencia", ["Alzheimer", "Movilidad reducida"], ["es"], 3, True, 4.8, 26, "approved"),
    ("Paula Fuentes", "Ñuñoa", ["Posoperatorio"], ["es", "en"], 1, False, None, 0, "pending"),
    ("Rosa Maldonado", "Las Condes", ["Demencia", "Acompañamiento"], ["es"], 4, True, 4.9, 41, "approved"),
    ("Carmen Villalobos", "La Florida", ["Movilidad reducida", "Curaciones"], ["es"], 2, True, 4.6, 18, "approved"),
    ("Ana Sepúlveda", "Maipú", ["Acompañamiento nocturno"], ["es"], 2, True, 4.4, 12, "approved"),
    ("Jorge Cárcamo", "Santiago Centro", ["Rehabilitación", "Movilidad reducida"], ["es"], 3, True, 4.7, 9, "approved"),
    ("Ingrid Kunstmann", "Vitacura", ["Alzheimer", "Terapia ocupacional"], ["es", "de"], 5, False, None, 0, "pending"),
    ("Luis Navarrete", "Puente Alto", ["Acompañamiento"], ["es"], 1, True, 3.2, 7, "suspended"),
]

ARTICULOS = [
    ("Andador plegable con asiento", "Movilidad", "OrtoChile", 64990, "published"),
    ("Pastillero semanal electrónico", "Medicación", "SaludHogar", 29990, "published"),
    ("Barra de apoyo para baño", "Seguridad en el hogar", "OrtoChile", 18990, "published"),
    ("Silla de ducha regulable", "Seguridad en el hogar", "VidaPlena", 42990, "published"),
    ("Tensiómetro digital de brazo", "Monitoreo", "MediCasa", 34990, "published"),
    ("Oxímetro de pulso", "Monitoreo", "MediCasa", 15990, "published"),
    ("Cojín antiescaras", "Cuidado postural", "VidaPlena", 55990, "published"),
    ("Alfombra antideslizante para ducha", "Seguridad en el hogar", "SaludHogar", 9990, "published"),
    ("Lupa con luz LED para lectura", "Vida diaria", "VidaPlena", 12990, "draft"),
    ("Teléfono de teclas grandes", "Comunicación", "MediCasa", 27990, "archived"),
]

PENDIENTES = [
    ("review", "Familia Pérez", "family", {"rating": 5, "text": "Excelente cuidadora, muy puntual y cariñosa."}, None, None, False),
    ("photo", "Usuario Demo 4", "family", {"url": "https://storage.demo/signed/foto123", "album": "Cumpleaños"},
     {"name": "Usuario Demo 7", "role": "caregiver"}, "Contenido que expone datos personales", True),
    ("review", "Familia Soto", "family", {"rating": 2, "text": "Llegó tarde dos veces y no avisó."}, None, None, False),
    ("review", "Familia Ramírez", "family", {"rating": 1, "text": "Pésimo servicio, no la recomiendo para nada."},
     {"name": "Rosa Maldonado", "role": "caregiver"}, "Reseña considerada injusta por la cuidadora", False),
    ("caregiver_profile", "Ingrid Kunstmann", "caregiver",
     {"bio": "Terapeuta ocupacional con 12 años de experiencia en demencias.", "zone": "Vitacura"},
     None, None, False),
    ("chat_message", "Usuario Demo 11", "family",
     {"text": "Te paso el número de cuenta para el pago directo: 000-11-2233."},
     {"name": "Sistema", "role": "system"}, "Posible dato bancario en el chat", True),
    ("photo", "Usuario Demo 19", "caregiver",
     {"url": "https://storage.demo/signed/foto481", "album": "Control de signos"},
     {"name": "Usuario Demo 2", "role": "family"}, "Aparece la receta médica completa", True),
    ("review", "Familia Contreras", "family", {"rating": 4, "text": "Muy buena, aunque le costó el primer día."}, None, None, False),
]
