# Incorpora la pagina del telefono (site/telefono.html e site/jpeg_prog.js) nel firmware, compressa con gzip: la scheda la serve dal suo Wi-Fi, senza Internet.
# Come script di PlatformIO (pre): scrive web_assets.h nella cartella di compilazione e la mette nel percorso degli include.
# Da riga di comando (prova sul PC):  python3 tools/embed_site.py --check <cartella-site> <uscita.h>   ricompone i file dal header e verifica che siano identici agli originali.
import gzip
import os
import re
import sys

ASSETS = [("telefono.html", "kPageHtml"), ("jpeg_prog.js", "kPageJs")]


def generate(site_dir, out_path):
    lines = ["// GENERATO da tools/embed_site.py: non modificare. Pagina del telefono compressa con gzip.", "#pragma once", "#include <cstddef>", "#include <cstdint>", ""]
    for name, sym in ASSETS:
        raw = open(os.path.join(site_dir, name), "rb").read()
        gz = gzip.compress(raw, compresslevel=9, mtime=0)            # mtime fisso: lo stesso file da' sempre gli stessi byte
        lines.append("// %s: %d byte, %d compressi" % (name, len(raw), len(gz)))
        lines.append("static const uint8_t %s[] = {" % sym)
        for i in range(0, len(gz), 16):
            lines.append("  " + ", ".join("0x%02x" % b for b in gz[i:i + 16]) + ",")
        lines.append("};")
        lines.append("static const size_t %sLen = %d;" % (sym, len(gz)))
        lines.append("static const size_t %sRawLen = %d;" % (sym, len(raw)))
        lines.append("")
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    return out_path


def check(site_dir, out_path):
    generate(site_dir, out_path)
    text = open(out_path).read()
    ok = True
    for name, sym in ASSETS:
        m = re.search(r"%s\[\] = \{(.*?)\};" % sym, text, re.S)
        data = bytes(int(x, 16) for x in re.findall(r"0x([0-9a-f]{2})", m.group(1)))
        same = gzip.decompress(data) == open(os.path.join(site_dir, name), "rb").read()
        print("%s: %d byte compressi, %s" % (name, len(data), "identico all'originale" if same else "DIVERSO"))
        ok = ok and same
    return ok


try:
    Import("env")  # noqa: F821  (PlatformIO)
    proj = env["PROJECT_DIR"]  # noqa: F821
    out = os.path.join(env.subst("$BUILD_DIR"), "web_assets.h")  # noqa: F821
    generate(os.path.join(proj, "..", "..", "site"), out)
    env.Append(CPPPATH=[os.path.dirname(out)])  # noqa: F821
    print("Pagina del telefono incorporata: " + out)
except NameError:
    if __name__ == "__main__":
        if len(sys.argv) == 4 and sys.argv[1] == "--check":
            sys.exit(0 if check(sys.argv[2], sys.argv[3]) else 1)
        print(__doc__)
        sys.exit(2)
