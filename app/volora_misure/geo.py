"""Distanze e locatore Maidenhead (senza dipendenze)."""
import math

R_EARTH_KM = 6371.0088


def haversine_km(lat1, lon1, lat2, lon2):
    """Distanza sulla sfera media (errore di qualche decimo di per cento rispetto all'ellissoide: basta per prove a decine di km)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing_deg(lat1, lon1, lat2, lon2):
    """Direzione iniziale dal punto 1 al punto 2, in gradi da 0 a 360."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0


def maidenhead(lat, lon, chars=6):
    """Locatore a 4, 6 o 8 caratteri."""
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("coordinate fuori campo")
    lon = min(lon, 179.999999) + 180.0
    lat = min(lat, 89.999999) + 90.0
    out = chr(ord("A") + int(lon // 20)) + chr(ord("A") + int(lat // 10))
    lon, lat = lon % 20, lat % 10
    out += str(int(lon // 2)) + str(int(lat // 1))
    lon, lat = lon % 2, lat % 1
    if chars >= 6:
        out += chr(ord("a") + int(lon * 12)) + chr(ord("a") + int(lat * 24))
        lon, lat = (lon * 12) % 1, (lat * 24) % 1
    if chars >= 8:
        out += str(int(lon * 10)) + str(int(lat * 10))
    return out[:chars]


def from_maidenhead(loc):
    """Centro del quadrato del locatore, come (lat, lon)."""
    s = loc.strip()
    if len(s) not in (4, 6, 8) or not (s[0:2].isalpha() and s[2:4].isdigit()):
        raise ValueError("locatore non valido: " + loc)
    lon = (ord(s[0].upper()) - 65) * 20 - 180.0
    lat = (ord(s[1].upper()) - 65) * 10 - 90.0
    lon += int(s[2]) * 2
    lat += int(s[3])
    size_lon, size_lat = 2.0, 1.0
    if len(s) >= 6:
        if not s[4:6].isalpha():
            raise ValueError("locatore non valido: " + loc)
        lon += (ord(s[4].lower()) - 97) * (2.0 / 24)     # la casella di 2 gradi ha 24 sottocaselle di 5 minuti
        lat += (ord(s[5].lower()) - 97) * (1.0 / 24)
        size_lon, size_lat = 2.0 / 24, 1.0 / 24
    if len(s) == 8:
        if not s[6:8].isdigit():
            raise ValueError("locatore non valido: " + loc)
        lon += int(s[6]) * (size_lon / 10)
        lat += int(s[7]) * (size_lat / 10)
        size_lon, size_lat = size_lon / 10, size_lat / 10
    return lat + size_lat / 2, lon + size_lon / 2
