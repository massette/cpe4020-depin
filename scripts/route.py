from lib.const import Address

import socket

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    udp.bind(Address.BROADCAST)

    while True:
        m = udp.recv(1024)
        print(m)
        print("-------------------------------------------------")

        for v in Address.VALIDATORS:
            udp.sendto(m, Address.VALIDATORS[v])
