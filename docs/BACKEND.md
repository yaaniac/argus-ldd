# Backend Argus LDD — Supabase + Render

Guía para poner en marcha el backend con **Supabase** (base de datos y APIs) y **Render** (hosting del front).

---

## 1. Supabase — Proyecto y base de datos

### 1.1 Crear proyecto

1. Entrá a [supabase.com](https://supabase.com) y creá una cuenta (o usá la que tengas).
2. **New project** → elegí organización, nombre del proyecto (ej. `argus-ldd`), contraseña de DB y región.
3. Esperá a que termine de crear el proyecto.

### 1.2 Ejecutar las migraciones

1. En el dashboard de Supabase, abrí **SQL Editor**.
2. **Primera migración:** New query → copiá todo `supabase/migrations/001_initial.sql` → **Run**.
3. **Segunda migración:** New query → copiá todo `supabase/migrations/002_backoffice_rpc.sql` → **Run**.

Con eso quedan creadas:

- **Tablas:** `tenants`, `casos`, `caso_seguimiento`
- **RPC portal:** `crear_denuncia`, `get_seguimiento` (denunciante consulta por código)
- **RPC back office:** `listar_casos_tenant`, `get_caso_por_id`, `get_seguimiento_mensajes`, `enviar_mensaje_denunciante`, `actualizar_estado_caso`
- **Tenants de ejemplo:** `demo` y `acme`

El **seguimiento** queda conectado: cuando el usuario del back office escribe un mensaje al denunciante (pestaña Comunicación), se guarda en `caso_seguimiento`. Ese mensaje es el que ve el denunciante al consultar por su código en el portal.

### 1.3 Obtener URL y anon key

1. En Supabase: **Project Settings** (ícono de engranaje) → **API**.
2. Copiá:
   - **Project URL**
   - **anon public** (clave pública, no la `service_role`).

Los vas a usar en el front y en Render.

### 1.4 Configurar el front en local

Creá (o editá) el archivo **`supabase-env.js`** en la raíz del proyecto, con tus valores:

```js
window.ArgusSupabase = {
  url: 'https://TU_PROYECTO.supabase.co',
  anonKey: 'tu_anon_key_aqui'
};
```

Podés basarte en `supabase-env.js.example`.  
Si dejás `url` y `anonKey` vacíos, el portal sigue funcionando en modo mock (sin backend).

---

## 2. Render — Hosting del sitio

### 2.1 Conectar el repo

1. Entrá a [render.com](https://render.com) e iniciá sesión (con GitHub si el código está ahí).
2. **New** → **Static Site**.
3. Conectá el repo de **argus-ldd** (autorizá a Render si hace falta).
4. Configurá:
   - **Name:** por ejemplo `argus-ldd`.
   - **Branch:** `main` (o la rama que uses).

### 2.2 Build y publicación

- **Build Command:**  
  `npm run inject-env`
- **Publish Directory:**  
  `.` (raíz del repo)

Así, en cada deploy Render ejecuta el script que genera `supabase-env.js` con las variables de entorno y publica todo el sitio desde la raíz.

### 2.3 Variables de entorno en Render

1. En tu Static Site de Render: **Environment**.
2. Agregá:

| Key                 | Value                          |
|---------------------|---------------------------------|
| `SUPABASE_URL`      | `https://TU_PROYECTO.supabase.co` |
| `SUPABASE_ANON_KEY` | La anon key de Supabase        |

Guardá. En el próximo deploy, el build usará estos valores para generar `supabase-env.js` y el portal hablará con tu Supabase.

### 2.4 Deploy

Hacé **Manual Deploy** o un push a la rama configurada. Cuando termine, Render te da una URL (ej. `https://argus-ldd.onrender.com`).

---

## 3. Probar el flujo

1. **Portal con tenant:**  
   `https://tu-app.onrender.com/formulario.html?t=acme`  
   (reemplazá `acme` por un slug que exista en `tenants`).
2. Completá una denuncia y enviá. Deberías recibir un código **ARG-AAAA-XXXX** generado por Supabase.
3. **Seguimiento:** en la misma URL, usá “Consultar denuncia” con ese código. Deberías ver el estado (inicialmente “Pendiente de evaluación”).
4. **Back office:** por ahora sigue usando datos en `localStorage`. Conectar el back office a Supabase (listar/editar casos por tenant) sería un siguiente paso (auth, RLS, etc.).

---

## 4. Resumen de archivos

| Archivo | Uso |
|--------|-----|
| `supabase/migrations/001_initial.sql` | Schema y RPC en Supabase (ejecutar una vez en SQL Editor). |
| `supabase-env.js` | Config local o generado en build (URL + anon key). |
| `supabase-env.js.example` | Plantilla para crear `supabase-env.js`. |
| `supabase-client.js` | Cliente en el navegador: `crearDenuncia`, `getSeguimiento`. |
| `scripts/inject-supabase-env.js` | Usado en Render: escribe `supabase-env.js` desde `SUPABASE_URL` y `SUPABASE_ANON_KEY`. |

---

## 5. Flujo completo (resumen)

1. **Denunciante** (portal): envía denuncia → recibe **código ARG-AAAA-XXXX** (guardado en Supabase).
2. **Denunciante** (portal): en “Consultar denuncia” ingresa el código → ve estado y el **último mensaje** del equipo.
3. **Back office** (por tenant): lista de casos sale de Supabase; al abrir un caso se cargan detalle y **mensajes al denunciante**.
4. **Back office** (pestaña Comunicación): al escribir y enviar un mensaje, se guarda en `caso_seguimiento`; el denunciante lo ve la próxima vez que consulte por código.

## 6. Siguientes pasos (opcional)

- **Auth back office:** Supabase Auth o PIN por tenant para restringir quién puede ver cada tenant.
- **Actualizar estado:** usar `actualizar_estado_caso` desde la UI (pending / active / closed).
- **Contacto/demo:** enviar el formulario de contacto a un servicio de email o tabla en Supabase.
