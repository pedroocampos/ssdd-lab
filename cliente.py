#!/usr/bin/python3

#pylint: disable=C0413
#pylint: disable=E0401
import logging
import time
import getpass
import hashlib
import threading
import sys
import Ice
Ice.loadSlice('IceFlix.ice')
import IceFlix
import cmd_cliente

INTENTOS_RECONEXION = 3
TAM_BLOQUE = 1024

class FileUploaderI(IceFlix.FileUploader):
    '''
    Sirviente del FileUploader
    '''

    def __init__(self, fichero):
        self.contenido_fichero = open(fichero, "rb")

    def receive(self, size, current=None):
        '''
        Método que lee una cantidad de bytes
        '''
        self.contenido_fichero.read(size)

    def close(self, current=None):
        '''
        Método para parar la transferencia de datos
        '''
        self.contenido_fichero.close()
        current.adapter.remove(current.id)


class Cliente(Ice.Application):
    '''
    Implementación de la clase cliente
    '''

    servicio_main = None
    servicio_autenticacion = None
    servicio_catalogo = None
    servicio_ficheros = None
    token = None
    resultados_busqueda = []
    titulo_seleccionado = None

    logging.basicConfig(level=logging.NOTSET)

    def conectar_main(self):
        '''
        Para conectarte al servicio Main
        '''
        intentos = 0
        main_proxy = self.communicator().propertyToProxy("main_prx")
        while intentos != INTENTOS_RECONEXION:
            try:
                intentos += 1
                self.servicio_main = IceFlix.MainPrx.checkedCast(main_proxy)
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
        if not self.servicio_autenticacion:
            intentos = 0
            while intentos != INTENTOS_RECONEXION:
                try:
                    intentos += 1
                    self.servicio_autenticacion = self.servicio_main.getAuthenticator()
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
            while intentos != INTENTOS_RECONEXION:
                try:
                    intentos += 1
                    self.servicio_catalogo = self.servicio_main.getCatalog()
                except (IceFlix.TemporaryUnavailable, Ice.Exception):
                    logging.error("Proxy inválido. Intentando reconectar...")
                    self.servicio_catalogo = None
                    time.sleep(5)
                    continue
                break

    def conectar_servicio_ficheros(self):
        '''
        Para conectarte al servicio de ficheros
        '''
        intentos = 0
        while intentos != INTENTOS_RECONEXION:
            try:
                intentos += 1
                self.servicio_ficheros = self.servicio_main.getFileService()
            except (IceFlix.TemporaryUnavailable, Ice.Exception):
                logging.error("Proxy inválido. Intentando reconectar...")
                self.servicio_ficheros = None
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
        self.servicio_ficheros = None
        self.token = None

    def autenticar(self):
        '''
        Llama al metodo para conectarte al servicio Authenticator y si la conexion
        ha ido bien te solicita las credenciales
        '''
        self.conectar_autenticador()
        if not self.servicio_autenticacion:
            logging.error("No se ha podido conectar con el autenticador")
            return
        nombre_usuario = input("Usuario: ")
        contrasena = getpass.getpass("Contraseña: ")
        contrasena = str(hashlib.sha256(contrasena.encode()).hexdigest())
        return nombre_usuario, contrasena

    def pedir_token(self, nombre_usuario, contrasena):
        '''
        Codigo que se ejecuta cada 2 minutos mientras que el usuario no cierre sesion
        He usado threading.Timer para conseguir hacer otras cosas de forma concurrente
        mientras esta funcion se ejecuta
        '''

        try:
            if self.servicio_autenticacion is not None:
                self.token = self.servicio_autenticacion.refreshAuthorization(nombre_usuario, contrasena)
        except IceFlix.Unauthorized:
            logging.error("Ha ocurrido un error en la autenticación")
            self.token = None
            return

        hilo = threading.Timer(120.0, self.pedir_token, args=(nombre_usuario, contrasena))
        hilo.start()
        if self.servicio_autenticacion is None:
            hilo.cancel()

    def realizar_busqueda(self):
        '''
        Método que contiene todo el proceso para realizar una búsqueda
        '''
        self.conectar_catalogo()
        if not self.servicio_catalogo:
            logging.error("No se ha podido conectar con el catálogo")
            return

        tipo_busqueda = input("¿Quiere buscar por nombre o tags? [nombre/tags] ")
        if tipo_busqueda == "nombre":
            media_ids = self.buscar_por_nombre()
        elif tipo_busqueda == "tags":
            if not self.servicio_autenticacion:
                logging.error("No has iniciado sesión <autenticar>")
                return
            media_ids = self.buscar_por_tags()
        else:
            return

        if not media_ids:
            logging.error("No se han obtenido resultados")
        else:
            self.resultados_busqueda.clear()
            self.resultados_busqueda = self.buscar_titulos_por_id(media_ids)
            self.listar_titulos()

    def listar_titulos(self):
        '''
        Metodo para sacar por pantalla
        el titulo y tags de los titulos
        '''
        aux = 0
        for titulo in self.resultados_busqueda:
            print(str(aux) + ". " + titulo.info.name + " " + str(titulo.info.tags))
            aux += 1

    def buscar_por_nombre(self):
        '''
        Para buscar un titulo en el catalogo por nombre
        '''
        nombre_titulo = input("Nombre del título que desea: ")
        termino_exacto = bool(input("¿Quieres que la búsqueda sea exacta? [si/no] ") == "si")
        media_ids = self.servicio_catalogo.getTilesByName(nombre_titulo, termino_exacto)

        return media_ids

    def buscar_por_tags(self):
        '''
        Para buscar un titulo en el catalogo por tags
        '''
        tags = input("Introduzca una lista de tags, separados por un espacio ").split()
        incluir_tags = bool(input("¿Quiere incluir todos los tags en la búsqueda? [si/no] ") == "si")
        if not incluir_tags:
            tags = input("Introduzca los tags que desea de la lista, separados por un espacio: " + str(tags) + " ").split()
        try:
            media_ids = self.servicio_catalogo.getTilesByTags(tags, incluir_tags, self.token)
        except IceFlix.Unauthorized:
            logging.error("El token de autenticación no es correcto")
            return

        return media_ids

    def buscar_titulos_por_id(self, media_ids):
        '''
        Una vez tengo los media ids este método obtendrá los títulos
        de cada media id
        '''
        titulos = []
        try:
            for media_id in media_ids:
                titulos.append(self.servicio_catalogo.getTile(media_id, self.token))
            return titulos
        except IceFlix.WrongMediaId:
            logging.error("Ha habido un error con el id")
        except IceFlix.TemporaryUnavailable:
            logging.error("El servicio catálogo no se encuentra disponible")
        except IceFlix.Unauthorized:
            logging.error("El token de autenticación no es correcto")

    def seleccionar_titulo(self):
        '''
        Imprime el resultado de la ultima busqueda y te pide que
        selecciones un titulo
        '''
        print("Resultados de la última búsqueda:")
        self.listarTitulos()
        logging.info("Introduce el valor numérico que acompaña al título que deseas")
        indice = input("Selecciona un título ")
        self.titulo_seleccionado = self.resultados_busqueda[indice]
        editar_tags = bool(input("¿Quieres editar los tags de " + self.titulo_seleccionado.info.name + "? [si/no] ") == "si")
        if editar_tags:
            self.editar_tags()
            logging.info("Tags actualizados")

    def editar_tags(self):
        '''
        Metodo para añadir o eliminar tags de un titulo
        '''
        try:
            modo_edicion = input("¿Quiere añadir o eliminar tags? [añadir/eliminar]")
            if modo_edicion == "añadir":
                tags = input("Introduzca una lista de tags, separados por un espacio ").split()
                self.servicio_catalogo.addTags(self.titulo_seleccionado.mediaId, tags, self.token)
            elif modo_edicion == "eliminar":
                print("Tags de " + self.titulo_seleccionado.info.name + " " + str(self.titulo_seleccionado.info.tags))
                tags = input("Introduzca los tags que desea eliminar de la lista, separados por un espacio: ").split()
                self.servicio_catalogo.removeTags(self.titulo_seleccionado.mediaId, tags, self.token)
        except IceFlix.WrongMediaId:
            logging.error("Ha habido un error con el id")
        except IceFlix.Unauthorized:
            logging.error("No estás autorizado para realizar esta acción")


    def descargar_archivo(self):
        '''
        Método para descargar un archivo
        '''
        self.conectar_servicio_ficheros()
        if not self.servicio_ficheros:
            return
        try:
            print("Titulo seleccionado " + self.titulo_seleccionado.info.name)
            file_handler = self.servicio_ficheros.openFile(self.titulo_seleccionado.mediaId, self.token)

            while True:
                datos = file_handler.receive(TAM_BLOQUE, self.token)
                if datos == 0:
                    file_handler.close(self.token)
                    break
            logging.info("Descarga completada")
        except IceFlix.WrongMediaId:
            logging.error("Ha habido un error con el id")
        except IceFlix.Unauthorized:
            logging.error("No estás autorizado para realizar esta acción")


    # ------------------ TAREAS ADMINISTRATIVAS -------------------------

    def tareas_administrativas(self):
        '''
        Comprueba si un usuario es admin,
        si lo es saca por pantalla el menu
        correspondiente
        '''
        logging.info("Para acceder a estas tareas debes ser administrador")
        token_admin = getpass.getpass("Token de administrador: ")
        token_admin = str(token_admin)
        self.conectar_autenticador()
        if not self.servicio_autenticacion.isAdmin(token_admin):
            logging.error("No eres administrador")
        else:
            opcion_menu = self.menu_administrador()
            if opcion_menu == 1:
                self.añadir_usuario(token_admin)
            elif opcion_menu == 2:
                self.eliminar_usuario(token_admin)
            elif opcion_menu == 3:
                self.renombrar_archivo(token_admin)
            elif opcion_menu == 4:
                self.subir_fichero(token_admin)
            elif opcion_menu == 5:
                self.eliminar_fichero(token_admin)
            elif opcion_menu == 6:
                return

    def menu_administrador(self):
        '''
        Para sacar por pantalla el menú de administrador
        '''
        print("Seleccione una de las siguientes opciones:")
        print("1. Añadir usuario")
        print("2. Eliminar usuario")
        print("3. Renombrar archivo")
        print("4. Subir fichero")
        print("5. Eliminar fichero")
        print("6. Salir")
        opcion = input("Opción: ")
        if not opcion.isdigit() or int(opcion) not in range(1, 6):
            return
        return int(opcion)

    def añadir_usuario(self, token_admin):
        '''
        Para que un admin añada un usuario
        '''
        nombre_usuario, contrasena = self.autenticar()
        try:
            self.servicio_autenticacion.addUser(nombre_usuario, contrasena, token_admin)
        except IceFlix.TemporaryUnavailable:
            logging.error("El servicio de autenticación no se encuentra disponible")
        except IceFlix.Unauthorized:
            logging.error("Error al añadir el usuario")

    def eliminar_usuario(self, token_admin):
        '''
        Para que un admin elimine un usuario
        '''
        self.conectar_autenticador()
        nombre_usuario = input("Usuario: ")
        try:
            self.servicio_autenticacion.removeUser(nombre_usuario, token_admin)
        except IceFlix.TemporaryUnavailable:
            logging.error("El servicio de autenticación no se encuentra disponible")
        except IceFlix.Unauthorized:
            logging.error("Error al eliminar el usuario")

    def renombrar_archivo(self, token_admin):
        '''
        Para que un admin renombre un archivo
        '''
        if not self.titulo_seleccionado:
            logging.error("Primero debes seleccionar un título <seleccionar_titulo>")
            return
        try:
            print("Titulo seleccionado " + self.titulo_seleccionado.info.name)
            nuevo_nombre = input("Nuevo nombre del archivo ")
            self.servicio_catalogo.renameTile(self.titulo_seleccionado.mediaId, nuevo_nombre, token_admin)
        except IceFlix.WrongMediaId:
            logging.error("Ha habido un error con el id")
        except IceFlix.Unauthorized:
            logging.error("Error al renombrar el fichero")

    def subir_fichero(self, token_admin):
        '''
        Método que crea el proxy del FileUploader
        '''
        broker = self.communicator()
        sirviente = FileUploaderI()
        adaptador = broker.createObjectAdapter("FileUploader")
        proxy = adaptador.addWithUUID(sirviente)
        adaptador.activate()

    def eliminar_fichero(self):
        '''
        Para que un admin elimine un archivo
        '''
        if not self.titulo_seleccionado:
            logging.error("Primero debes seleccionar un título <seleccionar_titulo>")
            return
        self.conectar_servicio_ficheros()
        if not self.servicio_ficheros:
            return
        try:
            print("Titulo seleccionado " + self.titulo_seleccionado.info.name)
            self.servicio_catalogo.removeMedia(self.titulo_seleccionado.mediaId, self.servicio_ficheros)
        except IceFlix.WrongMediaId:
            logging.error("Ha habido un error con el id")
        except IceFlix.Unauthorized:
            logging.error("Error al renombrar el fichero")

    def run(self, argv):
        '''
        Definicion del metodo run de Ice.Application
        '''
        terminal = cmd_cliente.Terminal()
        terminal.cmdloop()

        return 0

if __name__ == "__main__":
    Cliente().main(sys.argv)