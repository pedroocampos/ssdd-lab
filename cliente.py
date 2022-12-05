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

INTENTOS_RECONEXION = 3

class Cliente(Ice.Application):

    servicio_main = None
    servicio_autenticacion = None
    servicio_catalogo = None

    logging.basicConfig(level=logging.NOTSET)

    def conectar_main(self):
        '''
        Para conectarte al servicio Main
        '''
        intentos = 0
        proxy_main = self.communicator().stringToProxy("proxy")
        if not proxy_main:
            logging.error("Proxy inválido")
        while intentos != INTENTOS_RECONEXION:
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
        while intentos != INTENTOS_RECONEXION:
            try:
                intentos += 1
                self.servicio_autenticacion = IceFlix.Authenticator.checkedCast(proxy_authenticator)
            except (IceFlix.TemporaryUnavailable, Ice.Exception):
                logging.error("Proxy inválido. Intentando reconectar...")
                self.servicio_autenticacion = None
                time.sleep(5)
                continue
            break

    def conectar_catalogo(self):
        '''
        Para conectarte al servicio Catalogo
        '''
        if not self.servicio_catalogo:
            intentos = 0
            #proxy_catalogo = self.servicio_main.getCatalog()
            proxy_catalogo = "proxy"
            if not proxy_catalogo:
                logging.error("Proxy invalido")
            while intentos != INTENTOS_RECONEXION:
                try:
                    intentos += 1
                    self.servicio_catalogo = IceFlix.MediaCatalog.checkedCast(proxy_catalogo)
                except (IceFlix.TemporaryUnavailable, Ice.Exception):
                    logging.error("Proxy inválido. Intentando reconectar...")
                    self.servicio_catalogo = None
                    time.sleep(5)
                    continue
                break

    def desconectar_servicio(self):
        '''
        Para desconectarte
        '''
        self.servicio_main = None

    def cerrar_sesion(self):
        '''
        Para cerrar la sesion
        '''
        self.servicio_autenticacion = None
        self.servicio_catalogo = None
        self.token = None

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

    def realizar_busqueda(self):
        self.conectar_catalogo()
        #self.servicio_catalogo = "servicio_catalogo"
        if not self.servicio_catalogo:
            logging.error("No se ha podido conectar con el catálogo")
            return

        tipo_busqueda = input("¿Quiere buscar por nombre o tags? [nombre/tags] ")
        if tipo_busqueda == "nombre":
            titulos = self.buscar_por_nombre()
        elif tipo_busqueda == "tags":
            if not self.servicio_autenticacion:
                logging.error("No has iniciado sesión <autenticar>")
                return
            titulos = self.buscar_por_tags()
        else:
            return

        self.resultados_busqueda.clear() # Elimino la anterior busqueda
        self.resultados_busqueda = dict((i+1,j) for i, j in enumerate(titulos))
        print("Resultados:")
        print(self.resultados_busqueda)

    def buscar_por_nombre(self):
        '''
        Para buscar un titulo en el catalogo por nombre
        '''
        titulos = []
        nombre_titulo = input("Nombre del título que desea: ")
        termino_exacto = bool(input("¿Es el nombre exacto del título que desea? [si/no] ") == "si")
        media_ids = self.servicio_catalogo.getTilesByName(nombre_titulo, termino_exacto).copy()

        if not media_ids:
            logging.error("No se han obtenido resultados")
        else:
            titulos = self.buscar_titulos_por_id(media_ids)

        return titulos

    def buscar_por_tags(self):
        '''
        Para buscar un titulo en el catalogo por tags
        '''
        titulos = []
        tags = input("Introduzca una lista de tags, separados por un espacio ").split()
        incluir_tags = bool(input("¿Quiere incluir todos los tags en la búsqueda? [si/no]") == "si")
        if not incluir_tags:
            tags = input("Introduzca los tags que desea de la lista, separados por un espacio: " + str(tags) + " ").split()
        try:
            media_ids = self.servicio_catalogo.getTilesByTags(tags, incluir_tags, self.token).copy()
        except IceFlix.Unauthorized:
            logging.error("El token de autenticación no es correcto")
            return

        if not media_ids:
            logging.error("No se han obtenido resultados")
        else:
            titulos = self.buscar_titulos_por_id()

        return titulos

    def buscar_titulos_por_id(self, ids):
        titulos = []
        try:
            for id in ids:
                titulos.append(self.servicio_catalogo.getTile(id, self.token))
            return titulos
        except IceFlix.WrongMediaId:
            logging.error("Ha habido un error con el id")
        except IceFlix.TemporaryUnavailable:
            logging.error("El servicio catálogo no se encuentra disponible")
        except IceFlix.Unauthorized:
            logging.error("El token de autenticación no es correcto")

    def main(self):
        terminal = cmd_cliente.Terminal()
        terminal.cmdloop()

if __name__ == "__main__":
    Cliente().main()
