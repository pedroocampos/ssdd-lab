#!/usr/bin/python3

'''
Codigo que implementa la clase Cliente
y algunos sirvientes
'''

#pylint: disable=wrong-import-position
#pylint: disable=line-too-long

import logging
import time
import getpass
import hashlib
import threading
import sys
import random
import os
import Ice
import IceStorm
Ice.loadSlice('IceFlix.ice')
import IceFlix #pylint: disable=import-error
import cmd_cliente

INTENTOS_RECONEXION = 3
TAM_BLOQUE = 1024
TIEMPO_ESCUCHA = 120

class AnnouncementI(IceFlix.Announcement):
    '''
    Sirviente de Announcement
    '''
    #pylint: disable=unused-argument

    def __init__(self):
        self.main = []

    def announce(self, servicio, servicio_id, current=None):
        '''
        Metodo para manegar los announcements del servicio main
        '''
        if servicio.ice_isA("::IceFlix::Main"):
            if servicio not in self.main:
                print("\nSe ha recibido un nuevo announce de un servicio Main")
                self.main.append(IceFlix.MainPrx.uncheckedCast(servicio))

    def eliminar_servicios_inactivos(self, current=None):
        '''
        Metodo que elimina los servicios que no estan activos
        '''
        iterador = iter(self.main)
        while True:
            try:
                servicio = next(iterador)
                servicio.ice_ping()
            except StopIteration:
                break
            except Ice.Exception:
                self.main.remove(servicio)

class UserUpdateI(IceFlix.UserUpdate):
    '''
    Sirviente de UserUpdate
    '''
    #pylint: disable=unused-argument
    #pylint: disable=invalid-name
    #pylint: disable=logging-not-lazy

    def newToken(self, user, token, serviceId, current=None):
        '''
        Evento de crear un nuevo token
        '''
        logging.info(serviceId + " ha generado un nuevo token '" + token + "' para '" + user + "'")

    def revokeToken(self, token, serviceId, current=None):
        '''
        Evento de eliminar un token
        '''
        logging.info(serviceId + " ha eliminado el token '" + token + "'")

    def newUser(self, user, passwordHash, serviceId, current=None):
        '''
        Evento de añadir un nuevo usuario
        '''
        logging.info(serviceId + " ha añadido un nuevo usuario '" + user + "' con contraseña '" + passwordHash + "'")

    def removeUser(self, user, serviceId, current=None):
        '''
        Evento de eliminar un usuario
        '''
        logging.info(serviceId + "ha eliminado un usuario '" + user + "'")

class CatalogUpdateI(IceFlix.CatalogUpdate):
    '''
    Sirviente de CatalogUpdate
    '''
    #pylint: disable=unused-argument
    #pylint: disable=invalid-name
    #pylint: disable=logging-not-lazy

    def renameTile(self, mediaId, newName, serviceId, current=None):
        '''
        Evento de renombrar un titulo
        '''
        logging.info(serviceId + " ha cambiado el titulo de '" + mediaId + "' a '" + newName + "'")

    def addTags(self, mediaId, user, tags, serviceId, current=None):
        '''
        Evento cuando un usuario añade tags a un titulo
        '''
        logging.info(serviceId + " ha añadido los tags " + tags + " a '" + mediaId + "' para el usuario '" + user +"'")

    def removeTags(self, mediaId, user, tags, serviceId, current=None):
        '''
        Evento cuando un usuario elimina tags a un titulo
        '''
        logging.info(serviceId + " ha eliminado los tags " + tags + " de '" + mediaId + "' para el usuario '" + user +"'")

class FileAvailabilityAnnounceI(IceFlix.FileAvailabilityAnnounce):
    '''
    Sirviente de FileAvailabilityAnnounce
    '''
    #pylint: disable=unused-argument
    #pylint: disable=invalid-name
    #pylint: disable=logging-not-lazy

    def announceFiles(self, mediaIds, serviceId, current=None):
        '''
        Evento cuando se dan los titulos disponibles
        '''
        logging.info(serviceId + " tiene disponibles " + mediaIds)



class FileUploaderI(IceFlix.FileUploader):
    '''
    Sirviente del FileUploader
    '''

    def __init__(self, fichero):
        self.contenido_fichero = open(fichero, "rb")

    def receive(self, size, current=None): #pylint: disable=unused-argument
        '''
        Método que lee una cantidad de bytes del fichero
        '''
        return self.contenido_fichero.read(size)

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
    announcement = None

    logging.basicConfig(level=logging.NOTSET)

    def obtener_topic_manager(self, broker):
        '''
        Para conseguir el proxy al TopicManager
        '''
        intentos = 0
        topic_manager = None
        while intentos != INTENTOS_RECONEXION:
            try:
                intentos += 1
                proxy = broker.propertyToProxy("IceStorm.TopicManager")
                topic_manager = IceStorm.TopicManagerPrx.checkedCast(proxy)
            except Ice.Exception:
                logging.error("Intentando reconectar con el TopicManager...")
                topic_manager = None
                time.sleep(5)
                continue
        return topic_manager

    def obtener_topic(self, topic_manager, nombre_topic):
        '''
        Para obtener el proxy del topic que queramos
        '''
        if not topic_manager:
            return

        try:
            topic = topic_manager.retrieve(nombre_topic)
        except IceStorm.NoSuchTopic:
            topic = topic_manager.create(nombre_topic)
        finally:
            return topic

    def subscribir_announcement(self):
        '''
        Metodo para subscribirse al announcement
        '''
        broker = self.communicator()
        topic_announcement = self.obtener_topic(self.obtener_topic_manager(broker), "Announcements")
        if not topic_announcement:
            return

        self.adaptador = broker.createObjectAdapterWithEndpoints("Announcements", "tcp")
        self.adaptador.activate()

        self.announcement = AnnouncementI()
        announcement_prx = self.adaptador.addWithUUID(self.announcement)
        topic_announcement.subscribeAndGetPublisher({}, announcement_prx)
        announcement_pub = topic_announcement.getPublisher()
        announcement_pub = IceFlix.AnnouncementPrx.uncheckedCast(announcement_pub)

        self.comprobar_servicios()


    def reconectar(self):
        '''
        Metodo que lanza pings al main al que nos hemos
        conectado para ver si sigue vivo, en caso de que
        no responda intentaremos coger otro
        '''
        if self.servicio_main:
            try:
                self.servicio_main.ice_ping()
            except Ice.Exception:
                if not self.announcement.main:
                    logging.error("Se ha perdido la conexion con el servicio Main")
                    os._exit(os.EX_OK)
                else:
                    self.conectar_main()

            hilo  = threading.Timer(2.0, self.reconectar)
            hilo.daemon = True
            hilo.start()

    def comprobar_servicios(self):
        '''
        Metodo que llama a un metodo que lanza pings
        a todos los mains registrados y si alguno no responde
        lo elimina de la lista de servicios activos.
        Se ejecuta cada 5 segundos
        '''
        self.announcement.eliminar_servicios_inactivos()
        hilo = threading.Timer(5.0, self.comprobar_servicios)
        hilo.daemon = True
        hilo.start()

    def conectar_main(self):
        '''
        Para conectarte al servicio Main
        '''
        if not self.announcement:
            self.subscribir_announcement()

        intentos = 0

        while intentos != INTENTOS_RECONEXION:
            try:
                intentos += 1
                self.servicio_main = random.choice(self.announcement.main)
            except (Ice.Exception, IndexError):
                logging.error("Intentando reconectar con el servicio Main...")
                self.servicio_main = None
                time.sleep(5)
                continue
            except AttributeError:
                return

    def conectar_autenticador(self):
        '''
        Para conectarte al servicio Autenticador
        '''
        intentos = 0
        while intentos != INTENTOS_RECONEXION:
            try:
                intentos += 1
                self.servicio_autenticacion = self.servicio_main.getAuthenticator()
            except (IceFlix.TemporaryUnavailable, Ice.Exception):
                logging.error("Intentando reconectar con el servicio Autenticador...")
                self.servicio_autenticacion = None
                time.sleep(5)
                continue
            break

    def conectar_catalogo(self):
        '''
        Para conectarte al servicio Catalogo
        '''
        intentos = 0
        while intentos != INTENTOS_RECONEXION:
            try:
                intentos += 1
                self.servicio_catalogo = self.servicio_main.getCatalog()
            except (IceFlix.TemporaryUnavailable, Ice.Exception):
                logging.error("Intentando reconectar con el servicio Catalogo...")
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
                logging.error("Intentando reconectar con el servicio de Ficheros...")
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
            logging.error("No se ha podido conectar con ningún servicio Autenticador")
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
            if self.servicio_autenticacion:
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
            logging.error("No se ha podido conectar con ningún servicio Catálogo")
            return

        tipo_busqueda = input("¿Quiere buscar por nombre o tags? [nombre/tags] ")
        if tipo_busqueda == "nombre":
            media_ids = self.buscar_por_nombre()
        elif tipo_busqueda == "tags":
            if not self.token:
                logging.error("No has iniciado sesión <autenticar>")
                return
            media_ids = self.buscar_por_tags()

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
        incluir_tags = bool(input("¿Quieres que la búsqueda sea exacta? [si/no] ") == "si")
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
        self.listar_titulos()
        logging.info("Introduce el valor numérico que acompaña al título que deseas")
        indice = int(input("Selecciona un título "))
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
        try:
            datos = 0
            print("Titulo seleccionado " + self.titulo_seleccionado.info.name)
            file_handler = self.servicio_ficheros.openFile(self.titulo_seleccionado.mediaId, self.token)

            while True:
                datos += file_handler.receive(TAM_BLOQUE, self.token)
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
        token_admin = str(getpass.getpass("Token de administrador: "))
        token_admin = str(hashlib.sha256(token_admin.encode()).hexdigest())
        self.conectar_autenticador()
        if not self.servicio_autenticacion:
            logging.error("No se ha podido conectar con ningún servicio Autenticador")
            return
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
                self.conectar_user_updates()
            elif opcion_menu == 7:
                self.conectar_catalog_updates()
            elif opcion_menu == 8:
                self.conectar_file_availability()
            elif opcion_menu == 9:
                return

    def menu_administrador(self):
        '''
        Para sacar por pantalla el menú de administrador
        '''
        print("1. Añadir usuario\n2. Eliminar usuario\n3. Renombrar archivo\n4. Subir fichero\
        \n5. Eliminar fichero\n6. Suscribirse a UserUpdates\n7. Suscribirse a CatalogUpdates\
        \n8. Suscribirse a FileAvailabilityAnnounce\n9. Salir")
        opcion = input("Selecciona una opción: ")
        if not opcion.isdigit() or int(opcion) not in range(1, 10):
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
        if not self.servicio_autenticacion:
            logging.error("No se ha podido conectar con ningún servicio Autenticador")
            return
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
        self.conectar_catalogo()
        if not self.servicio_catalogo:
            logging.error("No se ha podido conectar con ningún servicio Catálogo")
            return
        try:
            if not self.titulo_seleccionado:
                media_id = input("Mediaid del archivo que quieres renombrar ")
            else:
                media_id = self.titulo_seleccionado.mediaId
            nuevo_nombre = input("Nuevo nombre del archivo ")
            self.servicio_catalogo.renameTile(media_id, nuevo_nombre, token_admin)
        except IceFlix.WrongMediaId:
            logging.error("Ha habido un error con el id")
        except IceFlix.Unauthorized:
            logging.error("Error al renombrar el fichero")

    def subir_fichero(self, token_admin):
        '''
        Método que crea el proxy del FileUploader
        y hace la llama a uploadFile
        '''
        self.conectar_servicio_ficheros()
        if not self.servicio_ficheros:
            logging.error("No se ha podido conectar con ningún servicio de Ficheros")
            return
        fichero = input("Ruta del fichero que quieres subir ")

        broker = self.communicator()
        sirviente = FileUploaderI(fichero)
        adaptador = broker.createObjectAdapterWithEndpoints("FileUploader", "tcp")
        proxy = adaptador.add(sirviente, broker.stringToIdentity("FileUploader"))
        adaptador.activate()

        file_uploader = IceFlix.FileUploaderPrx.uncheckedCast(proxy)

        try:
            self.servicio_ficheros.uploadFile(file_uploader, token_admin)
            logging.info("Fichero subido correctamente")
        except IceFlix.Unauthorized:
            logging.error("No estás autorizado para hacer esta acción")

        self.shutdownOnInterrupt()
        broker.waitForShutdown()


    def eliminar_fichero(self, token_admin):
        '''
        Para que un admin elimine un archivo
        '''

        self.conectar_servicio_ficheros()
        if not self.servicio_ficheros:
            logging.error("No se ha podido conectar con ningún servicio de Ficheros")
            return
        try:
            if not self.titulo_seleccionado:
                media_id = input("Mediaid del archivo que quieres eliminar ")
            else:
                media_id = self.titulo_seleccionado.mediaId
            self.servicio_ficheros.removeFile(media_id, token_admin)
        except IceFlix.WrongMediaId:
            logging.error("Ha habido un error con el id")
        except IceFlix.Unauthorized:
            logging.error("Error al renombrar el fichero")

    def conectar_user_updates(self):
        '''
        Para suscribirse a UserUpdates y ponerte a la escucha de los
        eventos que vayan ocurriendo durante un tiempo=TIEMPO_ESCUCHA
        '''
        logging.info("La suscripcion a UserUpdates tiene un tiempo limitado de " + str(TIEMPO_ESCUCHA/60) + " min") #pylint: disable=logging-not-lazy
        broker = self.communicator()

        topic_user_update = self.obtener_topic(self.obtener_topic_manager(broker), "UserUpdates")
        sirv_user_updates = UserUpdateI()
        user_update_prx = self.adaptador.addWithUUID(sirv_user_updates)
        topic_user_update.subscribeAndGetPublisher({}, user_update_prx)
        user_update_pub = topic_user_update.getPublisher()
        user_update_pub = IceFlix.UserUpdatePrx.uncheckedCast(user_update_pub)

        tiempo = 0
        while tiempo != TIEMPO_ESCUCHA:
            tiempo += 1
            time.sleep(1)
        topic_user_update.unsubscribe(user_update_prx)
        logging.info("Se ha acabado la suscripción a UserUpdates")

    def conectar_catalog_updates(self):
        '''
        Para suscribirse a CatalogUpdates y ponerte a la escucha de los
        eventos que vayan ocurriendo durante un tiempo=TIEMPO_ESCUCHA
        '''
        logging.info("La suscripcion a CatalogUpdates tiene un tiempo limitado de " + str(TIEMPO_ESCUCHA/60) + " min") #pylint: disable=logging-not-lazy
        broker = self.communicator()

        topic_catalog_update = self.obtener_topic(self.obtener_topic_manager(broker), "CatalogUpdates")
        sirv_catalog_updates = CatalogUpdateI()
        catalog_update_prx = self.adaptador.addWithUUID(sirv_catalog_updates)
        topic_catalog_update.subscribeAndGetPublisher({}, catalog_update_prx)
        catalog_update_pub = topic_catalog_update.getPublisher()
        catalog_update_pub = IceFlix.CatalogUpdatePrx.uncheckedCast(catalog_update_pub)

        tiempo = 0
        while tiempo != TIEMPO_ESCUCHA:
            tiempo += 1
            time.sleep(1)
        topic_catalog_update.unsubscribe(catalog_update_prx)
        logging.info("Se ha acabado la suscripción a CatalogUpdates")

    def conectar_file_availability(self):
        '''
        Para suscribirse a FileAvailability y ponerte a la escucha de los
        eventos que vayan ocurriendo durante un tiempo=TIEMPO_ESCUCHA
        '''
        logging.info("\nLa suscripcion a FileAvailability tiene un tiempo limitado de " + str(TIEMPO_ESCUCHA/60) + " min") #pylint: disable=logging-not-lazy
        broker = self.communicator()

        topic_file_availability = self.obtener_topic(self.obtener_topic_manager(broker), "FileAvailabilityAnnounce")
        sirv_file_availability = FileAvailabilityAnnounceI()
        file_availability_prx = self.adaptador.addWithUUID(sirv_file_availability)
        topic_file_availability.subscribeAndGetPublisher({}, file_availability_prx)
        file_availability_pub = topic_file_availability.getPublisher()
        file_availability_pub = IceFlix.FileAvailabilityAnnouncePrx.uncheckedCast(file_availability_pub)

        tiempo = 0
        while tiempo != TIEMPO_ESCUCHA:
            tiempo += 1
            time.sleep(1)
        topic_file_availability.unsubscribe(file_availability_prx)
        logging.info("Se ha acabado la suscripción a FileAvailability")

    def run(self, argv): #pylint: disable=unused-argument
        '''
        Definicion del metodo run de Ice.Application
        '''

        terminal = cmd_cliente.Terminal()
        terminal.cmdloop()

        return 0

if __name__ == "__main__":
    Cliente().main(sys.argv)
