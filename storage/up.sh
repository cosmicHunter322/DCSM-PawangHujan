#!/bin/bash
START_TIME=$(date +%s)

PVE02_IP="10.204.17.81"   
PRIMARY_ID=100          
BACKUP_ID=101          

BACKUP_LXC_ADDR="10.204.17.129:50053" 
STORAGE_DIR="/app"       

pct start $PRIMARY_ID > /dev/null 2>&1
sleep 3

pct exec $PRIMARY_ID -- bash -c "mkdir -p /var/data/primary && systemd-run --unit=primary-storage bash -c 'cd $STORAGE_DIR && source venv/bin/activate && python3 -u storage_server.py --type primary --port 50052 --data-dir /var/data/primary --backup-addr $BACKUP_LXC_ADDR'" > /dev/null 2>&1
sleep 2

ssh -o StrictHostKeyChecking=no root@$PVE02_IP "pct start $BACKUP_ID" > /dev/null 2>&1
sleep 3

ssh -o StrictHostKeyChecking=no root@$PVE02_IP "pct exec $BACKUP_ID -- bash -c 'mkdir -p /var/data/backup && systemd-run --unit=backup-storage bash -c \"cd $STORAGE_DIR && source venv/bin/activate && python3 -u storage_server.py --type backup --port 50053 --data-dir /var/data/backup\"'" > /dev/null 2>&1

echo "cluster storage berhasil di deploy"