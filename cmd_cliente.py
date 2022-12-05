#!/usr/bin/python3

import cmd
import os
import logging
from colorama import Fore, Style
from cliente import Cliente

class Terminal(cmd.Cmd):

    intro = Style.BRIGHT + Fore.YELLOW + "Introduce help para ver la lista de comandos" + Fore.RESET
    prompt = Style.BRIGHT +"<Cliente> " + Fore.RESET

    cliente = Cliente()

    logging.basicConfig(level=logging.NOTSET)

    def cambiar_prompt(self):
        if self.cliente.servicio_autenticacion is not None:
            logging.info("Puedes cerrar sesión con el comando <cerrar_sesion>")
            self.prompt = Style.BRIGHT + Fore.GREEN + "<(Conectado y autenticado) Cliente)> " + Fore.RESET
        elif self.conectado():
            logging.info("Recuerda que puedes autenticarte con el comando <autenticar>")
            self.prompt = Style.BRIGHT + Fore.GREEN + "<(Conectado) Cliente> " + Fore.RESET
        else:
            self.prompt = Style.BRIGHT +"<Cliente> " + Fore.RESET

    def conectado(self):
        return self.cliente.servicio_main is not None

    def do_conectar(self, line):
        "Para conectarte al servicio Main"
        if self.conectado():
            logging.error("Ya estás conectado")
            return
        self.cliente.conectar_main()
        self.cambiar_prompt()

    def do_desconectar(self, line):
        "Para desconectarte del servicio Main"
        if not self.conectado():
            logging.error("No estás conectado <conectar>")
            return
        self.cliente.desconectar_servicio()
        self.cambiar_prompt()

    def do_autenticar(self, line):
        "Para autenticarte en el sistema"
        if not self.conectado():
            logging.error("No estás conectado <conectar>")
            return
        elif self.cliente.servicio_autenticacion is not None:
            logging.error("Ya tienes una sesión iniciada")
            return
        self.cliente.autenticar()
        self.cambiar_prompt()

    def do_cerrar_sesion(self, line):
        "Para cerrar sesión"
        if self.cliente.servicio_autenticacion is None:
            logging.error("No has iniciado sesión")
        self.cliente.cerrar_sesion()
        self.cambiar_prompt()

    def do_realizar_busqueda(self, line):
        "Para buscar títulos en el catálogo"
        if not self.conectado():
            logging.error("No estás conectado <conectar>")
            return
        self.cliente.realizar_busqueda()

    def do_clear(self, line):
        "Deja la terminal como recién abierta"
        os.system("clear")
        print(self.intro)

    def do_exit(self, line):
        "Para salir de la terminal"
        os._exit(os.EX_OK)

    def default(self, line):
        logging.error("Orden no encontrada")
