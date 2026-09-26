import os
import sys
import grpc
import hashlib

sys.path.append(os.path.join(os.path.dirname(__file__), 'proto'))

import storage_pb2
import storage_pb2_grpc

PRIMARY_STORAGE_ADDR = "10.204.17.140:50052"
BACKUP_STORAGE_ADDR  = "10.204.17.129:50053"

def store_file_to_cluster(filename, file_bytes):
    """
    Mengirim file baru ke Primary Storage Node di Laptop 2.
    Jika Primary Offline, Upload ditolak untuk menjaga konsistensi data.
    """
    try:
        print(f"[GATEWAY] Mengirim file '{filename}' ke Primary Storage ({PRIMARY_STORAGE_ADDR})...")
        channel = grpc.insecure_channel(PRIMARY_STORAGE_ADDR)
        stub = storage_pb2_grpc.StorageServiceStub(channel)
        
        req = storage_pb2.StoreFileRequest(filename=filename, file_content=file_bytes)
        res = stub.StoreFile(req, timeout=5)
        return res.success, res.message, res.sha256_hash
    except grpc.RpcError as e:
        print(f"[GATEWAY ERROR] Primary Storage Offline ({e.code()}). Upload ditolak.")
        return False, "Gagal Upload: Primary Storage Server sedang offline. Sistem dalam mode Read-Only Failover.", ""

def read_file_from_cluster(filename):
    """
    Membaca file dengan Verifikasi Integritas SHA-256 (TC-03) dan Automatic Failover (TC-05).
    """
    primary_content = None
    primary_hash = None
    backup_content = None
    backup_hash = None

    try:
        print(f"[GATEWAY] Membaca file '{filename}' dari Primary Storage ({PRIMARY_STORAGE_ADDR})...")
        channel = grpc.insecure_channel(PRIMARY_STORAGE_ADDR)
        stub = storage_pb2_grpc.StorageServiceStub(channel)
        res_p = stub.ReadFile(storage_pb2.ReadFileRequest(filename=filename), timeout=3)
        if res_p.success:
            primary_content = res_p.file_content
            primary_hash = hashlib.sha256(primary_content).hexdigest()
    except grpc.RpcError as e:
        print(f"[GATEWAY WARNING] Primary Node Down ({e.code()}). Failover ke Backup Node")

    try:
        channel = grpc.insecure_channel(BACKUP_STORAGE_ADDR)
        stub = storage_pb2_grpc.StorageServiceStub(channel)
        res_b = stub.ReadFile(storage_pb2.ReadFileRequest(filename=filename), timeout=3)
        if res_b.success:
            backup_content = res_b.file_content
            backup_hash = hashlib.sha256(backup_content).hexdigest()
    except grpc.RpcError:
        pass

    if primary_content is not None and backup_content is not None:
        if primary_hash != backup_hash:
            print(f"\n[INTEGRITY ERROR DETECTED] Hash Berbeda")
            print(f" -> Primary Hash : {primary_hash[:16]}... (Ada perubahan ilegal di primary)")
            print(f" -> Backup Hash  : {backup_hash[:16]}... (Hash file utuh di backup)")
            print(f"[GATEWAY FAILOVER] Menggunakan replika bersih dari Backup\n")
            return True, backup_content, backup_hash, "Backup Storage (Integritas Primary Rusak)"
        else:
            return True, primary_content, primary_hash, "Primary Storage"

    if primary_content is not None:
        return True, primary_content, primary_hash, "Primary Storage"

    if backup_content is not None:
        return True, backup_content, backup_hash, "Backup Storage (Failover)"

    return False, b"", "", "Gagal: File tidak ditemukan atau kedua Storage Node Offline."
def list_files_from_cluster():
    """
    Mengambil daftar file dari Storage Cluster di Laptop 2 (Support Failover untuk View List)
    """
    try:
        channel = grpc.insecure_channel(PRIMARY_STORAGE_ADDR)
        stub = storage_pb2_grpc.StorageServiceStub(channel)
        res = stub.ListFiles(storage_pb2.ListFilesRequest(), timeout=3)
        if res.success:
            file_list = []
            for f in res.files:
                file_list.append({
                    'filename': f.filename,
                    'size_bytes': f.size_bytes,
                    'sha256_hash': f.sha256_hash
                })
            return True, file_list, "Primary Storage"
    except grpc.RpcError as e:
        print(f"[GATEWAY WARNING] Gagal ambil list dari primary: {e.code()}")

    try:
        channel = grpc.insecure_channel(BACKUP_STORAGE_ADDR)
        stub = storage_pb2_grpc.StorageServiceStub(channel)
        res = stub.ListFiles(storage_pb2.ListFilesRequest(), timeout=3)
        if res.success:
            file_list = []
            for f in res.files:
                file_list.append({
                    'filename': f.filename,
                    'size_bytes': f.size_bytes,
                    'sha256_hash': f.sha256_hash
                })
            return True, file_list, "Backup Storage (Failover)"
    except grpc.RpcError as e:
        print(f"[GATEWAY ERROR] Gagal ambil list dari Backup: {e.code()}")

    return False, [], "Cluster Offline"

def delete_file_from_cluster(filename):
    """
    Menghapus file dari Storage.
    """
    try:
        channel = grpc.insecure_channel(PRIMARY_STORAGE_ADDR)
        stub = storage_pb2_grpc.StorageServiceStub(channel)
        res = stub.DeleteFile(storage_pb2.DeleteFileRequest(filename=filename), timeout=3)
        return res.success, res.message
    except grpc.RpcError as e:
        print(f"[GATEWAY ERROR] Gagal hapus: Primary Storage Offline ({e.code()}).")
        return False, "Penghapusan ditolak: Primary Storage sedang offline"