#!/usr/bin/python3

import logging
import time
import Ice
Ice.loadSlice('IceFlix.ice')
import IceFlix
import cmd_cliente

class Cliente(Ice.Application):

    servicio_main = None

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

    def desconectar_servicio(self):
        '''
        Para desconectarte
        '''
        self.servicio_main = None

    def main(self):
        terminal = cmd_cliente.Terminal()
        terminal.cmdloop()

if __name__ == "__main__":
    Cliente().main()
