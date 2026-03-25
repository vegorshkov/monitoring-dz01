#!/usr/bin/env python3

# Скрипт для сбора системных метрик из /proc
# Логи сохраняются в: /home/vgorshkov/python/jira_scripts/monitoring-DZ01
# Формат файла: YY-MM-DD-hostname-monitoring.log
#
#
#

import os
import json
import time
import re
import socket
from datetime import datetime

# Задаем хардкод-путь для сохранения логов
LOG_DIR = '/home/vgorshkov/python/jira_scripts/monitoring-DZ01'

# Запрашиваем имя хоста
HOSTNAME = socket.gethostname()


def ensure_log_dir():
    "Создаем папку для логов"
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, mode=0o755, exist_ok=True)


def get_cpu_metrics():
    "Сбор метрик CPU"
    try:
        with open('/proc/stat', 'r') as f:
            line = f.readline().strip()
            parts = line.split()
            if parts[0] == 'cpu':
                user = int(parts[1])
                nice = int(parts[2])
                system = int(parts[3])
                idle = int(parts[4])
                iowait = int(parts[5]) if len(parts) > 5 else 0

                total = user + nice + system + idle + iowait
                active = user + nice + system

                return {
                    'cpu_user': user,
                    'cpu_system': system,
                    'cpu_idle': idle,
                    'cpu_iowait': iowait,
                    'cpu_total': total,
                    'cpu_active': active
                }
    except Exception as e:
        print(f"Error reading CPU metrics: {e}")
    return {'cpu_user': 0, 'cpu_system': 0, 'cpu_idle': 0, 'cpu_iowait': 0, 'cpu_total': 0, 'cpu_active': 0}


def get_memory_metrics():
    "Сбор метрик памяти RAM"
    try:
        mem_info = {}
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip()
                    value = parts[1].strip().split()[0]
                    mem_info[key] = int(value)

        mem_total = mem_info.get('MemTotal', 1)
        mem_available = mem_info.get('MemAvailable', mem_info.get('MemFree', 0))
        mem_free = mem_info.get('MemFree', 0)
        mem_buffers = mem_info.get('Buffers', 0)
        mem_cached = mem_info.get('Cached', 0)

        return {
            'memory_total_mb': mem_total // 1024,
            'memory_available_mb': mem_available // 1024,
            'memory_free_mb': mem_free // 1024,
            'memory_used_mb': (mem_total - mem_available) // 1024,
            'memory_buffers_mb': mem_buffers // 1024,
            'memory_cached_mb': mem_cached // 1024,
            'memory_usage_percent': round((mem_total - mem_available) / mem_total * 100, 1)
        }
    except Exception as e:
        print(f"Error reading memory metrics: {e}")
    return {
        'memory_total_mb': 0,
        'memory_available_mb': 0,
        'memory_free_mb': 0,
        'memory_used_mb': 0,
        'memory_buffers_mb': 0,
        'memory_cached_mb': 0,
        'memory_usage_percent': 0
    }


def get_load_metrics():
    "Cбор Load Average"
    try:
        with open('/proc/loadavg', 'r') as f:
            parts = f.read().strip().split()
            if len(parts) >= 3:
                return {
                    'load_1min': float(parts[0]),
                    'load_5min': float(parts[1]),
                    'load_15min': float(parts[2])
                }
    except Exception as e:
        print(f"Error reading load metrics: {e}")
    return {'load_1min': 0, 'load_5min': 0, 'load_15min': 0}


def get_disk_metrics():
    "Сбор метрик дисков (NVMe SATA виртуальные диски)"
    disk_stats = {}
    try:
        with open('/proc/diskstats', 'r') as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 14:
                    device = parts[2]
                    # Определение типа диска
                    if (re.match(r'^nvme\d+n\d+$', device) or  # NVMe
                            re.match(r'^[shv]d[a-z]+$', device) or  # SATA/SCSI
                            re.match(r'^xvd[a-z]+$', device)):  # Xen

                        reads = int(parts[3])
                        writes = int(parts[7])
                        read_time_ms = int(parts[6])
                        write_time_ms = int(parts[10])

                        disk_stats[f'disk_{device}_reads'] = reads
                        disk_stats[f'disk_{device}_writes'] = writes
                        disk_stats[f'disk_{device}_read_time_ms'] = read_time_ms
                        disk_stats[f'disk_{device}_write_time_ms'] = write_time_ms

    except Exception as e:
        print(f"Error reading disk metrics: {e}")
    return disk_stats


def get_network_metrics():
    "Сбор метрик из активных сетевых интерфейсов"
    net_stats = {}
    try:
        with open('/proc/net/dev', 'r') as f:
            lines = f.readlines()[2:]  # заголовки пропускаем
            for line in lines:
                parts = line.strip().split(':')
                if len(parts) == 2:
                    interface = parts[0].strip()
                    # Собираем метрики для всех интерфейсов, кроме lo
                    if interface != 'lo':
                        values = parts[1].split()
                        if len(values) >= 16:
                            rx_bytes = int(values[0])
                            tx_bytes = int(values[8])

                            # Добавляем только если есть трафик (не нулевой)
                            if rx_bytes > 0 or tx_bytes > 0:
                                net_stats[f'net_{interface}_rx_bytes'] = rx_bytes
                                net_stats[f'net_{interface}_tx_bytes'] = tx_bytes
                                net_stats[f'net_{interface}_rx_packets'] = int(values[1])
                                net_stats[f'net_{interface}_tx_packets'] = int(values[9])
                                net_stats[f'net_{interface}_rx_errors'] = int(values[2])
                                net_stats[f'net_{interface}_tx_errors'] = int(values[10])

    except Exception as e:
        print(f"Error reading network metrics: {e}")
    return net_stats


def get_process_count():
    "Подсчет количества процессов"
    try:
        count = len([d for d in os.listdir('/proc') if d.isdigit()])
        return {'process_count': count}
    except Exception:
        return {'process_count': 0}


def get_uptime():
    "Сбор времени работы системы из /proc/uptime"
    try:
        with open('/proc/uptime', 'r') as f:
            uptime_seconds = float(f.read().strip().split()[0])
            days = int(uptime_seconds // 86400)
            hours = int((uptime_seconds % 86400) // 3600)
            return {
                'uptime_seconds': int(uptime_seconds),
                'uptime_days': days,
                'uptime_hours': hours
            }
    except Exception:
        return {'uptime_seconds': 0, 'uptime_days': 0, 'uptime_hours': 0}


def collect_metrics():
    "Сбор всех метрик в единый словарь"
    metrics = {}

    # Добавляем timestamp
    metrics['timestamp'] = int(time.time())
    metrics['hostname'] = HOSTNAME  # добавляем имя хоста в JSON

    # Собираем метрики
    metrics.update(get_cpu_metrics())
    metrics.update(get_memory_metrics())
    metrics.update(get_load_metrics())
    metrics.update(get_disk_metrics())
    metrics.update(get_network_metrics())
    metrics.update(get_process_count())
    metrics.update(get_uptime())

    return metrics


def write_log(metrics):
    "Запись метрик в лог-файл"
    ensure_log_dir()

    # Формируем имя файла: YY-MM-DD-hostname-monitoring.log
    log_filename = datetime.now().strftime(f'%y-%m-%d-{HOSTNAME}-monitoring.log')
    log_path = os.path.join(LOG_DIR, log_filename)

    # Записываем JSON строку в файл
    with open(log_path, 'a') as f:
        f.write(json.dumps(metrics, ensure_ascii=False) + '\n')

    return log_path


def main():
    "Основная функция"
    try:
        metrics = collect_metrics()
        log_path = write_log(metrics)

        # Краткий вывод для проверки
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✓ Метрики сохранены")
        print(f"  Файл: {log_path}")
        print(f"  Hostname: {HOSTNAME}")
        print(f"  CPU active: {metrics.get('cpu_active', 0)}")
        print(
            f"  Memory: {metrics.get('memory_usage_percent', 0)}% used ({metrics.get('memory_used_mb', 0)}MB / {metrics.get('memory_total_mb', 0)}MB)")
        print(f"  Load: {metrics.get('load_1min', 0)}, {metrics.get('load_5min', 0)}, {metrics.get('load_15min', 0)}")
        print(f"  Processes: {metrics.get('process_count', 0)}")

        # Показываем диски, если есть
        disk_metrics = {k: v for k, v in metrics.items() if k.startswith('disk_')}
        if disk_metrics:
            print(f"  Disks: {', '.join(set([k.split('_')[1] for k in disk_metrics.keys()]))}")

        # Показываем сетевые интерфейсы, если есть
        net_metrics = {k: v for k, v in metrics.items() if k.startswith('net_')}
        if net_metrics:
            interfaces = set([k.split('_')[1] for k in net_metrics.keys()])
            print(f"  Network interfaces: {', '.join(interfaces)}")

    except Exception as e:
        error_msg = f"{datetime.now()}: ERROR - {str(e)}"
        print(f"✗ {error_msg}")
        # Записываем ошибку в отдельный файл
        error_log = os.path.join(LOG_DIR, 'monitoring_error.log')
        with open(error_log, 'a') as f:
            f.write(error_msg + '\n')


if __name__ == '__main__':
    main()

