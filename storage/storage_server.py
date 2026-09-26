import os
import sys
import argparse
import hashlib
from concurrent import futures

import grpc
import storage_pb2
import storage_pb2_grpc

class StorageServiceServicer(storage_pb2_grpc.StorageServiceServicer):
    def __init__(self, node_type, data_dir, backup_node_address=None):
        self.node_type = node_type # 'primary' atau 'backup'
        self.data_dir = data_dir
        self.backup_node_address = backup_node_address
        os.makedirs(self.data_dir, exist_ok=True)
        print(f"[{self.node_type.upper()} NODE] Server diinisialisasi. Storage path: {self.data_dir}")

    def _calculate_sha256(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def StoreFile(self, request, context):
        filename = request.filename
        file_bytes = request.file_content
        
        computed_hash = self._calculate_sha256(file_bytes)
        file_path = os.path.join(self.data_dir, filename)

        try:
            with open(file_path, 'wb') as f:
                f.write(file_bytes)
            print(f"[{self.node_type.upper()}] File '{filename}' tersimpan. SHA-256: {computed_hash}")
        except Exception as e:
            return storage_pb2.StoreFileResponse(
                success=False,
                message=f"Gagal menulis file: {str(e)}",
                sha256_hash=""
            )

        if self.node_type == 'primary' and self.backup_node_address:
            print(f"[PRIMARY] Memicu replikasi ke Backup Node ({self.backup_node_address})...")
            try:
                channel = grpc.insecure_channel(self.backup_node_address)
                stub = storage_pb2_grpc.StorageServiceStub(channel)
                repl_req = storage_pb2.ReplicateFileRequest(
                    filename=filename,
                    file_content=file_bytes,
                    primary_sha256=computed_hash
                )
                repl_res = stub.ReplicateFile(repl_req, timeout=5)
                
                if repl_res.success:
                    print(f"[PRIMARY] Replikasi BERHASIL ke Backup Node. Backup SHA-256: {repl_res.backup_sha256}")
                else:
                    print(f"[PRIMARY] Replikasi GAGAL: {repl_res.message}")
            except Exception as e:
                print(f"[PRIMARY] ERROR saat menghubungii Backup Node: {str(e)}")

        return storage_pb2.StoreFileResponse(
            success=True,
            message=f"File successfully stored on {self.node_type} node",
            sha256_hash=computed_hash
        )

    def ReplicateFile(self, request, context):
        filename = request.filename
        file_bytes = request.file_content
        primary_hash = request.primary_sha256

        computed_hash = self._calculate_sha256(file_bytes)

        if computed_hash != primary_hash:
            print(f"[BACKUP ERROR] SHA-256 MISMATCH! Primary: {primary_hash} vs Backup: {computed_hash}")
            return storage_pb2.ReplicateFileResponse(
                success=False,
                message="Data corruption detected! SHA-256 mismatch.",
                backup_sha256=computed_hash
            )

        file_path = os.path.join(self.data_dir, filename)
        try:
            with open(file_path, 'wb') as f:
                f.write(file_bytes)
            print(f"[BACKUP] Replikasi file '{filename}' BERHASIL & Terverifikasi (SHA-256 Match).")
            return storage_pb2.ReplicateFileResponse(
                success=True,
                message="Replication verified and saved successfully",
                backup_sha256=computed_hash
            )
        except Exception as e:
            return storage_pb2.ReplicateFileResponse(
                success=False,
                message=f"Gagal menulis file replikasi: {str(e)}",
                backup_sha256=""
            )

    def ListFiles(self, request, context):
        files_info = []
        try:
            for fname in os.listdir(self.data_dir):
                fpath = os.path.join(self.data_dir, fname)
                if os.path.isfile(fpath):
                    with open(fpath, 'rb') as f:
                        content = f.read()
                    fsize = os.path.getsize(fpath)
                    fhash = self._calculate_sha256(content)
                    files_info.append(storage_pb2.FileInfo(
                        filename=fname,
                        size_bytes=fsize,
                        sha256_hash=fhash
                    ))
            return storage_pb2.ListFilesResponse(success=True, files=files_info)
        except Exception as e:
            return storage_pb2.ListFilesResponse(success=False, files=[])

    def DeleteFile(self, request, context):
        filename = request.filename
        file_path = os.path.join(self.data_dir, filename)
        
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"[{self.node_type.upper()}] File '{filename}' dihapus.")
            except Exception as e:
                return storage_pb2.DeleteFileResponse(success=False, message=str(e))
        
        if self.node_type == 'primary' and self.backup_node_address:
            try:
                channel = grpc.insecure_channel(self.backup_node_address)
                stub = storage_pb2_grpc.StorageServiceStub(channel)
                stub.DeleteFile(storage_pb2.DeleteFileRequest(filename=filename), timeout=3)
            except Exception as e:
                print(f"[PRIMARY] Gagal hapus di Backup: {e}")

        return storage_pb2.DeleteFileResponse(success=True, message=f"File '{filename}' berhasil dihapus.")

    def ReadFile(self, request, context):
        filename = request.filename
        file_path = os.path.join(self.data_dir, filename)

        if not os.path.exists(file_path):
            return storage_pb2.ReadFileResponse(
                success=False,
                message=f"File '{filename}' tidak ditemukan di {self.node_type} storage.",
                file_content=b"",
                sha256_hash=""
            )

        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            computed_hash = self._calculate_sha256(content)
            print(f"[{self.node_type.upper()}] Membaca file '{filename}' (SHA-256: {computed_hash})")
            return storage_pb2.ReadFileResponse(
                success=True,
                message="File read successfully",
                file_content=content,
                sha256_hash=computed_hash
            )
        except Exception as e:
            return storage_pb2.ReadFileResponse(
                success=False,
                message=f"Gagal membaca file: {str(e)}",
                file_content=b"",
                sha256_hash=""
            )

def serve():
    parser = argparse.ArgumentParser(description="Run Storage Node Service")
    parser.add_argument('--type', choices=['primary', 'backup'], required=True, help="Node type: primary or backup")
    parser.add_argument('--port', type=int, default=50052, help="Port listener gRPC")
    parser.add_argument('--data-dir', required=True, help="Path direktori penyimpanan file")
    parser.add_argument('--backup-addr', help="IP:Port Backup Node (Khusus Primary Node)")
    args = parser.parse_args()

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    storage_servicer = StorageServiceServicer(
        node_type=args.type,
        data_dir=args.data_dir,
        backup_node_address=args.backup_addr
    )
    storage_pb2_grpc.add_StorageServiceServicer_to_server(storage_servicer, server)
    
    server.add_insecure_port(f'0.0.0.0:{args.port}')
    server.start()
    print(f"=== Storage Service [{args.type.upper()}] Berjalan di Port {args.port} ===")
    server.wait_for_termination()

if __name__ == '__main__':
    serve()