import sys

for chemin in sys.argv[1:]:
    with open(chemin, "rb") as f:
        octets = f.read()
    neuf = octets.replace(b"\r\n", b"\n")
    if neuf != octets:
        with open(chemin, "wb") as f:
            f.write(neuf)
        print(chemin, "converti en LF,", octets.count(b"\r\n"), "CRLF retires")
    else:
        print(chemin, "deja en LF")
