"""Coordina la UI Flet: navegación, refresco de estado y cronómetro (Fase 2).

`ui/app.py` es la parte "viva" (página, vistas, diálogos); la lógica de
presentación pura vive en `ui/logica` y `ui/format`, y las pantallas solo
componen controles en `ui/pages`.

Contratos clave:
- Toda acción llama al servicio y, si termina bien, RELEE el estado desde la
  BD y vuelve a pintar (los modelos son inmutables: un snapshot previo nunca
  refleja los cierres posteriores).
- Si el servicio lanza un error de dominio (`ValidationError`,
  `DuplicateTaskError`, `SessionClosedError`, ...), se muestra como snack
  limpio (`ui/errores`) y NO se refresca: así se conserva lo que la persona
  tenía escrito en el campo. Nada de trazas en pantalla.
- El cronómetro se actualiza cada segundo con `page.run_task`, leyendo el
  `started_at` de la entry en curso (persiste entre arranques: se recalcula
  contra el reloj real al pintar la vista).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Callable

import flet as ft

from core.exceptions import SessionNotFoundError, TimeTrackerError
from core.models import Session, TimeEntry, utc_now
from core.services import TimeTrackerService
from ui import format as fmt, logica, theme
from ui.errores import mensaje_usuario
from ui.pages.inicio import construir_vista_inicio
from ui.pages.sesion import construir_vista_sesion


class TimeTrackerApp:
    """Aplicación de escritorio: enruta, pinta y delega en el servicio."""

    def __init__(self, page: ft.Page, service: TimeTrackerService) -> None:
        self.page = page
        self.service = service
        # Cronómetro: control vivo de la vista de sesión + inicio de la entry
        self._lbl_crono: ft.Text | None = None
        self._crono_inicio: datetime | None = None
        self._tick_future: Any = None

    # --------------------------------------------------------------- arranque

    def arrancar(self) -> None:
        """Tema, handlers, recuperación de estado y primer pintado.

        Persistencia entre arranques: si al abrir la app hay una sesión
        abierta, se selecciona; la entry en curso se lee de la BD y su
        `started_at` (UTC) alimenta el cronómetro, que sigue contando desde
        el momento real en que se inició.
        """
        theme.configurar_pagina(self.page)
        self.page.on_route_change = self._al_cambiar_ruta
        self.page.on_view_pop = self._al_cerrar_vista
        self._recuperar_estado()
        self._pintar(self.page.route or logica.RUTA_INICIO)
        self._tick_future = self.page.run_task(self._bucle_cronometro)

    def _recuperar_estado(self) -> None:
        """Selecciona la sesión abierta, si la hay (una sola por regla)."""
        abierta = next(
            (s for s in self.service.listar_sesiones() if s.is_open), None
        )
        if abierta is not None:
            self.service.seleccionar_sesion(abierta.id)

    # ------------------------------------------------------------ navegación

    def _al_cambiar_ruta(self, e: Any) -> None:
        """`page.on_route_change`: relee y pinta la vista de `e.route`."""
        self._pintar(e.route)

    async def _al_cerrar_vista(self, e: Any) -> None:
        """`page.on_view_pop`: botón atrás del sistema → vista anterior."""
        vistas = self.page.views
        vista = getattr(e, "view", None)
        if vista is not None and any(v is vista for v in vistas):
            vistas.remove(vista)
        destino = vistas[-1].route if vistas else logica.RUTA_INICIO
        if destino == self.page.route:
            self._pintar(destino)  # misma ruta: sin evento, pintamos a mano
        else:
            await self.page.push_route(destino)

    def _volver_inicio(self) -> None:
        self.page.navigate(logica.RUTA_INICIO)

    def _refrescar(self) -> None:
        """Relee el estado de la BD y repinta la vista actual."""
        self._pintar(self.page.route or logica.RUTA_INICIO)

    # --------------------------------------------------------------- pintado

    def _pintar(self, route: str | None = None) -> None:
        """Reconstruye TODAS las vistas desde un snapshot fresco del servicio.

        La pila de vistas es `[inicio, sesión]` cuando se está en una sesión:
        así el botón "atrás" del sistema funciona de forma nativa.
        """
        page = self.page
        ruta = route if route is not None else (page.route or logica.RUTA_INICIO)
        sid = logica.id_sesion_de_ruta(ruta)
        ahora = utc_now()

        sesion: Session | None = None
        if sid is not None:
            try:
                sesion = self.service.seleccionar_sesion(sid)
            except SessionNotFoundError:
                # La sesión ya no existe (p. ej. eliminada): vuelta al inicio.
                page.navigate(logica.RUTA_INICIO)
                return

        vistas: list[ft.View] = [self._vista_inicio(ahora)]
        if sesion is not None:
            vistas.append(self._vista_sesion(sesion, ahora))

        page.views.clear()
        page.views.extend(vistas)
        page.update()

    def _vista_inicio(self, ahora: datetime) -> ft.View:
        """Snapshot de portada: sesiones con su duración total."""
        resumenes = [
            logica.resumen_sesion(
                s, self.service.listar_intervalos(s.id), ahora
            )
            for s in self.service.listar_sesiones()
        ]
        return construir_vista_inicio(
            resumenes,
            on_crear=self._crear_sesion,
            on_abrir=self._abrir_sesion,
            on_eliminar=self._eliminar_sesion,
        )

    def _vista_sesion(self, sesion: Session, ahora: datetime) -> ft.View:
        """Snapshot de la sesión: intervalos, catálogo y entry en curso."""
        intervalos = self.service.listar_intervalos(sesion.id)
        tareas = self.service.listar_tareas()
        entrada = logica.entrada_de_sesion(
            self.service.entry_abierta(), sesion.id
        )

        # Control vivo del cronómetro: lo actualiza el tick de 1 s.
        if entrada is not None:
            valor = fmt.hhmmss(logica.segundos_desde(entrada.started_at, ahora))
            self._lbl_crono = ft.Text(
                valor, size=44, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN
            )
            self._crono_inicio = entrada.started_at
        else:
            self._lbl_crono = ft.Text(
                "00:00:00", size=44, weight=ft.FontWeight.BOLD,
                color=ft.Colors.OUTLINE,
            )
            self._crono_inicio = None

        sid = sesion.id or 0
        return construir_vista_sesion(
            sesion,
            tareas=tareas,
            intervalos=intervalos,
            entrada=entrada,
            ahora=ahora,
            lbl_crono=self._lbl_crono,
            on_anadir_tarea=self._anadir_tarea,
            on_iniciar_tarea=self._iniciar_tarea,
            on_detener=self._detener,
            on_terminar_sesion=lambda: self._terminar_sesion(sid),
            on_volver=self._volver_inicio,
        )

    # -------------------------------------------------------------- acciones

    def _crear_sesion(self, nombre: str) -> None:
        try:
            nueva = self.service.crear_sesion(nombre)
        except TimeTrackerError as exc:
            self._mostrar_error(exc)
            return
        # crear_sesion ya la deja seleccionada; navegar repinta con snapshot
        self.page.navigate(logica.ruta_sesion(nueva.id))

    def _abrir_sesion(self, session_id: int) -> None:
        try:
            self.service.seleccionar_sesion(session_id)
        except TimeTrackerError as exc:
            self._mostrar_error(exc)
            return
        self.page.navigate(logica.ruta_sesion(session_id))

    def _eliminar_sesion(self, session_id: int, nombre: str) -> None:
        def confirmado() -> None:
            try:
                self.service.eliminar_sesion(session_id)
            except TimeTrackerError as exc:
                self._mostrar_error(exc)
                return
            self._refrescar()
            self._mostrar_mensaje(f"Sesión '{nombre}' eliminada.")

        self._confirmar(
            titulo="Eliminar sesión",
            mensaje=(
                f"Se eliminará '{nombre}' y todos sus intervalos. "
                "Las tareas del catálogo global se conservan."
            ),
            etiqueta="Eliminar",
            on_aceptar=confirmado,
        )

    def _anadir_tarea(self, nombre: str) -> None:
        try:
            self.service.añadir_tarea(nombre)
        except TimeTrackerError as exc:
            # No se refresca: el campo conserva lo escrito para corregirlo.
            self._mostrar_error(exc)
            return
        self._refrescar()

    def _iniciar_tarea(self, task_id: int) -> None:
        try:
            self.service.iniciar_tarea(task_id)
        except TimeTrackerError as exc:
            self._mostrar_error(exc)
            return
        self._refrescar()

    def _detener(self) -> None:
        try:
            self.service.detener_tarea()
        except TimeTrackerError as exc:
            self._mostrar_error(exc)
            return
        self._refrescar()

    def _terminar_sesion(self, session_id: int) -> None:
        entrada = self.service.entry_abierta()
        if entrada is not None and entrada.session_id == session_id:
            # Hay tarea en curso: confirmar (la cierra junto con la sesión)
            nombre_tarea = logica.nombre_tarea(
                self.service.listar_tareas(), entrada.task_id
            )
            self._confirmar(
                titulo="Terminar sesión",
                mensaje=(
                    f"Hay una tarea en curso ('{nombre_tarea}'). "
                    "Se detendrá y la sesión quedará cerrada (solo lectura)."
                ),
                etiqueta="Terminar",
                on_aceptar=lambda: self._cerrar_sesion(session_id),
            )
        else:
            self._cerrar_sesion(session_id)

    def _cerrar_sesion(self, session_id: int) -> None:
        try:
            self.service.cerrar_sesion(session_id)
        except TimeTrackerError as exc:
            self._mostrar_error(exc)
            return
        self._refrescar()
        self._mostrar_mensaje(
            "Sesión terminada: ya no se puede cronometrar en ella."
        )

    # ------------------------------------------------------------- cronómetro

    async def _bucle_cronometro(self) -> None:
        """Bucle infinito de 1 s (lanzado con `page.run_task` al arrancar)."""
        while True:
            await asyncio.sleep(1)
            self._tick_cronometro()

    def _tick_cronometro(self) -> None:
        """Recalcula el cronómetro contra el reloj real (UTC → segundos)."""
        lbl, inicio = self._lbl_crono, self._crono_inicio
        if lbl is None or inicio is None:
            return  # sin entry en curso (o en portada): nada que latir
        try:
            texto = fmt.hhmmss(logica.segundos_desde(inicio, utc_now()))
            if texto != lbl.value:
                lbl.value = texto
                lbl.update()  # solo el texto: sin repintar la vista
        except Exception:
            # La vista pudo reconstruirse entre ticks; el siguiente lo
            # reintenta con el control vivo de la vista actual.
            pass

    # --------------------------------------------------------------- feedback

    def _mostrar_error(self, exc: BaseException) -> None:
        """Error de dominio → snack limpio, jamás una traza en pantalla."""
        self._mostrar_mensaje(mensaje_usuario(exc))

    def _mostrar_mensaje(self, texto: str) -> None:
        self.page.show_dialog(
            ft.SnackBar(ft.Text(texto), show_close_icon=True)
        )

    def _confirmar(
        self, *, titulo: str, mensaje: str, etiqueta: str,
        on_aceptar: Callable[[], None],
    ) -> None:
        """Diálogo modal de confirmación (eliminar / terminar sesión)."""
        page = self.page

        def cancelar(e: Any) -> None:
            page.pop_dialog()

        def aceptar(e: Any) -> None:
            page.pop_dialog()
            on_aceptar()

        page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(titulo),
                content=ft.Text(mensaje),
                actions=[
                    ft.TextButton("Cancelar", on_click=cancelar),
                    ft.FilledButton(etiqueta, on_click=aceptar),
                ],
                actions_alignment=ft.MainAxisAlignment.END,
            )
        )
