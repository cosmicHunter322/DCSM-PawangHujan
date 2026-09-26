from flask import Flask, render_template, request, redirect, url_for, make_response, flash, send_file
import io
import security
import storage_manager

app = Flask(__name__)
app.secret_key = "flask_app_secret_key_uts"

security.init_db()

@app.route('/')
def index():
    token = request.cookies.get('jwt_token')
    user_info = security.verify_token(token) if token else None
    if not user_info:
        return redirect(url_for('login'))
    
    success, file_list, source_node = storage_manager.list_files_from_cluster()
    return render_template('dashboard.html', user=user_info, files=file_list, source_node=source_node)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        token, role, clearance = security.authenticate_user(username, password)
        if token:
            resp = make_response(redirect(url_for('index')))
            resp.set_cookie('jwt_token', token)
            return resp
        else:
            flash("Username atau Password salah!")
            
    return render_template('login.html')

@app.route('/logout')
def logout():
    resp = make_response(redirect(url_for('login')))
    resp.set_cookie('jwt_token', '', expires=0)
    return resp

@app.route('/upload', methods=['POST'])
def upload_file():
    token = request.cookies.get('jwt_token')
    user_info = security.verify_token(token)
    if not user_info:
        return redirect(url_for('login'))

    if 'file' not in request.files:
        flash("Tidak ada file yang dipilih")
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash("Nama file kosong")
        return redirect(url_for('index'))

    filename = file.filename
    file_bytes = file.read()

    success, msg, sha256_hash = storage_manager.store_file_to_cluster(filename, file_bytes)

    if success:
        security.write_audit_log(
            username=user_info['username'], 
            action="UPLOAD", 
            filename=filename, 
            sha256_hash=sha256_hash, 
            source_node="Primary Storage", 
            status="ALLOW"
        )
        flash(f"Berhasil File {filename} tersimpan dan ter-replikasi. Hash: {sha256_hash[:16]}")
    else:
        flash(f"Gagal Upload: {msg}")
    return redirect(url_for('index'))

@app.route('/download/<filename>')
def download_file(filename):
    token = request.cookies.get('jwt_token')
    user_info = security.verify_token(token)
    if not user_info:
        return redirect(url_for('login'))
    fname_lower = filename.lower()
    if "secret" in fname_lower:
        required_clearance = 3
    elif "confidential" in fname_lower:
        required_clearance = 2
    else:
        required_clearance = 1

    if not security.check_bell_lapadula_read(user_info['clearance'], required_clearance):
        security.write_audit_log(
            username=user_info['username'],
            action="READ/DOWNLOAD",
            filename=filename,
            sha256_hash="-",
            source_node="Access Denied",
            status="DENY"
        )
        flash(f"Akses Ditolak user tidak berwenang membaca file ini.")
        return redirect(url_for('index'))
    success, content, sha256_hash, source_node = storage_manager.read_file_from_cluster(filename)

    if success:
        if "Integritas Primary Rusak" in source_node:
            flash("PERINGATAN INTEGRITAS: File di Primary Storage terdeteksi dimodifikasi secara ilegal! Sistem mengunduh replika sah dari Backup Storage.")

        # Catat Audit Log ALLOW
        security.write_audit_log(
            username=user_info['username'],
            action="READ/DOWNLOAD",
            filename=filename,
            sha256_hash=sha256_hash,
            source_node=source_node,
            status="ALLOW"
        )
        return send_file(
            io.BytesIO(content),
            download_name=filename,
            as_attachment=True
        )
    else:
        flash(f"Gagal Mengambil File: {source_node}")
        return redirect(url_for('index'))

@app.route('/delete/<filename>')
def delete_file(filename):
    token = request.cookies.get('jwt_token')
    user_info = security.verify_token(token)
    if not user_info:
        return redirect(url_for('login'))

    fname_lower = filename.lower()
    if "secret" in fname_lower:
        required_clearance = 3
    elif "confidential" in fname_lower:
        required_clearance = 2
    else:
        required_clearance = 1

    if user_info['clearance'] < required_clearance:
        security.write_audit_log(user_info['username'], "DELETE", filename, "-", "Access Denied", "DENY")
        flash(f"Akses Ditolak! User '{user_info['username']}' (Clearance Level {user_info['clearance']}) tidak berwenang menghapus file ini.")
        return redirect(url_for('index'))

    success, msg = storage_manager.delete_file_from_cluster(filename)

    if success:
        security.write_audit_log(user_info['username'], "DELETE", filename, "-", "Cluster", "ALLOW")
        flash(f"Berhasil! File '{filename}' telah dihapus dari Storage Cluster.")
    else:
        flash(f"Gagal Menghapus File: {msg}")

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)