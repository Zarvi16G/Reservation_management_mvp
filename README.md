# Reservation Management

Aplicación web para **reservar instalaciones deportivas** (canchas, pistas y salas) por bloques de una hora, construida con Django.

**Demo:** https://vps.santiagoboada.dev

---

## Objetivo

Que un centro deportivo pueda ofrecer sus espacios en línea sin conflictos de horario:
- Los **clientes** ven solo los bloques libres, reservan varios a la vez y gestionan sus reservas.
- El **personal** administra canchas, horarios y reservas desde un panel.
- **Nadie puede reservar un bloque ocupado**, ni siquiera dos personas pulsando a la vez.

## Cómo se usa

### Clientes
1. **Crear una cuenta** y **verificar el email** con el enlace recibido. Sin verificar no se puede reservar.
2. **Reservar:** elegir los bloques libres de 1 hora en una o varias canchas, para hoy y los próximos 6 días. "Seleccionar todo" marca un día completo, y los bloques seguidos se unen en una sola reserva.
3. **Pagar** la garantía de 1 USD. Es un **pago de prueba**: no pide datos de tarjeta y siempre se aprueba.
4. Un pop-up muestra lo reservado. Si alguien tomó un bloque mientras tanto, se omite y se indica cuál.
5. Llega **un email de resumen** con las reservas confirmadas.
6. En **Mis reservas** se puede **cancelar** o **reprogramar** cada reserva.
7. En **Perfil** se cambian los datos, el idioma y la contraseña. Cambiar el email pide la contraseña actual. También hay recuperación de contraseña por email.

### Personal (staff)
- **Admin** (`/admin/`): canchas, tipos de espacio, horarios de apertura, reservas, usuarios y la **zona horaria** del centro.
- **Reservar a nombre de un cliente:** el mismo selector de bloques, buscando al cliente por email.
- **Gestores:** un grupo de empleados con permisos limitados. Pueden editar canchas y horarios y ver las reservas, pero no crear ni borrar canchas ni tocar usuarios.

### Reglas de reserva
- Bloques de 1 hora, desde hoy hasta 6 días después.
- Solo dentro del horario de apertura de cada cancha.
- Dos reservas confirmadas nunca se solapan.
- Las reglas se validan en el modelo, así que se cumplen también desde el admin, scripts o peticiones hechas a mano.

## Funcionalidades

- Reserva de **varios bloques, canchas y días** en una sola solicitud, con éxito parcial.
- **Concurrencia segura:** bloqueo de filas en la base de datos (`select_for_update`).
- **Emails reales** de confirmación, cancelación y reprogramación, en el idioma de cada cliente, con reintento automático si fallan.
- **Español e inglés** (`/es/`, `/en/`).
- **Zona horaria configurable** desde el admin.
- **Protección contra bots:** verificación de email, límites por IP y por cuenta, y campo trampa en el registro.
- **Diseño "Marcador"** (azul marino y ámbar, como un marcador de estadio) en el sitio y en el admin, adaptado al móvil.

## Tecnologías

| Área | Tecnología |
|---|---|
| Backend | Python 3.14, **Django 6.1** |
| Base de datos | MySQL 8.4 |
| Frontend | Templates de Django, **Tailwind CSS 4** (layout), **SCSS** (diseño), JavaScript sin frameworks |
| Email | Brevo (API) con django-anymail |
| Tests y calidad | pytest, pytest-django, Ruff |
| Producción | Docker Compose, Gunicorn, Nginx, SSL con certbot |

## Ejecutarlo en local

Requisitos: Python 3.12+ y Docker.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env              # completar SECRET_KEY y contraseñas
docker compose up -d              # MySQL

python manage.py migrate
python manage.py createcachetable
python manage.py createsuperuser
python manage.py runserver        # http://127.0.0.1:8000/es/
```

En local los emails se muestran en la consola. Para enviarlos de verdad, usa `SEND_REAL_EMAILS=True` y una API key de Brevo en `.env`.

## Tests

```bash
pytest
```

Cubren lo que no se puede comprobar a mano: varias personas reservando el mismo bloque a la vez, peticiones falsificadas, permisos, límites contra bots y envío de emails.

## Estructura

```
config/                  Configuración de Django (settings de desarrollo y producción)
reservation_managment/   La app: modelos y reglas, vistas, admin, emails, tests
templates/               Páginas, emails y personalización del admin
static/                  Tailwind (src/), SCSS (scss/), CSS compilado (css/), JS e imágenes
locale/es/               Traducción al español
deploy/                  Producción: Docker Compose, scripts de despliegue y Nginx
Dockerfile               Imagen de producción
```

## Despliegue

En producción corre en un VPS con **Docker Compose**: un contenedor con Django y Gunicorn, otro con MySQL, y Nginx delante con HTTPS. Los archivos están en `deploy/`; el código se actualiza con `git pull` y `deploy-project`.

---

Proyecto académico y de portafolio de Santiago Boada.
