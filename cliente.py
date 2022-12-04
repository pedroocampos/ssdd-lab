#!/usr/bin/python3

import logging
import time
import hashlib
import getpass
import threading
import Ice
Ice.loadSlice('IceFlix.ice')
import IceFlix
import cmd_cliente

class Cliente(Ice.Application):

    servicio_main = None
    servicio_autenticacion = None

    logging.basicConfig(level=logging.NOTSET)

    def conectar_main(self):
        '''
        Para conectarte al servicio Main
        '''
        intentos = 0
        proxy_main = self.communicator().stringToProxy("proxy")
        if not proxy_main:
            logging.error("Proxy inválido")
        while intentos != 3:
            try:
                intentos += 1
                self.servicio_main = IceFlix.Main.checkedCast(proxy_main)
            except Ice.Exception:
                logging.error("Proxy inválido. Intentando reconectar...")
                self.servicio_main = None
                time.sleep(5)
                continue
            break

    def conectar_autenticador(self):
        '''
        Para conectarte al servicio Authenticator
        '''
        intentos = 0
        proxy_authenticator = self.servicio_main.getAuthenticator()
        if not proxy_authenticator:
            logging.error("Proxy invalido")
        while intentos != 3:
            try:
                intentos += 1
                self.servicio_autenticacion = IceFlix.Authenticator.checkedCast(proxy_authenticator)
            except (IceFlix.TemporaryUnavailable, Ice.Exception):
                logging.error("Proxy inválido. Intentando reconectar...")
                self.servicio_autenticacion = None
                time.sleep(5)
                continue
            break

    def desconectar_servicio(self):
        '''
        Para desconectarte
        '''
        self.servicio_main = None

    def autenticar(self):
        '''
        Llama al metodo para conectarte al servicio Authenticator y si la conexion
        ha ido bien te solicita las credenciales
        '''
        self.conectarAutenticador()
        if not self.servicio_autenticacion:
            logging.error("No se ha podido conectar con el autenticador")
            return
        nombre_usuario = input("Usuario: ")
        contrasena = getpass.getpass("Contraseña: ")
        contrasena = str(hashlib.sha256(contrasena.encode()).hexdigest)
        self.pedir_token(nombre_usuario, contrasena)

    def pedir_token(self, nombre_usuario, contrasena):
        '''
        Codigo que se ejecuta cada 2 minutos mientras que el usuario no cierre sesion
        He usado threading.Timer para conseguir hacer otras cosas de forma concurrente
        mientras esta funcion se ejecuta
        '''
        try:
            if self.servicio_autenticacion is not None:
                print("pidiendo token")
                #self.token = self.servicio_autenticacion.refreshAuthorization(nombre_usuario, contrasena)
        except IceFlix.Unauthorized:
            logging.error("Ha ocurrido un error en la autenticación")
            return

        hilo = threading.Timer(120.0, self.pedir_token, args=(nombre_usuario, contrasena))
        hilo.start()
        if self.servicio_autenticacion is None:
            hilo.cancel()

    def main(self):
        terminal = cmd_cliente.Terminal()
        terminal.cmdloop()

if __name__ == "__main__":
    Cliente().main()