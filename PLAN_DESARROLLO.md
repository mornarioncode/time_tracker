# Plan de desarrollo — Time Tracker

- **Fecha:** 2026-11-18
- **Fuente:** Solicitud del usuario (requisitos de producto) + investigación técnica del agente de planificación
- **Propósito:** Guía de implementación fase a fase de una aplicación de time tracking estilo Toggl, de concepto sencillo, escrita en Python con Flet, con persistencia SQLite y prioridad en Windows.

---

## 1. Resumen del proyecto y objetivos

Time Tracker es una aplicación de seguimiento de tiempo con un concepto muy simple:

1. Al iniciar el programa se **crea una sesión de trabajo** o se **selecciona una existente**.
2. Se crean **tareas** (solo nombre) en un **catálogo global** reutilizable entre sesiones *(cambio de modelo del usuario, 18/11/2026; ver §5)*.
3. Al **seleccionar una tarea** se guarda fecha/hora de inicio. Al **cambiar de tarea** o al **terminar la sesión** se guarda fecha/hora de fin, y el intervalo resultante se añade a una lista.
4. La aplicación ofrece **reporting con estadísticas** de la actividad (totales por tarea, día, semana, filtros y gráficos).

**Objetivos:**

- Interfaz **muy limpia**, estilo Material, sin fricción para el usuario.
- **Persistencia** de sesiones, tareas e intervalos entre arranques (SQLite).
- Plataformas: **Windows (prioritario)**, Android (Fase 5). iPhone/iPad **pospuesto / fuera del alcance actual** (ver §6 Fase 5 y §8, riesgo 2).
- Todo el código en **Python** (requisito explícito del usuario).

**Fuera de alcance del MVP:** sincronización en la nube, multiusuario, colaboración, estimaciones/presupuestos, plugins, notificaciones de escritorio, modo offline multi-dispositivo.

---

## 2. Punto de partida (estado actual y decisión de empezar de cero)

El repositorio contiene hoy un esqueleto CLI casi vacío:

| Fichero | Contenido actual |
|---|---|
| `main.py` | Menú CLI con 5 opciones (cargar sesión, nueva sesión, listar, eliminar, salir) cuyo cuerpo está **sin implementar**. Incluye un *leftover* irrelevante: `load_dotenv()` para una API key de OpenAI (`python-dotenv`), que no guarda relación con el proyecto. |
| `time_tracking.py` | Clase `session` con `start()`, `stop()`, `get_duration()`, `add_task()`, `get_tasks()`. Sin modelo `Task`, sin persistencia, sin UI. `add_task` solo hace `list.append` de un objeto genérico. |
| `README.md` | Solo la línea `# time_tracker`. |
| Otros | `.venv`, `.git`, `.gitignore`, `.env` (este último, también heredado del leftover de OpenAI). |

**Decisión: empezar de cero.** *Justificación:* el código existente no aporta lógica reutilizable (no hay modelo de datos, ni persistencia, ni UI, y la única clase `session` se reescribiría casi entera al introducir SQLite y entry intervals), así que eliminarlo evita lastre y el *leftover* de OpenAI/.env queda descartado de fábrica. Esta decisión está **autorizada expresamente por el usuario**.

Consecuencias:

- `main.py` y `time_tracking.py` se **eliminan** en Fase 0 (junto con `.env` y la dependencia `python-dotenv`).
- `README.md` se reescribe (fase posterior al MVP o al final de la Fase 0, según se decida) — *mínimo requerido: rellenarlo con instrucciones de arranque*.
- `.gitignore` se revisa/conserva (es útil tal cual; se ampliará con entradas de builds, `.venv`, `dist/`, `build/`, `*.db`).
- No se migra ningún dato previo porque **no existe persistencia previa**.

---

## 3. Stack tecnológico y justificación

### 3.1 Stack elegido

| Capa | Elección |
|---|---|
| Lenguaje | Python 3.11+ (requisito del usuario) |
| UI | **Flet** (elegido explícitamente por el usuario) |
| Persistencia | **SQLite** vía `sqlite3` de la stdlib (recomendación aceptada) |
| Charts | `flet-charts` (gráficos de barras/líneas/tarta para reporting) |
| Tests | `pytest` (+ `pytest-cov` opcional) |
| Empaquetado Windows | `flet build windows` (prioritario) / PyInstaller (alternativa) |
| Empaquetado Android | `flet build apk` |
| Empaquetado iOS | `flet build ipa` — **requiere Mac o CI con runner macOS**; **fuera del alcance actual** (pospuesto) |
| Gestión de dependencias | **`uv`** — **fijado** (decisión del usuario), con `pyproject.toml` |

### 3.2 Investigación técnica (comparativa resumida)

Comparativa realizada: **Flutter / Flet / BeeWare / Kivy / PySide6 / React Native + RN for Windows / Tauri / .NET MAUI**.

**Gana Flet** para este caso porque:

- **Reutiliza Python**: no hay que abandonar el lenguaje (requisito duro del usuario).
- **Curva mínima**: API declarativa simple, ideal para un concepto sencillo.
- **UI estilo Material limpia** de serie, justo lo que pide el producto.
- `flet build windows` genera un **.exe** sin escribir código nativo.
- Soporta **SQLite** directamente y **charts** (`flet-charts`) para reporting.
- `flet build` genera también **APK** para Android desde Windows/Linux.

**Riesgos conocidos de Flet (ver también §8):**

- Debe **Flutter por debajo**, lo que implica un *cold start* mayor (más visible en móvil).
- Ecosistema de extensiones más pequeño que Flutter/React.
- **iOS: compilar requiere un Mac** (o CI con Mac, p. ej. GitHub Actions con `runs-on: macos-*`); al no haber Mac ni presupuesto de CI con macOS, **iPhone/iPad queda fuera del alcance actual** y se pospone (ver §6 Fase 5).
- Móvil **menos probado que desktop**: se prioriza Windows primero, se validan Android/iOS después.
- Posibles cambios de **licencia/estrategia** de la empresa detrás de Flet (Flet tiene modelo freemium en su SDK cloud; el uso local/CLI es open source hoy — verificar versión al fijar dependencias).

**Alternativas descartadas (motivo breve):**

| Alternativa | Por qué se descarta |
|---|---|
| Flutter | Exigiría abandonar Python (Dart). |
| Qt (PySide6) | Sin vía oficial a móviles; licencias/peso innecesarios aquí. |
| Kivy | UI poco pulida; estética alejada del "muy limpio" pedido. |
| React Native + RNW | Soporte de Windows efímero/madurez dudosa; abandona Python. |
| Tauri | Móvil inmaduro; requiere Rust/JS. |
| .NET MAUI | Reescritura total en C#/XAML. |
| BeeWare | Ecosistema y tooling de builds menos fiables que Flet para este alcance. |

---

## 4. Arquitectura de la aplicación

Arquitectura en **capas** con dependencias unidireccionales: `ui → core → storage`, donde `core` no conoce a `ui` ni a `storage` (la persistencia se abstraerá tras un repositorio).

```
time-tracker/
├── main.py                  # punto de entrada: arranca la app Flet
├── pyproject.toml           # dependencias (uv)
├── README.md
├── PLAN_DESARROLLO.md
├── core/                    # lógica de negocio (sin Flet, sin SQL directo)
│   ├── __init__.py
│   ├── models.py            # dataclasses: Session, Task, TimeEntry
│   ├── services.py          # TimeTrackerService: reglas de negocio
│   ├── repository.py        # abstractas: SessionRepository, EntryRepository
│   └── exceptions.py        # errores de dominio (SesionAbiertaError, etc.)
├── storage/                 # persistencia SQLite
│   ├── __init__.py
│   ├── db.py                # conexión, migraciones/schema, PRAGMAs
│   ├── schema.sql           # DDL inicial (opcional: embebido en db.py)
│   └── sqlite_repository.py # implementación de los repositorios
├── ui/                      # presentación Flet
│   ├── __init__.py
│   ├── app.py               # montaje de la app, rutas/tema
│   ├── theme.py             # tema, colores, tipografía (limpieza visual)
│   ├── components/          # widgets reutilizables (cronómetro, fila de entry…)
│   └── pages/
│       ├── home_page.py         # crear/seleccionar sesión
│       ├── session_page.py      # tareas, cronómetro, switch, lista de intervalos
│       └── report_page.py       # reporting y gráficos
├── reports/                  # consultas/agregaciones de reporting (Fase 3)
│   └── stats.py
└── tests/
    ├── test_models.py
    ├── test_service.py
    ├── test_storage.py
    └── test_reports.py
```

**Responsabilidades:**

- **`core/models`**: entidades inmutables o dataclasses; validación básica (fin ≥ inicio, nombre no vacío).
- **`core/services`**: operaciones de caso de uso — `crear_sesion`, `seleccionar_sesion`, `añadir_tarea`, `iniciar_tarea` (cierra la entry abierta si la hay y abre la nueva), `detener_tarea`, `cerrar_sesion` (cierra la entry abierta), `listar_intervalos`, `eliminar_sesion`. Toda escritura a BD pasa por aquí.
- **`storage`**: **una única conexión por proceso** (`sqlite3.connect(..., check_same_thread=False)`) protegida por un `threading.RLock` que serializa las operaciones — *decisión de diseño fijada para Fase 1* (la app es monousuario/escritorio, la UI Flet puede tocar la BD desde su hilo de eventos; con una sola conexión + WAL no hay "database is locked" y se evita el coste de abrir/cerrar por operación; alternativa "conexión por operación" descartada por simplicidad, salvo que los tests la exijan), `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`, y **migraciones numeradas** desde el día uno (aplicadas con `PRAGMA user_version`; esquema v1 → **v2** con el refactor de tareas globales, ver §5.2 y Fase 1b).
- **`ui/pages`**: solo compone controles y llama a servicios; **nunca** contiene SQL ni reglas de negocio. El cronómetro se refresca con un `page.run_task`/timer periódico (1 s) leyendo el `start` de la entry activa.
- **`reports/stats`**: agregaciones (SUM de segundos) parametrizadas por rango/tarea, devolviendo estructuras listas para pintar.

**API v2 del servicio para la Fase 2 (UI) — contrato tras el refactor de tareas globales (Fase 1b):**

| Operación | Sesión requerida | Comportamiento |
|---|---|---|
| `añadir_tarea(nombre)` | **No** | Escribe en el **catálogo global** (`Task`: `name` + `created_at`; **sin `session_id`**). Homónimo → `DuplicateTaskError`. |
| `listar_tareas()` | **No** | Devuelve el catálogo global completo (independiente de la sesión seleccionada). |
| `iniciar_tarea(task_id)` | **Sí (seleccionada)** | Crea la `TimeEntry` con `task_id` + `session_id` de la sesión **seleccionada**; debe estar **abierta** → `SessionClosedError` si está cerrada; `ValidationError` si no hay sesión seleccionada. |
| `crear_sesion` / `seleccionar_sesion` / `listar_sesiones` / `listar_intervalos` / `cerrar_sesion` | según caso | Igual que en §4 (la sesión seleccionada vive en el servicio: `sesion_actual`). |

Notas para la UI:

- **`TimeEntry.session_id` es obligatorio**; `Task` **no** tiene `session_id` pero sí `created_at` (la UI puede mostrar "creada el …").
- **Modelos inmutables** (`frozen=True`): los objetos devueltos por el servicio son **snapshots**. Tras cualquier escritura la UI debe **releer** con `listar_intervalos()` / `listar_sesiones()` (y `sesion_actual`) en lugar de reutilizar la referencia anterior. **Ojo con el snapshot de `crear_sesion`**: devuelve la sesión recién creada, pero el auto-cierre de la sesión anterior (§5.3.2) y cierres posteriores solo se ven al releer.

**Principios a mantener durante la implementación:**

- Timestamps guardados en **UTC** (columnas `*_at`, texto ISO-8601 terminado en `Z`, p. ej. `2026-11-18T09:12:00Z`); se localizan al mostrar.
- Duraciones almacenadas como **entero de segundos**; se formatean (`1 h 23 min`) solo en UI.
- La UI depende de `core`, nunca al revés → los tests de dominio corren sin Flet.

---

## 5. Modelo de datos

### 5.1 Entidades

- **Session**: grupo de trabajo (p. ej. "Semana 47 — App web"). Tiene nombre, fecha de creación, opcionalmente `ended_at` (null = sesión abierta).
- **Task**: **tarea global del catálogo** *(decisión del usuario, 18/11/2026 — modelo estilo Toggl)*. Solo **nombre + fecha de creación** (`created_at`), **única en toda la BD** (el `UNIQUE` aplica tras `strip()`; homónimos se rechazan con `DuplicateTaskError`). Se crea una vez y **se reutiliza en todas las sesiones** (p. ej. "Correo", "Reuniones"). Sustituye al modelo v1, donde la tarea estaba encapsulada en la sesión (`UNIQUE(session_id, name)`). Las tareas **no se borran en cascada** al borrar una sesión: sobreviven al catálogo.
- **TimeEntry (intervalo)**: `task_id` + `session_id`, `started_at`, `ended_at` (null mientras está corriendo). Con `task_id` + `session_id` el tramo queda anclado a **"qué tarea"** y **"qué sesión/jornada"**. **Una sola entry abierta a la vez** (regla de negocio: al cambiar de tarea se cierra la anterior y se abre la nueva).

> Nota de naming: el usuario habla de "tareas" e "intervalos"; en el código se usan `Task` y `TimeEntry`. La lista que ve el usuario ("lista de intervalos") son los `TimeEntry`.

### 5.2 Esquema SQLite — **DDL v2** *(decisión del usuario, 18/11/2026; sustituye al v1)*

```sql
PRAGMA foreign_keys = ON;

-- v1 → v2: sessions SIN CAMBIOS
CREATE TABLE IF NOT EXISTS sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,   -- ISO-8601 UTC, p. ej. 2026-11-18T09:12:00Z
    ended_at    TEXT                -- NULL = sesión abierta
);

-- v2: tareas GLOBALES (sin session_id); se crean una vez y se reutilizan
-- en todas las sesiones. UNIQUE aplica tras strip(); homónimos → DuplicateTaskError.
CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    created_at  TEXT    NOT NULL
);

-- v2: añade session_id → el tramo queda anclado a "qué tarea" y "qué sesión/jornada"
CREATE TABLE IF NOT EXISTS time_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    session_id  INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    started_at  TEXT    NOT NULL,
    ended_at    TEXT                -- NULL = intervalo en curso
);

CREATE INDEX IF NOT EXISTS idx_entries_task     ON time_entries(task_id);
CREATE INDEX IF NOT EXISTS idx_entries_started  ON time_entries(started_at);
CREATE INDEX IF NOT EXISTS idx_entries_session  ON time_entries(session_id);
-- idx_tasks_session (v1) eliminado: tasks ya no tiene session_id
```

**`PRAGMA user_version` → 2.** Migración desde v1 vía `ALTER TABLE` / rebuild de tablas. **La app es pre-lanzamiento y la BD v1 solo existe en entorno de dev: migración *best-effort* aceptable** (la implementa *makerman*).

**Migración v1→v2 — criterios implementados y smoke-verificados (Fase 1b, 19/11/2026):**

1. **Transaccional**: todo el rebuild corre dentro de **UNA transacción** (DDL transaccional en SQLite); si falla → `ROLLBACK` y la BD queda **intacta en v1** (`user_version = 1`).
2. **Homónimos fusionados**: en v1 el `UNIQUE(session_id, name)` permitía "Correo" en varias sesiones; en v2 `tasks.name` es global. La migración **fusiona** por nombre conservando la tarea **más antigua** (`MIN(id)` y `MIN(created_at)`).
3. **Entries re-ancladas**: cada `time_entries` hereda el `session_id` de la **task vieja** (`tasks_v1.session_id`) y su `task_id` se **remapea** al superviviente fusionado.
4. **Huérfanos descartados**: entries con `task_id` o `session_id` inexistente (solo posibles con FK OFF) se **eliminan** en el `JOIN` de la migración (best-effort documentado); tras migrar, `PRAGMA foreign_key_check` queda **limpio**.
5. **Idempotente**: re-ejecutar `initialize()` no cambia nada; el estado final es `user_version = 2` y se aplican solo las migraciones con `version > current`.
6. **Sin restos de v1**: se eliminan las tablas `*_v1`, el índice `idx_tasks_session` y se crean los índices v2 (`idx_entries_session` incluido).

**Reglas de integridad (aplicadas en servicio + asserts/tests):**

1. Como máximo **un** `time_entries.ended_at IS NULL` en toda la base (intervalo en curso).
2. Al cerrar un intervalo: `ended_at >= started_at`.
3. Borrar una sesión borra en cascada sus **entries** (`time_entries.session_id` → `ON DELETE CASCADE`); las **tareas globales NO se borran**: quedan huérfanas de entries pero **vivas en el catálogo** (confirmación en UI previa al borrar).
4. Cambiar de tarea = `UPDATE ... SET ended_at = now` (entry anterior) + `INSERT` (entry nueva) en **una transacción**.

### 5.3 Decisiones de negocio registradas en la implementación (Fases 0–1)

1. **No-op al re-seleccionar la tarea en curso.** Si `iniciar_tarea` se invoca sobre la tarea que ya está corriendo, no se cierra ni se reabre el intervalo: se devuelve la entry existente. Evita *micro-intervalos* por dobles clics o re-selecciones accidentales.
2. **Solo UNA sesión de trabajo abierta a la vez (decisión del usuario, 18/11/2026) — ✅ IMPLEMENTADA.** Iniciar una nueva sesión **cierra automáticamente la sesión anterior** (auto-cierre en `crear_sesion`, guardando su `ended_at`); todas las sesiones abiertas + la entry global se cierran en **una transacción con un único `now`**. Se mantiene la restricción global de **como máximo 1 `time_entries` abierta** en toda la BD. **Decisión: `seleccionar_sesion` no cierra ni reabre sesiones** (solo cambia el puntero de sesión actual).
3. **Tareas globales *(decisión del usuario, 18/11/2026).*** `añadir_tarea` escribe en el **catálogo global** de `tasks` (no ligado a una sesión). `iniciar_tarea` crea la entry con `task_id` **y** `session_id` de la sesión **actualmente abierta/seleccionada**. Reutilizar una tarea (p. ej. "Correo") en otra sesión solo requiere iniciarla de nuevo — no hay que recrearla.
4. **Sesiones cerradas = historial de solo lectura *(decisión del usuario, 18/11/2026; semántica confirmada por el coordinador, 19/11/2026).*** Las sesiones cerradas **NO se reabren**. Al iniciar el programa solo se puede: **(a)** crear sesión nueva, o **(b)** continuar la sesión **actualmente abierta**. **Semántica confirmada:** `seleccionar_sesion` sobre una sesión cerrada **NO lanza** — la sesión cerrada es **consultable** (historial de solo lectura: `listar_intervalos`, `listar_tareas`, etc. funcionan); las **escrituras** sobre ella (`iniciar_tarea`, `cerrar_sesion`) lanzan **`SessionClosedError`**. Conserva la regla de **sesión única abierta** del punto 2.

---

## 6. Funcionalidades por fases (roadmap)

Cada fase termina en entregables verificables. No empezar una fase sin cerrar la anterior (salvo Fase 4/5, que pueden solaparse con Fase 3).

### Fase 0 — Proyecto limpio

**Objetivo:** partir de cero sin lastre. — **✅ Completada (18/11/2026).**

- [x] Eliminar `main.py` y `time_tracking.py` (código CLI descartado).
- [x] Eliminar `.env` y la dependencia `python-dotenv` / leftover de OpenAI.
- [x] Ampliar `.gitignore` (`.venv/`, `dist/`, `build/`, `*.db`, `__pycache__/`, `.flet/`).
- [x] Crear la estructura de paquetes de §4 (carpetas con `__init__.py` vacíos).
- [x] Crear `pyproject.toml` con dependencias: `flet`, `flet-charts`, `pytest`; gestor de dependencias **`uv` (fijado, decisión del usuario)**. *Hecho con `flet==1.1.2` + `flet-cli` + `flet-desktop` fijados (desviación justificada: Flet 1.x no empaqueta la CLI en `flet`; ver Historial de cambios).*
- [x] `main.py` nuevo mínimo: arranca una app Flet con una sola página "Hola" (humo).
- [x] Reescribir `README.md`: qué es, requisitos, cómo ejecutar (`uv run flet run main.py` / equivalente), cómo testear.
- [x] Confirmar: `flet run main.py` abre la ventana en Windows.

**Entregables:** repo sin restos de OpenAI, estructura por capas, arranque de Flet comprobado, README útil.

### Fase 1 — Núcleo de dominio + persistencia SQLite + tests

**Objetivo:** todo el comportamiento sin UI, cubierto por tests. — **✅ Completada (18/11/2026); cerrada con la Fase 1b el 19/11/2026.**

- [x] `core/models.py`: `Session`, `Task`, `TimeEntry` (dataclasses + validaciones).
- [x] `storage/db.py`: conexión (única por proceso con `check_same_thread=False` + `threading.RLock`, §4), PRAGMAs, creación/migración de esquema v1 (§5.2; hoy DDL **v2** — ver Fase 1b).
- [x] `storage/sqlite_repository.py`: CRUD de sesiones/tareas/entries + `get_open_entry()`, `close_open_entry(now)`.
- [x] `core/services.py`: casos de uso de §4 con transacción en `iniciar_tarea` y `cerrar_sesion`.
- [x] `core/exceptions.py`.
- [x] `tests/`: modelos, servicio y repositorio contra un `tmp_path/*.db` real (no mocks). **Suite del agente tester: 147 tests, todos en verde (19/11/2026).**
- [x] Cobertura sobre `core` + `storage` (objetivo orientativo ≥ 80 %): **100 % medida con `uv run pytest --cov=core --cov=storage` (19/11/2026).**

**Entregables:** librería `core+storage` usable por REPL, suite `pytest` en verde, esquema migrable (aplicar `user_version`).

### Fase 1b — Refactor a modelo global (tareas globales + `session_id`) — **✅ Completada (19/11/2026, verificada por el coordinador)**

**Objetivo:** llevar el núcleo al **DDL v2** (§5.2): tareas globales estilo Toggl y `time_entries.session_id`. Trabajo dentro de la Fase 1.

- [x] **DDL v2 + migración**: `tasks` sin `session_id` (`UNIQUE(name)`), `time_entries.session_id` NOT NULL + `idx_entries_session`, `PRAGMA user_version = 2`; migración v1→v2 *best-effort* (pre-lanzamiento, BD v1 solo en dev). **Implementada y smoke-verificada**: transaccional (rollback → BD intacta en v1), idempotente (`user_version = 2`), homónimos fusionados con `MIN(id)`/`MIN(created_at)`, entries re-ancladas a `session_id` de la task vieja, huérfanos descartados y `PRAGMA foreign_key_check` limpio (criterios en §5.2).
- [x] **Modelos**: `Task` sin `session_id` (con `created_at`); `TimeEntry` con `session_id` obligatorio; `DuplicateTaskError` y `SessionClosedError` en `core/exceptions.py`.
- [x] **Servicios/repos**: `añadir_tarea` al catálogo global (sin sesión); `listar_tareas()` global; `iniciar_tarea` con `task_id` + `session_id` de la sesión seleccionada; `SessionClosedError` al **escribir** sobre sesión cerrada (selección y consultas no lanzan — §5.3.4); cascada de borrado de sesión solo en `time_entries` (las tareas sobreviven).
- [x] **Tests afectados**: modelos, servicio y storage (unicidad global de tareas, anclado `session_id`, cascadas, sesión única abierta, sesiones cerradas en solo lectura). **147 tests → ✅ 147 passed, 0 failed, 0 xfail; cobertura `core`+`storage` = 100 %.** El antiguo **xfail FK fue retirado**: el bug FK-vs-UNIQUE está corregido y cubierto en verde.

**Entregables:** núcleo en verde contra el DDL v2. **✅ Verificado por el coordinador (19/11/2026).**

### Fase 2 — UI Flet en Windows

**Objetivo:** MVP funcional de tracking. — **✅ Completada y verificada (20/11/2026).**

> **Estado: ✅ completada y verificada (20/11/2026).** La verificación del coordinador (pasada del tester) está hecha: **225 tests → 225 passed, 0 failed, 0 xfail** (78 tests nuevos de UI), cobertura **100 % en `core`+`storage` y también 100 % en `ui/`**, **sin bugs** en la UI. Decisiones cerradas de la implementación, ver §6.1 (Fase 2).

- [x] `ui/app.py` + `ui/theme.py`: tema Material limpio, tipografía y espaciados coherentes.
- [x] **home_page**: lista de sesiones existentes (nombre, fecha, duración total), botón "Nueva sesión", "Continuar sesión", "Eliminar" con confirmación.
- [x] **session_page**:
  - Crear tarea (campo de texto + Enter/botón) — escribe en el **catálogo global** (§5.3.3).
  - Lista de tareas; al pulsar una → cierra entry abierta (si la hay) y abre nueva.
  - **Cronómetro visible** (hh:mm:ss) de la tarea en curso, con estado claro de "corriendo".
  - Botón **Detener** (guarda `ended_at`) y **Terminar sesión** (cierra entry + marca `sessions.ended_at`).
  - **Lista de intervalos** de la sesión: tarea, inicio, fin, duración formateada.
- [x] Persistencia entre arranques: al reabrir la app se recupera la sesión y la entry en curso.
- [x] Tests de UI mínimos (ver §7): **78 tests de UI en verde** — `test_ui_format` 17, `test_ui_logica` 19, `test_ui_app` 26, `test_ui_vistas` 9, `test_ui_errores` 7 (ayudante `tests/ui_util.py`); verifican el contrato §6.1, incluido el **test clave**: sesión cerrada = **ni botones ni TextField de escritura**.

**Entregables:** app usable de punta a punta en Windows: crear sesión → tareas → cronómetro → intervalos persistidos. **✅ Verificado por el coordinador (20/11/2026):** 225 tests en verde (78 de UI), 100 % de cobertura (`core`+`storage`+`ui`), sin bugs en la UI.

#### 6.1 Decisiones cerradas en la implementación de la Fase 2 (19/11/2026) — **✅ completada y verificada (20/11/2026)**

> Todas las decisiones de este apartado están **cerradas** (fuente indicada en cada una). El estado de la fase es **"✅ completada y verificada (20/11/2026)"**: la pasada de verificación del coordinador/tester está hecha (225 tests en verde, 100 % de cobertura `core`+`storage`+`ui`, sin bugs).

**Estructura de la UI (diseño para testabilidad sin GUI):**

| Módulo | Responsabilidad |
|---|---|
| `ui/app.py` | `TimeTrackerApp`: navegación por rutas `/` (portada/inicio) y `/sesion/<id>`; **pila con "atrás" nativo** de Flet; **relee la BD y repinta tras cada acción** (los modelos son *snapshots* inmutables, §4). |
| `ui/theme.py` | Tema **Material 3** con **semilla índigo**; ventana **1120×800** (mínimo **800×600**); **columna centrada de 740 px con scroll**. |
| `ui/pages/inicio.py` | Portada: lista de sesiones, crear/continuar/eliminar. |
| `ui/pages/sesion.py` | Vista de sesión: tareas, cronómetro, detener, terminar sesión, lista de intervalos. |
| `ui/format.py`, `ui/errores.py`, `ui/logica.py` | **Capas puras sin Flet** (formateo, mapeo de errores a mensaje de usuario, lógica de presentación): **diseño pensado para testear sin GUI**. |

**UX decidida (decisiones CERRADAS):**

- **Tema: `ThemeMode.SYSTEM`** — la app respeta el modo claro/oscuro del sistema *(decisión del usuario)*.
- **"Terminar sesión": diálogo de confirmación SOLO si hay tarea cronometrada en curso**; si no hay tarea, cierra directo *(decisión del usuario)*.
- **Formatos** *(decisión del coordinador)*: totales de **portada legibles** (`1 h 23 min`); **intervalos precisos `hh:mm:ss`** (soporta **> 23 h**).
- **Sin snackbar de éxito al añadir tarea**: la fila nueva es el feedback — menos ruido *(decisión del coordinador)*.
- **Errores de dominio → SnackBar de 4 s** con `mensaje_usuario()`: el error de dominio se muestra **tal cual, en español**; `StorageError` y excepciones inesperadas → **mensaje genérico**, **jamás una traza** al usuario.
- **Confirmación modal también en "eliminar sesión"**, advirtiendo de que **el catálogo de tareas se conserva** (las tareas globales no se borran en cascada, §5.2).
- **Cronómetro**: *tick* de **1 s** con `page.run_task`, **recalculado desde el `started_at` real** de la entry → **persiste entre arranques** de la app (no depende de estado en memoria).
- **Sesión cerrada = solo lectura, DOS veces**: en **servicio** (`SessionClosedError` al escribir, §5.3.4) y en **presentación** (la vista de sesión cerrada **no contiene ningún control de escritura**).

### Fase 3 — Reporting

**Objetivo:** estadísticas de la actividad.

- [ ] `reports/stats.py`: totales agrupados por **tarea**, por **día**, por **semana**; rangos: hoy / 7 días / 30 días / todo / rango personalizado.
- [ ] Filtros: por sesión, por tarea, por rango de fechas.
- [ ] **report_page** con `flet-charts`: barras (duración por día), tarta o barras horizontales (reparto por tarea), tabla detallada exportable (CSV opcional).
- [ ] Ignorar entries sin `ended_at` en los cálculos (o contarlas hasta ahora — decidir y documentar; **recomendado: excluir y marcar visualmente**).
- [ ] Tests de `reports/stats` con datos sembrados.

**Entregables:** página de informes con al menos 3 vistas y filtros funcionando.

### Fase 4 — Empaquetado Windows

**Objetivo:** .exe distribuible.

- [ ] Probar `flet build windows` y validar que el ejecutable arranca en una máquina limpia (sin Python).
- [ ] Alternativa: PyInstaller (`--onedir --windowed`) si `flet build` da problemas; documentar cuál se queda.
- [ ] Nombre/versión/icono del producto en `pyproject.toml` + `assets/`.
- [ ] Nota: primera ejecución genera el perfil de Flet/Flutter (cold start); comprobar que el arranque es aceptable.

**Entregables:** instalador o carpeta con `.exe` funcionando en Windows limpio.

### Fase 5 — Android (APK) — iOS fuera del alcance actual

**Objetivo:** móvil Android. **Solo después de validar Windows (Fases 0–4).**

- [ ] **Android:** `flet build apk` (requiere Android SDK + Java instalados); probar touch, cronómetro en background y permisos. Riesgo: cold start mayor por Flutter.
- [ ] **iOS:** **pospuesto y explícitamente fuera del alcance actual** (decisión del usuario: no hay Mac ni presupuesto de CI con runner macOS). Requiere retomarlo solo cuando exista un Mac local o CI con `runs-on: macos-*`; hasta entonces no se planifican tareas, criterios ni entregables de iOS.
- [ ] Adaptar layouts a pantallas pequeñas (la UI de Fase 2 se diseña ya responsive para minimizar rework).

**Entregables:** APK instalable probado en dispositivo real. **iOS no es entregable** en este plan (quedó fuera del alcance actual).

---

## 7. Pruebas

| Nivel | Qué | Herramienta | Fase |
|---|---|---|---|
| Unitarias de dominio | modelos, validaciones, reglas (una entry abierta, cierre al cambiar de tarea) | `pytest` | 1 |
| Integración persistencia | repositorio contra SQLite real en `tmp_path`; cascadas e integridad | `pytest` | 1 |
| Reporting | agregaciones con datasets sembrados (incl. bordes: días sin datos, entry en curso) | `pytest` | 3 |
| UI | **78 tests en verde (20/11/2026)**: montaje **headless** de páginas con datos falsos (`PaginaFalsa`) y verificación de controles clave — **sin plugin de Flet para pytest** (las `ft.View` se construyen headless); el resto, **pruebas manuales** con checklist | `pytest` (+ ayudante propio `tests/ui_util.py`) | 2 |
| Smoke final | checklist manual de los criterios de §9 en Windows limpio | manual | 4 |

- No se usan *mocks* de SQLite: se prueba contra una BD real temporal (más fiable y detecta errores de SQL).
- **Cobertura (20/11/2026): 100 % en `core`, `storage` y `ui/`** (225 tests en verde). **Único fichero no cubierto: `main.py`** (bootstrap Flet real, que requiere GUI) — **alcance razonable** documentado al cerrar la Fase 2.
- Checklist manual por fase: crear sesión, cambiar de tarea repetidamente, matar el proceso y reabrir, verificar que los tiempos cuadran.
- **CI (GitHub Actions) con `pytest`: opcional recomendado, pendiente de decisión del usuario.** No bloquea la Fase 1 ni el MVP: la suite corre y se exige en local (`pytest` en verde, §9.8); el CI solo añade repetibilidad y pasaría a ser necesario únicamente si se retoma iOS con runner macOS.

---

## 8. Riesgos y mitigaciones

| # | Riesgo | Impacto | Mitigación |
|---|---|---|---|
| 1 | Flet depende de Flutter → *cold start* alto, sobre todo en móvil | Arranque lento percibido | Priorizar Windows (menos sensible); medir arranque en Fase 4/5; evitar trabajo pesado al inicio |
| 2 | **iOS requiere Mac** (o CI con runner macOS), no disponible | iPhone/iPad no sale en el alcance actual | **Decisión: iOS pospuesto y fuera del alcance actual**; Fase 5 limitada a Android (APK); no bloquea el MVP; retomar solo con Mac o CI `macos-*` |
| 3 | Ecosistema de extensiones de Flet pequeño | Falten widgets/gráficos | Limitarse a widgets Material nativos + `flet-charts`; lógica propia en `core` |
| 4 | Móvil menos probado que desktop | Bugs en Android | Orden estricto: Windows primero; diseñar UI responsive desde Fase 2 |
| 5 | Cambios de licencia/estrategia de la empresa detrás de Flet | Ruptura de toolchain | Fijar versión en `pyproject.toml`; abstraer UI en `ui/` para migrar con menor coste; revisar changelog antes de actualizar |
| 6 | Corrupción de datos / pérdida por crash con entry abierta | Pérdida de tiempos | WAL + transacciones; entry abierta se recuperan al arrancar; backup puntual del `.db` documentado |
| 7 | Concurrencia de hilos con `sqlite3` | Errores "database is locked" | **Decisión fijada (§4):** conexión única por proceso con `check_same_thread=False` + `threading.RLock`; todo acceso (incluido el hilo de eventos de Flet) serializado por ese lock |
| 8 | Cambios de esquema futuros | BDs existentes incompatibles | Migraciones versionadas (`PRAGMA user_version`) desde v1 |
| 9 | Sobredimensionar el alcance | Retrasos | MVP = Fases 0–3; empaquetado y móvil son post-MVP |

---

## 9. Criterios de aceptación del MVP

El MVP se considera terminado cuando, en **Windows**:

1. La app arranca y muestra la pantalla de crear/seleccionar sesión con una interfaz limpia y sin ruido visual.
2. Se puede crear una sesión con nombre o **continuar la sesión actualmente abierta**; **la lista de sesiones persiste entre arranques** y las cerradas se consultan en **solo lectura** (no se reabren).
3. Se pueden crear **tareas en el catálogo global** (solo nombre, únicas por `strip()`) y se persisten; se reutilizan entre sesiones.
4. Al pulsar una tarea se registra la fecha/hora de inicio; al cambiar de tarea, la anterior guarda su `ended_at` y la nueva empieza — **nunca hay dos intervalos abiertos a la vez**.
5. El cronómetro de la tarea en curso se ve avanzando en pantalla.
6. Al terminar la sesión se cierra el intervalo abierto, la sesión queda cerrada y **toda la lista de intervalos es visible y persiste**.
7. El reporting muestra totales por tarea, por día y por semana, con al menos un filtro de rango de fechas y un gráfico.
8. `pytest` pasa en verde (dominio, persistencia y reporting).
9. Los cálculos de duración cuadran con la suma de intervalos (verificado con datos de prueba conocidos).

**No exigido para el MVP** (fases posteriores): .exe empaquetado (Fase 4), Android (Fase 5). **iOS queda fuera del alcance actual** (pospuesto hasta disponer de Mac o CI con runner macOS), por lo que no forma parte de los criterios de aceptación.

---

## Historial de cambios

| Fecha | Cambio | Autor |
|---|---|---|
| 2026-11-18 | Creación inicial del plan (Fases 0–5, modelo de datos y arquitectura) | Agente de planificación |
| 2026-11-18 | Decisiones del usuario aplicadas: `uv` fijado como gestor de dependencias; iOS pospuesto y fuera del alcance actual (Fase 5 = solo Android APK); CI con pytest marcado como opcional recomendado pendiente de decisión (no bloquea Fase 1); estrategia de hilos de SQLite fijada (conexión única por proceso con `check_same_thread=False` + lock). Se retiran todas las marcas `[PENDIENTE]` | Agente bibliotecario |
| 2026-11-18 | **Fases 0 y 1 completadas** (núcleo + persistencia; roadmap actualizado y README reescrito). Decisiones de diseño de implementación fijadas por **makerman**: timestamps **UTC aware** + **ISO-8601 terminado en `Z`**; duraciones en **enteros de segundos**; conexión SQLite **única por proceso** con **`RLock`** + **WAL** (+ `foreign_keys = ON`, `synchronous = NORMAL`); migraciones por **`PRAGMA user_version = 1`**; **reloj inyectable** (`now: Callable[[], datetime]`) para tests; dependencias fijadas **`flet==1.1.2`** (+ `flet-cli`, `flet-desktop` — **desviación justificada**: Flet 1.x no las empaqueta en `flet`; sin `flet-cli`, `flet.exe` se autoinstala en el Python del sistema); BD por defecto en **`~/.time_tracker/time_tracker.db`** (+ `-wal`/`-shm`). Decisiones de negocio: **no-op al re-seleccionar la tarea en curso** (evita micro-intervalos); **se permiten varias sesiones abiertas** (solo 1 entry abierta global — *decisión de diseño de implementación, confirmar con usuario*; **sustituida por la decisión de sesión única abierta, ver filas siguientes**). La suite `tests/` queda **a cargo del agente tester** (puede no existir aún o estar en curso). §4 y §8 ajustados: `threading.Lock` → `threading.RLock`; notación de columnas de timestamp corregida. | Agente bibliotecario (implementación: makerman) |
| 2026-11-18 | **Decisiones del usuario (§5 actualizado):** **(1) Nuevo modelo de datos — tareas globales estilo Toggl** (motivo: reutilizar tareas como "Correo"/"Reuniones" entre días/sesiones): `tasks` **sin `session_id`** (`name UNIQUE` tras `strip()`, homónimos → `DuplicateTaskError`), `time_entries` **añade `session_id`** (FK a `sessions` `ON DELETE CASCADE` + `idx_entries_session`) — **DDL v2, `PRAGMA user_version = 2`** (migración v1 *best-effort* por *makerman*; app pre-lanzamiento, BD v1 solo en dev). Al borrar una sesión se borran sus entries en cascada pero **las tareas sobreviven al catálogo**. **(2) Sesiones cerradas = historial de solo lectura**: no se reabren; al arrancar solo crear sesión nueva o continuar la abierta; operar sobre una cerrada lanza `SessionClosedError`. **(3)** Regla de **sesión única abierta: ya IMPLEMENTADA** (auto-cierre en `crear_sesion`, abiertas + entry global en una transacción con un único `now`; `seleccionar_sesion` no cierra ni reabre). | Agente bibliotecario |
| 2026-11-18 | **Implementación (Fase 1):** regla de **sesión única abierta** implementada por **makerman**; añadido **`pytest-cov>=6`** al group `dev` de `pyproject.toml` (resuelto 7.1.0 + coverage 7.17.3). **Corrección FK-vs-UNIQUE** en `storage/sqlite_repository.py`: por `sqlite_errorcode`, `SQLITE_CONSTRAINT_UNIQUE` → `DuplicateTaskError`; FK u otra integridad → `StorageError`. Normalización `strip()` ahora en **dos capas** (servicio y modelo, idempotente). `.gitignore` ampliado. **Nota:** la Fase 1 queda "completada con refactor de modelo en curso" (ver Fase 1b). | Agente bibliotecario |
| 2026-11-19 | **Cierre de Fase 1b (modelo de tareas globales), verificado por el coordinador.** DDL v2 (`user_version = 2`) + migración v1→v2 implementada y smoke-verificada: **transaccional** (rollback → BD intacta en v1), **idempotente** (`user_version = 2`), homónimos **fusionados con `MIN(id)`/`MIN(created_at)`**, entries heredan `session_id` de la task vieja, **huérfanos descartados**, `foreign_key_check` limpio. **Suite: 147 tests → ✅ 147 passed, 0 failed, 0 xfail; cobertura `core`+`storage` = 100 %** (`uv run pytest --cov=core --cov=storage`); **retirado el antiguo xfail FK** (bug FK-vs-UNIQUE corregido y en verde). **Decisión confirmada:** `seleccionar_sesion` sobre sesión cerrada **NO lanza** (historial consultable de solo lectura); las escrituras `iniciar_tarea`/`cerrar_sesion` sobre ella → **`SessionClosedError`** (§5.3.4 actualizado). Roadmap: Fase 1b checklist ✅ completo y Fase 1 sin la nota "refactor en curso". Añadida en §4 la **API v2 para la Fase 2 (UI)**. README actualizado (estado + comando de cobertura). | Agente bibliotecario |
| 2026-11-19 | **Fase 2 (UI Flet) — implementada, EN VERIFICACIÓN (checklist sin marcar).** Estructura cerrada: `ui/app.py` (`TimeTrackerApp`, rutas `/` y `/sesion/<id>`, pila con atrás nativo, relee BD y repinta tras cada acción), `ui/theme.py` (Material 3, semilla índigo, ventana 1120×800 mín. 800×600, columna centrada 740 px con scroll), `ui/pages/inicio.py`, `ui/pages/sesion.py` y capas puras sin Flet `ui/format.py`, `ui/errores.py`, `ui/logica.py` (testabilidad sin GUI). **Decisiones UX cerradas** (§6.1 nuevo): tema **`ThemeMode.SYSTEM`** (usuario); **"Terminar sesión" con confirmación SOLO si hay tarea cronometrada** (usuario); **formatos** — totales de portada legibles `1 h 23 min`, intervalos precisos `hh:mm:ss` con >23 h (coordinador); **sin snackbar de éxito al añadir tarea** (coordinador); **errores de dominio → SnackBar 4 s** con `mensaje_usuario()` (dominio en español; `StorageError`/inesperadas → genérico, **jamás traza**); **confirmación modal en "eliminar sesión"** advirtiendo que el **catálogo de tareas se conserva**; **cronómetro** con *tick* 1 s vía `page.run_task` **recalculado desde `started_at` real** (persiste entre arranques); **sesión cerrada = solo lectura en dos capas** (`SessionClosedError` en servicio + vista sin controles de escritura). README actualizado al estado "Fase 2 implementada (en verificación)". **Falta:** pasada de verificación del coordinador/tester — checklist de Fase 2 **NO marcado**. | Agente bibliotecario |
| 2026-11-20 | **Cierre de Fase 2 (UI Flet), completada y verificada por el coordinador.** **Suite: 225 tests → ✅ 225 passed, 0 failed, 0 xfail** (78 tests nuevos de UI: `test_ui_format` 17, `test_ui_logica` 19, `test_ui_app` 26, `test_ui_vistas` 9, `test_ui_errores` 7; ayudante `tests/ui_util.py`). **Cobertura 100 % en `core`+`storage` y también 100 % en `ui/`**; **sin bugs** en la UI; **sin plugin de Flet para pytest** (las `ft.View` se construyen headless). Tests de UI verifican el contrato §6.1, incluido el **test clave**: sesión cerrada = **ni botones ni TextField de escritura**; handlers con `PaginaFalsa` (crear/abrir/terminar con confirmación **solo si hay entry en curso**; eliminar con aviso de catálogo); `ThemeMode.SYSTEM`; cronómetro **recalculado desde `started_at`**. **Único no cubierto: `main.py`** (bootstrap Flet real, requiere GUI) — **alcance razonable** anotado en §7. Roadmap: checklist de Fase 2 **✅ completo** y notas de §6/§6.1 actualizadas a "completada y verificada (20/11/2026)". §7 ajustado a la realidad (tests de UI hechos, cobertura `ui/`). README actualizado (estado "Fases 0-2 completadas" + 225 tests). | Agente bibliotecario |
