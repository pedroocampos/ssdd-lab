#!/usr/bin/python3

import cmd
import os
import logging
from colorama import Fore, Style
from cliente import Cliente

class Terminal(cmd.Cmd):
    '''
    Clase que controla el funcionamiento
    de la terminal del cliente
    '''

    intro = Style.BRIGHT + Fore.YELLOW + "Introduce help para ver la lista de comandos" + Fore.RESET
    prompt = Style.BRIGHT +"<Cliente> " + Fore.RESET

    cliente = Cliente()

    logging.basicConfig(level=logging.NOTSET)

    def conectado(self):
        '''
        Método para ver si un usuario se encuentra conectado
        '''
        return self.cliente.servicio_main is not None

    def cambiar_prompt(self):
        '''
        Método que controla el cambio del prompt
        '''
        if self.cliente.servicio_autenticacion is not None:
            logging.info("Puedes cerrar sesión con el comando <cerrar_sesion>")
            self.prompt = Style.BRIGHT + Fore.GREEN + "<(Conectado y autenticado) Cliente)> " + Fore.RESET
        elif self.conectado():
            logging.info("Recuerda que puedes autenticarte con el comando <autenticar>")
            self.prompt = Style.BRIGHT + Fore.GREEN + "<(Conectado) Cliente> " + Fore.RESET
        else:
            self.prompt = Style.BRIGHT +"<Cliente> " + Fore.RESET

    def do_clear(self):
        "Deja la terminal como recién abierta"
        os.system("clear")
        print(self.intro)

    def do_exit(self):
        "Para salir de la terminal"
        os._exit(os.EX_OK)

    def default(self):
        logging.error("Orden no encontrada")

    def do_conectar(self):
        "Para conectarte al servicio Main"
        if self.conectado():
            logging.error("Ya estás conectado")
            return
        self.cliente.conectar_main()
        self.cambiar_prompt()

    def do_desconectar(self):
        "Para desconectarte del servicio Main"
        if not self.conectado():
            logging.error("No estás conectado <conectar>")
            return
        self.cliente.desconectar_servicio()
        self.cambiar_prompt()

    def do_autenticar(self):
        "Para autenticarte en el sistema"
        if not self.conectado():
            logging.error("No estás conectado <conectar>")
            return
        if not self.cliente.servicio_autenticacion:
            logging.error("Ya tienes una sesión iniciada")
            return
        nombre_usuario, contrasena = self.cliente.autenticar()
        self.cliente.pedir_token(nombre_usuario, contrasena)
        self.cambiar_prompt()

    def do_cerrar_sesion(self):
        "Para cerrar sesión"
        if self.cliente.servicio_autenticacion is None:
            logging.error("No has iniciado sesión")
        self.cliente.cerrar_sesion()
        self.cambiar_prompt()

    def do_realizar_busqueda(self):
        "Para buscar títulos en el catálogo"
        if not self.conectado():
            logging.error("No estás conectado <conectar>")
            return
        self.cliente.realizar_busqueda()

    def do_seleccionar_titulo(self):
        "Para seleccionar uno de los títulos de la última búsqueda realizada"
        if not self.cliente.resultados_busqueda:
            logging.error("Primero debes realizar una búsqueda <realizar_busqueda>")
            return
        self.cliente.seleccionar_titulo()

    def do_descargar_archivo(self):
        "Para descargar el título seleccionado"
        if not self.conectado():
            logging.error("No estás conectado <conectar>")
            return
        if not self.cliente.servicio_autenticacion:
            logging.error("Debes iniciar sesión <autenticar>")
        if not self.cliente.titulo_seleccionado:
            logging.error("Primero debes seleccionar un título <seleccionar_titulo>")
            return
        self.cliente.descargar_archivo()

    def do_tareas_administrativas(self):
        "Para acceder a las tareas administrativas"
        if not self.conectado():
            logging.error("No estás conectado <conectar>")
            return
        self.cliente.tareas_administrativas()