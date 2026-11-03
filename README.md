# Reservation Management

Sistema web para **reservar instalaciones deportivas** (pistas, canchas y salas), construido 100 % con Django.

Los clientes (con cuenta) eligen bloques de 1 hora libres en una cuadrícula, pagan un cobro de garantía de prueba y los reservan en una sola solicitud, que se confirma con un único email de resumen. Desde "Mis reservas" cancelan o reprograman sus reservas. Los empleados (gestores) administran pistas y horarios desde el admin de Django.

> **Estado:** el backend está terminado: modelos y reglas, pago de prueba, emails reales con Brevo, permisos, registro y login, páginas de reserva y "Mis reservas", perfil y recuperación de contraseña, traducciones es/en, layout con Tailwind y diseño "Marcador" en SCSS (sitio y admin), límites contra bots, verificación del email y tests. Solo falta el despliegue (ver [Hoja de ruta](#hoja-de-ruta)).

---

## Tabla de contenidos

- [Tecnologías](#tecnologías)
- [Puesta en marcha](#puesta-en-marcha)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Modelo de datos](#modelo-de-datos)
- [Reglas de reserva](#reglas-de-reserva)
- [Cómo funciona una reserva](#cómo-funciona-una-reserva)
- [Notificaciones por email](#notificaciones-por-email)
- [Cuentas: perfil y contraseña](#cuentas-perfil-y-contraseña)
- [Límites contra bots y spam](#límites-contra-bots-y-spam)
- [Roles y permisos](#roles-y-permisos)
- [Zona horaria](#zona-horaria)
- [Idiomas](#idiomas)
- [Frontend: Tailwind + SCSS](#frontend-tailwind--scss)
- [Tests](#tests)
- [Despliegue (Docker)](#despliegue-docker)
- [Decisiones de diseño](#decisiones-de-diseño)
- [Hoja de ruta](#hoja-de-ruta)

---

## Tecnologías

| Área | Tecnología | Para qué |
|---|---|---|
| Lenguaje | Python 3.14 | — |
| Framework | Django 6.1 | Backend, ORM, admin, autenticación, formularios, i18n |
| Base de datos | MySQL 8.4 (en Docker) | Persistencia. Driver: `mysqlclient` |
| Configuración | `django-environ` + `.env` | Secretos y valores por entorno fuera del código |
| Email | Brevo + `django-anymail` | Emails transaccionales por API, desde el dominio propio |
| Imágenes | Pillow | `ImageField` de las pistas |
| Frontend | Templates de Django + **Tailwind CSS 4** (layout) + **SCSS** con Dart Sass (diseño), ambos con ejecutables standalone, sin Node + JavaScript sin frameworks | Tailwind: estructura y espacios. SCSS: colores, tipografía y componentes, también del admin. El JS solo mejora la experiencia (menú en el celular, cerrar mensajes, seleccionar todo, pop-up, "Procesando pago…", búsqueda de clientes) |
| Servidor de producción | Gunicorn (+ Nginx en el droplet) | Ejecutar Django en producción |
| Tests | pytest + pytest-django | Tests unitarios y de integración |
| Linting / formato | Ruff | Detectar errores y mantener un estilo uniforme |
| Depuración | django-debug-toolbar | Ver consultas SQL y tiempos (solo en desarrollo) |

## Puesta en marcha

Requisitos: Python 3.12+, Docker y las librerías de cliente de MySQL (`mysql_config`).

```bash
# 1. Entorno virtual y dependencias de desarrollo
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Variables de entorno
cp .env.example .env          # y completar SECRET_KEY y contraseñas

# 3. Base de datos MySQL
docker compose up -d

# 4. Tablas y datos iniciales (incluye el grupo "Gestores") + tabla del caché (límites)
python manage.py migrate
python manage.py createcachetable

# 5. Tu cuenta de administrador
python manage.py createsuperuser

# 6. Traducciones (genera los .mo a partir de los .po)
python manage.py compilemessages --ignore=.venv

# 7. Arrancar
python manage.py runserver    # http://127.0.0.1:8000/es/
```

### Variables de `.env`

| Variable | Ejemplo | Descripción |
|---|---|---|
| `DEBUG` | `True` | Modo depuración (solo desarrollo) |
| `SECRET_KEY` | — | Clave secreta de Django |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Dominios permitidos |
| `TIME_ZONE` | `America/Bogota` | Zona horaria **de respaldo** (la real se elige en el admin) |
| `LANGUAGE_CODE` | `es` | Idioma por defecto |
| `CSRF_TRUSTED_ORIGINS` | `https://midominio.com` | Orígenes de confianza en producción |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_ROOT_PASSWORD` | — | Conexión a MySQL (Docker los usa al crear la base) |
| `SEND_REAL_EMAILS`, `BREVO_API_KEY`, `DEFAULT_FROM_EMAIL`, `SITE_URL` | — | Envío de emails (ver [Notificaciones por email](#notificaciones-por-email)) |
| `USE_X_FORWARDED_FOR` | `False` | `True` **solo** en producción detrás de Nginx: toma la IP real del visitante para los límites |

### Cuentas staff

El registro público (`/es/accounts/signup/`) **solo crea clientes**. Las cuentas staff las crea el superuser desde el admin:

1. **Users → Add user**: usuario, **email** (obligatorio y único) y contraseña.
2. En la ficha del usuario, marcar **Staff status** (para entrar a `/admin/`). **Nunca** *Superuser status*.
3. Asignar un grupo, por ejemplo **"Gestores"**, o un grupo creado a mano con los permisos que hagan falta.

⚠️ No se deben dar los permisos de **user** (add/change/delete), **group** ni **permission**: con ellos una cuenta podría darse más permisos a sí misma o volverse superuser.

---

## Estructura del proyecto

```
reservation_managment/
├── config/                         # Proyecto Django (configuración global)
│   ├── settings/
│   │   ├── base.py                 # Settings compartidos (apps, BD, i18n, static, auth)
│   │   ├── dev.py                  # Desarrollo: DEBUG, debug toolbar, logs en consola
│   │   └── prod.py                 # Producción: HTTPS, cookies seguras, HSTS
│   ├── urls.py                     # URLs raíz (admin, idioma, app)
│   ├── wsgi.py / asgi.py           # Entrada para Gunicorn (usa settings.prod)
│
├── reservation_managment/          # La app (toda la lógica del negocio)
│   ├── models.py                   # Modelos y reglas de reserva
│   ├── emails.py                   # Emails de las reservas (Brevo)
│   ├── management/commands/        # send_test_email, send_pending_emails
│   ├── payments.py                 # Cobro (dummy: siempre aprobado)
│   ├── ratelimit.py                # Límites contra bots (por IP y por cuenta)
│   ├── verification.py             # Enlace firmado para verificar el email
│   ├── middleware.py               # Activa la zona horaria configurada
│   ├── admin.py                    # Panel de administración
│   ├── forms.py                    # Registro y perfil
│   ├── views.py                    # Registro, perfil, reservar, pagar, mis reservas
│   ├── urls.py                     # URLs de la app
│   ├── migrations/
│   │   ├── 0001–0002, 0004         # Tablas (generadas con makemigrations)
│   │   ├── 0003                    # Datos: crea el grupo "Gestores"
│   │   ├── 0005                    # Datos: Gestores pueden ver solicitudes
│   │   ├── 0006                    # Pago de la solicitud (monto y referencia)
│   │   ├── 0007                    # Quita la notificación "solicitud cancelada"
│   │   ├── 0008                    # Idioma preferido del usuario
│   │   ├── 0009                    # Email verificado (los usuarios existentes quedan verificados)
│   │   └── 0010                    # Email obligatorio y único
│   └── tests/
│       ├── conftest.py             # Fixtures compartidos
│       ├── test_models.py          # Reglas de reserva y zona horaria
│       ├── test_booking_requests.py# Concurrencia y solicitudes de varios bloques
│       ├── test_notifications.py   # Notificaciones y emails
│       ├── test_security.py        # POST falsificados y permisos de Gestores
│       └── test_abuse.py           # Verificación del email y límites contra bots
│
├── templates/                      # Templates de proyecto
│   ├── base.html                   # Layout: navegación, idioma, mensajes
│   ├── admin/base_site.html        # Carga la paleta en el admin de Django
│   ├── home.html
│   ├── 404.html / 403.html         # Páginas de error (se ven con DEBUG=False)
│   ├── 429.html                    # "Demasiados intentos" (límites)
│   ├── emails/                     # Textos de los emails de reservas
│   ├── includes/form_fields.html   # Campos de un formulario, apilados
│   ├── registration/               # login, signup, profile, cambio y recuperación de contraseña
│   └── bookings/                   # book (selector), checkout (pago), my_bookings, reschedule
├── static/
│   ├── src/input.css               # Tailwind: solo layout
│   ├── scss/                       # Diseño (ver Frontend):
│   │   ├── _palette.scss           #   colores, fuentes y esquinas (un solo lugar)
│   │   ├── _tokens.scss, _mixins.scss, _base.scss
│   │   ├── components/             #   header, slots, bookings, feedback
│   │   ├── site.scss               #   → css/site.css
│   │   └── admin.scss              #   → css/admin.css
│   ├── css/                        # main.css (Tailwind), site.css y admin.css (Sass). Generados y minificados: no editar
│   ├── img/tennis-ball-favicon.svg # Favicon (sitio y admin)
│   └── js/                         # nav, messages, slot_picker, checkout, customer_search, clock
├── bin/                            # tailwindcss y dart-sass/ (descargados, fuera de git)
├── media/                          # Archivos subidos (imágenes de pistas)
├── locale/es/                      # Traducción al español: django.po (fuente) y django.mo (compilado)
│
├── docker-compose.yml              # MySQL 8.4 para desarrollo
├── Dockerfile, .dockerignore       # Imagen de producción (Django + Gunicorn)
├── deploy/                         # Producción: compose, scripts de despliegue y Nginx
├── pyproject.toml                  # Configuración de pytest y Ruff
├── requirements.txt                # Dependencias de producción
├── requirements-dev.txt            # + herramientas de desarrollo
├── .env.example                    # Plantilla de variables de entorno
└── manage.py
```

---

## Modelo de datos

```
SiteSettings (una sola fila: la zona horaria)

ResourceType ──< Resource ──< Availability        (tipo → pista → horario semanal)
                    │
User ──< BookingRequest ──< Booking >── Resource   (solicitud → reservas)
  │            │               │
  └──────< Notification >──────┘                   (sobre una reserva O una solicitud)
```

| Modelo | Qué representa | Campos clave |
|---|---|---|
| `User` | Usuario (modelo propio, hereda de `AbstractUser`) | `email` **obligatorio y único**, + `phone`, `language` (idioma de sus emails), `email_verified` |
| `ResourceType` | Categoría: "Pista de tenis", "Sala" | `name` (único) |
| `Resource` | Una pista o sala concreta | `resource_type`, `capacity`, `location`, `image`, `is_active` |
| `Availability` | Horario semanal de apertura | `resource`, `weekday` (0 = lunes), `start_time`, `end_time` |
| `BookingRequest` | Una solicitud: los bloques reservados juntos y su pago | `user`, `amount_paid`, `payment_reference`, `created_at` |
| `Booking` | Una reserva | `user`, `resource`, `booking_request` (opcional), `start`, `end`, `status` |
| `Notification` | Registro de cada email enviado | `user`, `booking` **o** `booking_request`, `kind`, `emailed_at` |
| `SiteSettings` | Configuración global (singleton) | `time_zone` |

---

## Reglas de reserva

Las reglas viven en el **modelo** (`Booking.clean()`), y `Booking.save()` las ejecuta siempre. Por eso se cumplen sin importar por dónde entre la reserva: admin, páginas, shell o tests.

| # | Regla | Ejemplo válido | Ejemplo inválido |
|---|---|---|---|
| 1 | Inicio y fin en **:00 o :30** | 08:30–09:30 | 08:15–09:15 |
| 2 | Duración **mínima de 1 hora** | 10:00–11:00 | 10:00–10:30 |
| 3 | Duración en **horas completas** (múltiplo de 60 min) | 08:30–11:30 (3h) | 10:00–11:30 (1h30) |
| 4 | **Sin duración máxima** (el límite es el cierre) | 08:00–22:00 | — |
| 5 | **Dentro del horario** de apertura, en un solo día | 08:00–09:00 si abre a las 8 | 21:00–23:00 si cierra a las 22 |
| 6 | **Sin solapamiento** con otra reserva confirmada de la misma pista | 18–20 y 20–21 | 18–20 y 19–21 |
| 7 | **En el futuro** (al crear, reagendar o volver a confirmar) | mañana | ayer |
| 8 | Ventana de **7 días**: hoy + los 6 siguientes, también para el superuser | hoy + 6 | hoy + 7 |
| 9 | Una reserva **ya empezada no se puede mover** | — | mover una de ayer |
| 10 | Solo pistas **activas** (`is_active`) | — | pista desactivada |
| 11 | Una reserva **cancelada libera** su horario | — | — |

**Horarios de apertura (`Availability`):**
- Inicio y fin en :00 o :30.
- Duración en horas completas: 08:30–21:30 ✅ · 08:30–22:00 ❌.
- Sin rangos solapados el mismo día.
- Dos rangos que se tocan (08–14 y 14–20) cuentan como uno solo (08–20).

**Concurrencia:** antes de validar y guardar, `Booking.save()` bloquea la fila de la pista con `select_for_update()` dentro de una transacción. Si dos personas reservan el mismo horario a la vez, la segunda espera y luego recibe "ya está ocupado". MySQL no puede impedir solapamientos de rangos por sí solo, por eso se hace así.

---

## Cómo funciona una reserva

### 1. Bloques libres: `Resource.available_slots(date)`
Para una fecha, genera bloques de **1 hora** desde la hora de apertura (08:00, 09:00… o 08:30, 09:30…) y **oculta**:
- los bloques ocupados por reservas confirmadas,
- los que ya empezaron (hoy a las 10:15, el primero es 11:00),
- los días cerrados o fuera de la ventana de 7 días,
- todo, si la pista está inactiva.

### 2. Solicitud: `BookingRequest.create_from_slots(user, slots)`
El cliente envía los bloques elegidos como pares `(pista, inicio)`. Pueden ser **varias pistas y varios días**. El proceso:

1. Abre una transacción y **bloquea** las pistas involucradas.
2. **Recalcula** qué bloques siguen libres. Nunca confía en lo que envió el navegador.
3. Separa los bloques en **confirmables** y **omitidos**. Un bloque se omite si otro usuario lo tomó entre medio, si es inventado o si está fuera de horario o de la ventana.
4. **Une** los bloques seguidos de la misma pista: 09:00 + 10:00 + 11:00 → una reserva de 09:00 a 12:00.
5. Guarda cada reserva con `save()` normal, así que se aplican todas las reglas.
6. Crea **una** notificación de resumen y devuelve `confirmed` + `omitted`.

Si nada estaba disponible, no se crea la solicitud ni se envía ningún email.

### 3. Las páginas (hace falta una cuenta para reservar)

| Paso | URL | Qué pasa |
|---|---|---|
| 1. Elegir | `/bookings/new/` | Los 7 días con **solo los bloques libres**, filtro por tipo y **"Seleccionar todo"** por pista y día |
| 2. Pagar | `/bookings/checkout/` | Resumen con los bloques ya unidos y un cobro de garantía de **1.00 USD** por solicitud. Al pulsar **Pagar** se muestra "Procesando pago…" y luego "Pago aprobado" |
| 3. Resultado | vuelve a `/bookings/new/` | **Pop-up** con las confirmadas y, por cada bloque omitido: *"esta reserva ya no se encuentra disponible, por lo cual se omitió"* |

- La disponibilidad se **recalcula al pagar**, porque alguien pudo tomar un bloque mientras tanto. Si no se confirma nada, **no se cobra**.
- Patrón **Post/Redirect/Get**: recargar la página del resultado no reserva ni cobra dos veces.

**Pago dummy:** `payments.py` no se conecta a ninguna pasarela ni pide datos de tarjeta. Siempre aprueba y devuelve una referencia falsa (`DUMMY-XXXXXXXX`), que se guarda en la solicitud junto con el monto. Para usar una pasarela real, como Stripe, solo hay que cambiar `payments.charge()`.

**Reservar a nombre de un cliente:** en el admin, **Bookings → Add** abre el mismo selector con un campo **"Book for customer"**. Solo lo ve el staff con el permiso *Can add booking*: el superuser o una cuenta a la que se le dé. Los Gestores no lo tienen.

El cliente se **busca por email**, no por nombre: los nombres se repiten y el email es único. Al escribir al menos 3 letras, el servidor devuelve hasta 10 coincidencias (`/bookings/customers/?q=`), con el formato `email — Nombre`. El navegador nunca recibe la lista completa de usuarios. Solo aparecen **clientes** (usuarios activos sin *Staff status*). Si se escribe algo y no se elige a nadie de la lista, el formulario no se envía, para no reservar por error a nombre propio.

### 4. Mis reservas: `/bookings/`
| Acción | Cómo |
|---|---|
| Ver | Solo las reservas **de la cuenta que inició sesión**: próximas e historial |
| Cancelar **una** reserva | Botón con POST. Envía el email de cancelación |
| Reprogramar | Elegir un nuevo inicio entre los libres de la misma pista, con la misma duración (`Booking.reschedule_options()`). Envía el email de reprogramación |

Cada vista busca la reserva con `user=request.user`. Si alguien cambia el id en la URL o envía un POST a mano con una reserva ajena, recibe **404**, como si no existiera. Solo se puede cancelar o reprogramar una reserva confirmada que aún no empezó.

---

## Notificaciones por email

Cada email queda registrado como una `Notification`. El email sale con `transaction.on_commit()`, es decir, **solo después** de que los datos se guardaron. Si la transacción falla, no se envía nada.

| Situación | Tipo (`kind`) | Emails |
|---|---|---|
| Se crea una solicitud | `request_confirmed` | **1**, con la lista de reservas confirmadas |
| Se cancela una reserva | `booking_cancelled` | 1 |
| Se reagenda una reserva | `booking_rescheduled` | 1 |
| Una reserva cancelada se vuelve a confirmar (en el admin) | `booking_confirmed` | 1 |

Las reservas que se crean **como parte de una solicitud** no mandan email individual: las cubre el resumen. Las cancelaciones y reprogramaciones son siempre de una en una, cada una con su email.

### Envío real con Brevo
Los emails salen por la **API HTTP de Brevo** con [`django-anymail`](https://anymail.dev), no por SMTP:
- DigitalOcean bloquea los puertos SMTP; la API usa HTTPS (443).
- La API key **solo puede enviar**: si se filtra, no da acceso a ningún buzón. El MFA del correo de Microsoft sigue intacto.

| Variable de `.env` | Qué es |
|---|---|
| `SEND_REAL_EMAILS` | `False`: los emails se imprimen en la consola de `runserver`. `True`: se envían por Brevo |
| `BREVO_API_KEY` | API key de Brevo con permiso **solo de envío transaccional**. Una para desarrollo y otra para producción |
| `DEFAULT_FROM_EMAIL` | Remitente, **verificado en Brevo**: `Reservation Management <no-reply@santiagoboada.dev>` |
| `SITE_URL` | Dirección pública del sitio, para los enlaces de los emails (en producción, `https://…`) |

**En Brevo:** dominio autenticado (DKIM, DMARC y `brevo-code` en el DNS de **Cloudflare**, que es quien maneja el DNS del dominio), remitente verificado e IP del servidor en *Security → Authorised IPs*.

**Probar la configuración:**
```bash
python manage.py send_test_email tu@correo.com
```

**Qué emails existen** (todos en `templates/emails/` y en el **idioma del cliente**, aunque reserve el staff por él):
| Email | Contenido |
|---|---|
| Solicitud confirmada | Reservas confirmadas, monto y referencia del pago, enlace a "Mis reservas" |
| Reserva confirmada / cancelada / reprogramada | La reserva y el enlace a "Mis reservas" |
| Verificar el email | Enlace firmado (1 día) |
| Recuperar la contraseña | Enlace de un solo uso (1 hora) |

**Si Brevo falla**, la reserva **no se pierde**: el error queda en el log y la notificación queda con `emailed_at` vacío. Para reintentar los pendientes (se puede programar con cron cada pocos minutos):
```bash
python manage.py send_pending_emails
```

---

## Cuentas: perfil y contraseña

| Página | URL | Qué hace |
|---|---|---|
| Perfil | `/accounts/profile/` | Editar nombre, apellido, teléfono, email e idioma preferido. **Cambiar el email exige la contraseña actual** |
| Cambiar contraseña | `/accounts/password/change/` | Vista de Django; pide la contraseña actual |
| ¿Olvidaste tu contraseña? | `/accounts/password/reset/` | Envía un enlace de **un solo uso que expira en 1 hora** (`PASSWORD_RESET_TIMEOUT`) |

- **¿Por qué el email pide contraseña?** El email es adonde llegan los enlaces para recuperar la contraseña. Si alguien deja la sesión abierta, otra persona podría cambiar el email y luego quedarse con la cuenta.
- **Recuperar contraseña:** la pantalla dice lo mismo exista o no el email, para no revelar quién tiene cuenta. Solo se envía el email si la cuenta existe.
- **Idioma preferido:** se guarda al registrarse (el idioma en que se registró) y se cambia en el perfil. Al guardar, la página vuelve en ese idioma.
- **Notificaciones por SMS: "Próximamente".** Aparece en el perfil como opción desactivada. No está construida: se pensó como un canal más, y `Notification` ya registra qué se notificó, así que se podría agregar después.

---

## Límites contra bots y spam

Para que la página no se use como herramienta de bots (crear cuentas en masa, mandar emails a terceros, adivinar contraseñas u ocupar todas las pistas), hay **varias capas**. Solo por IP no basta: los bots cambian de IP, y muchas personas reales pueden compartir una (una universidad, una oficina).

### 1. Verificación del email al registrarse
- Al registrarse, el cliente recibe un **enlace firmado** (`verification.py`). Hasta abrirlo, **no puede reservar** (las páginas de reserva le muestran "Verifica tu correo" y un botón para reenviar el enlace).
- Así nadie puede registrarse con el email **de otra persona** y llenarle la bandeja con emails de reservas.
- El enlace dura **1 día** (`EMAIL_VERIFICATION_MAX_AGE`) y lleva el email dentro: si el cliente cambia su email, el enlace viejo deja de servir.
- Cambiar el email en el perfil vuelve a pedir la verificación.
- El staff no necesita verificar (son empleados). Los usuarios que existían antes de esta función quedaron verificados (migración `0009`).

### 2. Límites (`ratelimit.py`)
| Acción | Límite | Al superarlo |
|---|---|---|
| Crear cuentas | **5 por IP por hora** (solo cuentan las creadas) | Página **429** |
| Login fallido | **10 por usuario + IP cada 15 min** | 429, **incluso con la contraseña correcta**: así se frena el adivinar contraseñas |
| "¿Olvidaste tu contraseña?" | **3 por email por hora** y **10 por IP por hora** | Por email: la pantalla de siempre, pero **no se envía nada** (no revela nada). Por IP: 429 |
| Reenviar el enlace de verificación | **3 por cuenta por hora** | 429 |
| Solicitudes de reserva | **10 por cuenta por día** (contadas en la base de datos) | Mensaje de error. El staff que reserva a nombre de clientes no tiene este límite |

- El login se limita por **usuario e IP a la vez**: un atacante no puede bloquear la cuenta de alguien desde otro lugar.
- Los contadores viven en el **caché de Django**, en una tabla de MySQL (`createcachetable`), compartida por todos los procesos de Gunicorn. No hace falta Redis. Las claves se guardan **con hash**: no quedan emails ni IPs en texto plano.
- Los números se cambian en un solo lugar, al inicio de `ratelimit.py`.

### 3. Campo trampa (honeypot)
El formulario de registro tiene un campo `website` **invisible** para las personas (fuera de la pantalla y sin foco con el teclado). Los bots rellenan todos los campos: si llega con valor, no se crea la cuenta y se responde como si todo hubiera salido bien.

### 4. La IP real en producción
Detrás de Nginx, todas las peticiones llegan con la IP de Nginx. Con `USE_X_FORWARDED_FOR=True` se usa la IP que Nginx agrega en `X-Forwarded-For`. **Solo** se activa detrás de tu propio Nginx: sin él, cualquiera podría enviar esa cabecera falsa y tener una "IP nueva" en cada petición.

---

## Roles y permisos

| Rol | Cómo se crea | Qué puede hacer |
|---|---|---|
| **Superuser** | `createsuperuser` (solo el dueño del proyecto) | Todo, incluida la zona horaria y reservar a nombre de clientes |
| **Gestor** (empleado) | El superuser crea el usuario en el admin, marca *Staff status* y lo agrega al grupo **"Gestores"** | Ver y editar tipos y pistas; gestionar horarios; **ver** reservas, solicitudes y notificaciones |
| **Cliente** | Registro público (`/es/accounts/signup/`) | Reservar (después de **verificar su email**) y gestionar **sus propias** reservas. No entra al admin |
| Staff con *Can add booking* (opcional) | El superuser le da ese permiso a una cuenta staff | Reservar a nombre de clientes desde **Bookings → Add**. Los Gestores **no** lo tienen |

**Permisos del grupo "Gestores"** (creados por las migraciones de datos `0003` y `0005`):

| Modelo | Ver | Crear | Editar | Borrar |
|---|:-:|:-:|:-:|:-:|
| ResourceType | ✅ | ❌ | ✅ | ❌ |
| Resource | ✅ | ❌ | ✅ | ❌ |
| Availability | ✅ | ✅ | ✅ | ✅ |
| Booking | ✅ | ❌ | ❌ | ❌ |
| BookingRequest | ✅ | ❌ | ❌ | ❌ |
| Notification | ✅ | ❌ | ❌ | ❌ |
| SiteSettings, User | ❌ | ❌ | ❌ | ❌ |

`BookingRequest` y `Notification` son de **solo lectura para todos** en el admin, porque las crea el sistema.

**Seguridad del registro:**
- El formulario solo acepta sus campos declarados, así que no se puede enviar `is_staff`.
- **Un email = una cuenta.** El email es obligatorio y único **en el modelo** (`User.email`, índice `UNIQUE` en MySQL), así que vale para el registro, el perfil, el admin, `createsuperuser` y el shell, e incluso si dos personas se registran con el mismo email en el mismo instante. Se guarda en minúsculas, y el cotejamiento `utf8mb4_unicode_ci` de MySQL compara sin distinguir mayúsculas: `Ana@x.com` y `ana@x.com` son el mismo.
- Las contraseñas pasan los validadores de Django.
- El logout es solo por POST.

**Seguridad de las reservas:**
- Todas las páginas de reserva exigen haber iniciado sesión.
- Cancelar, reprogramar y pagar solo se hacen con POST y token CSRF.
- Una reserva ajena da **404**, aunque se cambie el id en la URL.
- Elegir cliente o buscar clientes sin el permiso *Can add booking* da **403**.
- El servidor recalcula los bloques libres al pagar: nunca confía en lo que envía el navegador.

---

## Zona horaria

- Las fechas se **guardan en UTC** (`USE_TZ = True`).
- Se **interpretan y muestran** en la zona del lugar de las pistas, que se elige en el admin: **Site settings → Time zone** (solo superuser). Por defecto es `America/Bogota`.
- Todas las reglas usan esa zona **explícitamente** (`get_business_timezone()`), así que se comportan igual en una petición web, en el shell o en los tests.
- `BusinessTimezoneMiddleware` activa esa zona en cada petición, para que el admin y las páginas muestren la hora local.

⚠️ Cambiar la zona con reservas ya creadas cambia **cómo se muestran**: es el mismo instante, visto desde otra zona. La zona se configura al inicio.

---

## Idiomas

El sitio funciona en **español e inglés**:
- URLs con prefijo (`/es/…`, `/en/…`) y un selector de idioma en la cabecera.
- En el código, los textos están en inglés y marcados con `gettext_lazy` / `{% translate %}`.
- **Español: 100 % traducido** (páginas, errores de las reglas, nombres en el admin, emails y textos del JavaScript). Los textos de Django (admin, formularios de contraseña) ya vienen traducidos por Django.
- No hay `.po` de inglés: los textos originales ya están en inglés, así que `/en/` los muestra tal cual.
- Los textos que muestra el **JavaScript** vienen de atributos `data-*` en los templates, así que se traducen como el resto.
- Los números y las fechas siguen el idioma: en español el precio es `1,00 USD` y los días, "Lunes 2 noviembre".

Al agregar o cambiar textos:
```bash
python manage.py makemessages -l es --ignore=.venv --ignore=bin --ignore=static
# traducir los msgstr nuevos en locale/es/LC_MESSAGES/django.po
python manage.py compilemessages --ignore=.venv
```

---

## Frontend: Tailwind + SCSS

**Estado:** layout y diseño aplicados en el sitio y en el admin. El estilo es **"Marcador"**: azul marino y ámbar, en oscuro, como el marcador de un estadio.

### Quién hace qué
| Herramienta | Archivo | Se encarga de |
|---|---|---|
| **Tailwind CSS 4** | `static/src/input.css` → `css/main.css` | **Layout:** estructura, espacios, columnas, responsive (clases en los templates) |
| **SCSS** (Dart Sass) | `static/scss/site.scss` → `css/site.css` | **Diseño del sitio:** colores, tipografía, botones, bloques, pills, cabecera |
| **SCSS** (Dart Sass) | `static/scss/admin.scss` → `css/admin.css` | **Diseño del admin** |

**¿Por qué dos herramientas?** Tailwind v4 no está hecho para preprocesadores: no lee `.scss` y `@apply` no funciona dentro de SCSS. Por eso son dos compilaciones separadas. Las dos encajan así:
- **Una sola paleta.** Los colores se definen solo en `_palette.scss`. `_tokens.scss` los escribe como variables CSS (`--bg`, `--mark`…) y las pocas clases de color de Tailwind (`border-line`, `bg-surface`, `bg-band`) apuntan a esas variables con `@theme inline`.
- **Capas CSS.** `site.css` mete sus reglas en las mismas capas que Tailwind (`@layer base` y `@layer components`). Así, si una clase de layout de un template y el SCSS tocan la misma propiedad, gana la clase del template.

### Qué aporta SCSS
| Recurso | Dónde | Para qué |
|---|---|---|
| **Map** + `@each` | `_palette.scss`, `_tokens.scss` | La paleta es un mapa; un bucle genera todas las variables CSS |
| **Función** `color()` | `_palette.scss` | `color('mark')` → `var(--mark)` |
| **Mixins** | `_mixins.scss` | `caps`, `numbers`, `stripe`, `button`, `focus-ring`: el estilo Marcador reutilizado en el sitio y en el admin |
| **Parciales** y `@use` | `components/_*.scss` | Un archivo por componente |
| `meta.load-css` | `site.scss` | Carga cada parcial dentro de su capa CSS |

### El estilo "Marcador"
| Color | Uso |
|---|---|
| Azul marino (`bg`, `surface`, `raised`, `band`) | Fondos y la cabecera, que es el "marcador" |
| Azul claro (`accent`, `key`) | Botones, bloques seleccionados, títulos y enlaces |
| **Ámbar** (`mark`) | El reloj, la línea bajo la cabecera, las franjas de las reservas y lo seleccionado |
| Gris azulado (`muted`) | Textos pequeños y secundarios |

- **Reloj** en la cabecera, del sitio y del admin: la hora local de las canchas (zona horaria de *Configuración del sitio*). Lo actualiza `static/js/clock.js`.
- **Horas en monoespaciada** (IBM Plex Mono), para que queden en columna. El texto va en **Archivo**. Las dos fuentes se cargan de Google Fonts.
- Esquinas rectas, franja ámbar a la izquierda de cada reserva y estados en etiquetas en mayúsculas.
- **Admin:** su HTML es de Django y no admite clases, así que `admin.scss` cambia las **variables CSS** con las que Django construye el admin (`--body-bg`, `--primary`, `--link-fg`…) y añade los detalles del Marcador. Lo carga `templates/admin/base_site.html`. Solo tiene versión oscura, por eso se oculta su botón de tema claro/oscuro.

### Compilar
Los dos son **ejecutables standalone, sin Node.js**, y viven en `bin/` (fuera de git).

```bash
# Descargar (una vez; Linux x64)
mkdir -p bin
curl -sSLo bin/tailwindcss https://github.com/tailwindlabs/tailwindcss/releases/download/v4.3.3/tailwindcss-linux-x64
chmod +x bin/tailwindcss
curl -sSL https://github.com/sass/dart-sass/releases/download/1.105.2/dart-sass-1.105.2-linux-x64.tar.gz | tar -xz -C bin/

# Mientras desarrollas (cada uno en su terminal; recompilan al guardar)
./bin/tailwindcss -i static/src/input.css -o static/css/main.css --watch
./bin/dart-sass/sass --watch static/scss/site.scss:static/css/site.css static/scss/admin.scss:static/css/admin.css --no-source-map

# Para producción
./bin/tailwindcss -i static/src/input.css -o static/css/main.css --minify
./bin/dart-sass/sass static/scss/site.scss:static/css/site.css static/scss/admin.scss:static/css/admin.css --style=compressed --no-source-map
```

- Se editan `static/src/` y `static/scss/`, **nunca** los archivos de `static/css/`.
- Los CSS generados sí van en git, **minificados** (comandos de producción), para que el proyecto funcione sin compilar nada. Las fuentes (`static/src/`, `static/scss/`) también van, para seguir editando el diseño.
- **Sin JavaScript todo funciona**: el menú queda abierto, los bloques se marcan uno por uno, el pop-up se ve igual, el pago se envía directamente y el reloj muestra la hora a la que cargó la página.

| Página | Layout |
|---|---|
| Todas | Cabecera con menú (☰ en el celular), contenido centrado y pie de página |
| Cuenta (login, registro, perfil, contraseña) | Una columna centrada |
| Reservar | Un bloque por día; bloques en cuadrícula de 2 columnas en el celular y hasta 6 en pantalla grande; botón de pago fijo abajo |
| Pago | Resumen y pago lado a lado en escritorio; una columna en el celular |
| Mis reservas | Filas tipo tabla en escritorio; tarjetas en el celular |

---

## Tests

```bash
pytest                    # todos
pytest -v                 # con el nombre de cada test
pytest -k overlap         # solo los que contienen "overlap"
pytest --setup-show       # ver qué fixtures prepara cada test
```

Los tests corren contra **MySQL**, el mismo motor que producción, en una base temporal `test_reservation_managment` que se crea y se borra sola. El usuario de MySQL necesita permisos sobre esa base.

**Criterio:** solo se prueba lo que no se puede comprobar a mano usando la página: varios usuarios a la vez, reglas que dependen de la hora actual, peticiones falsificadas, transacciones y zona horaria.

| Archivo | Cubre |
|---|---|
| `test_models.py` | Solapamientos, reglas que dependen de "ahora" (pasado, ventana de 7 días, ya empezó) y zona horaria |
| `test_booking_requests.py` | **3 usuarios reservando el mismo bloque a la vez** (solo uno gana), bloques omitidos, unir bloques, un solo email con solo las confirmadas |
| `test_notifications.py` | Reagendar no es una nueva confirmación, el email solo sale después del commit, **un email que falla no deshace la reserva** y se reintenta, y sale **en el idioma del cliente** aunque reserve el staff |
| `test_abuse.py` | Sin verificar no se reserva (aunque sea con POST a mano), el enlace de verificación (válido, falsificado y de un email viejo), límites de registro, login, recuperación de contraseña y reservas por día, campo trampa, IP falsa en `X-Forwarded-For` |
| `test_security.py` | POST falsificados: registro (nunca crea staff), Gestor en el admin, cancelar o reprogramar reservas ajenas (404), reservar a nombre de otro (403), buscar clientes sin ser staff (403), cambiar el email del perfil sin la contraseña; email único en la base de datos aunque cambien las mayúsculas; permisos exactos de Gestores |

Los fixtures compartidos (`user`, `resource`, `at`, `make_booking`, `make_resource`, `freeze_now`…) están en `tests/conftest.py`.

**Linting:**
```bash
ruff check .              # buscar problemas
ruff format .             # dar formato
```

---

## Despliegue (Docker)

Producción en un VPS Ubuntu 26.04 en **`vps.santiagoboada.dev`**. Cada proyecto del servidor es un **stack de Docker Compose aislado**: su propia red, su base de datos y sus volúmenes. Un solo **Nginx** en el servidor recibe el tráfico y gestiona el SSL de todos los dominios.

```
Internet → Nginx (80/443, SSL con certbot)
             ├─ /static/, /media/  → archivos en /srv/reservas/ (los sirve Nginx)
             └─ /                  → 127.0.0.1:8001 → contenedor web (Gunicorn) → contenedor db (MySQL, sin puertos)
```

| Archivo | En el servidor | Qué es |
|---|---|---|
| `Dockerfile` | Se construye desde `/srv/reservas/app/` | Imagen en dos etapas: compila `mysqlclient` y luego copia solo el resultado. Corre como usuario `app` (uid 10001), nunca como root |
| `deploy/docker-compose.prod.yml` | `/srv/reservas/docker-compose.yml` (root) | `web` + `db`. El puerto solo en `127.0.0.1` (Docker se salta el firewall); MySQL sin puertos; límites de memoria |
| `deploy/post-deploy.sh` | `/srv/reservas/post-deploy.sh` (root) | `migrate`, `createcachetable`, `collectstatic`, `check --deploy` |
| `deploy/deploy-project` | `/usr/local/sbin/deploy-project` (root) | Reconstruye y reinicia un proyecto. Es **lo único** que `deploy` puede ejecutar con `sudo` |
| `deploy/nginx/vps.santiagoboada.dev.conf` | `/etc/nginx/sites-available/` | Proxy hacia Gunicorn + archivos estáticos. Certbot le añade HTTPS |

**Usuarios del servidor (mínimo privilegio):**
| Usuario | SSH | Permisos |
|---|---|---|
| `root` | ❌ | Solo con `sudo -i` desde `zarvi`, o por la consola de GoDaddy |
| `zarvi` | Llave propia | Administración con `sudo` |
| `deploy` | Llave propia (otra) | Sube el código a `/srv/reservas/app/` y ejecuta `sudo deploy-project reservas`. **Sin sudo general y fuera del grupo `docker`** (estar en ese grupo equivale a ser root). No puede leer el `.env` ni cambiar el compose, que son de root |

**Seguridad del servidor:** SSH solo con llave (sin contraseñas, sin root, solo `zarvi` y `deploy`), firewall `ufw` con 22 (con límite de intentos), 80, 443 y 2224 (agente de GoDaddy), y actualizaciones de seguridad automáticas.

**Qué no va en git y se copia a mano:** el `.env` de producción (`/srv/reservas/.env`, root 600) y las fotos de las canchas (`/srv/reservas/media/`).

**Desplegar una nueva versión:**
```bash
rsync -az --delete --exclude-from=deploy/rsync-exclude ./ deploy@vps.santiagoboada.dev:/srv/reservas/app/
ssh deploy@vps.santiagoboada.dev sudo deploy-project reservas
```

---

## Decisiones de diseño

| Decisión | Por qué |
|---|---|
| **Reglas en el modelo**, no en las vistas ("fat models, thin views") | Una sola fuente de verdad: valen para el admin, las páginas, el shell y una futura API |
| `save()` llama a `full_clean()` | Ni `Booking.objects.create()` puede saltarse las reglas |
| Nunca `bulk_create()` para reservas | Se salta `save()` y con él todas las reglas |
| Bloquear la pista con `select_for_update()` | Evita reservas dobles simultáneas; MySQL no tiene restricciones de exclusión de rangos |
| Elegir de **bloques libres** en vez de escribir horas | El usuario no ve errores por horarios ocupados; el servidor igual recalcula todo |
| Confirmar **lo posible** e informar lo omitido | Si otro tomó un bloque entre medio, el resto de la selección no se pierde |
| Unir bloques seguidos | Menos reservas: más claras en el email, el admin y "Mis reservas" |
| Notificaciones en `save()` en vez de *signals* | Una sola app que controla su modelo: el flujo queda visible en un solo lugar |
| Email con `on_commit` | Nunca se avisa de algo que no se guardó |
| Texto del email generado al enviar, no guardado | Sale en el idioma del cliente |
| Email por **API de Brevo**, no por SMTP del buzón de Microsoft | Funciona en DigitalOcean (sin puertos SMTP), no obliga a desactivar el MFA y la key solo sirve para enviar |
| Zona horaria en el admin (singleton) | Cualquier negocio, en cualquier país, configura su zona sin tocar código |
| Settings separados (base / dev / prod) | Imposible desplegar con `DEBUG=True` o con herramientas de desarrollo |
| Grupo de permisos creado por migración de datos | Existe automáticamente en cualquier base, incluida producción |
| **Recurrencia dentro de la ventana de 7 días**, sin series de meses | Para repetir una reserva, se marcan los mismos bloques en varios días de la semana. Las pistas son de uso diario: si una se daña, hay que mandarla a mantenimiento, y con 7 días se planifica con más precisión que con reservas comprometidas por meses |
| **Email único en el modelo**, no solo en los formularios | Una sola regla para todas las entradas; el índice de MySQL también frena dos registros simultáneos |
| **Solo con cuenta**, sin reservas de invitado | Sin cuenta, cualquiera podría ocupar todos los bloques con emails falsos |
| Cobro de garantía (dummy) | Asegura la reserva como lo haría un negocio real; el código queda listo para una pasarela real |

---

## Hoja de ruta

- [x] Setup: Django, MySQL en Docker, `.env`, settings por entorno, i18n
- [x] Modelos y reglas de reserva
- [x] Notificaciones por email (reales con Brevo)
- [x] Admin + grupo "Gestores"
- [x] Registro, login, logout (el registro solo crea clientes)
- [x] Zona horaria configurable
- [x] Bloques libres y solicitudes de varios bloques
- [x] **Reservar:** selector de bloques con "Seleccionar todo", pago dummy y pop-up de resultado
- [x] **Mis reservas:** listar, cancelar de una en una, reprogramar (solo las propias)
- [x] Reservar a nombre de un cliente (búsqueda por email)
- [x] **Traducciones** es/en (español 100 %)
- [x] **Perfil**, cambiar contraseña y "¿Olvidaste tu contraseña?" (enlace de 1 hora)
- [x] **Layout** con Tailwind (CLI standalone) y JavaScript de todas las páginas
- [x] **Diseño "Marcador"** en SCSS (azul marino y ámbar), en el sitio y en el admin
- [x] **Límites contra bots y spam** (por IP y por cuenta), campo trampa y verificación del email al registrarse
- [x] Email obligatorio y único en todo el sistema (también en **Users → Add** del admin)
- [x] **Servidor preparado:** SSH solo con llave, firewall, usuarios `zarvi`/`deploy`, Docker, Nginx, certbot
- [ ] **Deploy** en el VPS con Docker: `vps.santiagoboada.dev`, SSL, Brevo de producción
- [ ] **Pago real:** cambiar `payments.charge()` por una pasarela (p. ej. Stripe)
- [ ] **SMS (próximamente):** solo planteado, no se construirá por ahora
