import ssl
import os
from app import app

CERTS_DIR = os.path.join(os.path.dirname(__file__), 'certs')
CA_CRT     = os.path.join(CERTS_DIR, "ca.crt")
SERVER_CRT = os.path.join(CERTS_DIR, "server.crt")
SERVER_KEY = os.path.join(CERTS_DIR, "server.key")

if __name__ == '__main__':
    print("Menjalankan Koneksi mTLS")

    ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ssl_context.load_cert_chain(certfile=SERVER_CRT, keyfile=SERVER_KEY)
    ssl_context.load_verify_locations(cafile=CA_CRT)
    ssl_context.verify_mode = ssl.CERT_REQUIRED
    app.run(host='0.0.0.0', port=5000, ssl_context=ssl_context, threaded=True, debug=False)