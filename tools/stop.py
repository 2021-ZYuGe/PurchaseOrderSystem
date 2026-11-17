# -*- coding: utf-8 -*-
"""停止本机正在运行的采购下单系统。

只认 8899-8930 上、对 /__ping 返回 pong 的进程，避免误杀其它程序。
页面关不掉、服务无响应时由 stop.bat 调用。
"""
import subprocess
import sys
import time
import urllib.request

PORTS = range(8899, 8931)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def tcp_snapshot():
    """netstat 一次拿全：监听端口 -> PID"""
    try:
        raw = subprocess.run(['netstat', '-ano', '-p', 'tcp'],
                             capture_output=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    text = raw.decode('oem', 'replace')
    result = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0].upper() == 'TCP' and parts[3].upper() == 'LISTENING':
            try:
                port = int(parts[1].rsplit(':', 1)[-1])
            except ValueError:
                continue
            result.setdefault(port, set()).add(parts[4])
    return result


def is_ours(port):
    try:
        with OPENER.open('http://127.0.0.1:%d/__ping' % port, timeout=1.5) as resp:
            return resp.status == 200 and resp.read().split(b'|')[0].strip() == b'pong'
    except Exception:
        return False


def running_ports():
    snapshot = tcp_snapshot()
    return [port for port in PORTS if port in snapshot and is_ours(port)]


def stop_port(port):
    pid = next(iter(tcp_snapshot().get(port, ())), '')
    if not pid:
        return False
    try:
        subprocess.run(['taskkill', '/PID', pid, '/F'],
                       capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def stop_all(verbose=True):
    ports = running_ports()
    if not ports:
        if verbose:
            print('没有正在运行的采购下单系统。')
        return []
    for port in ports:
        if verbose:
            print('正在关闭端口 %d …' % port)
        stop_port(port)
    deadline = time.time() + 8
    while time.time() < deadline:
        left = running_ports()
        if not left:
            if verbose:
                print('已关闭（共 %d 个实例）。' % len(ports))
            return []
        time.sleep(0.3)
    left = running_ports()
    if verbose:
        print('还有 %d 个实例没关掉：%s' % (len(left), '、'.join(map(str, left))))
    return left


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(errors='replace')
    return 0 if not stop_all() else 1


if __name__ == '__main__':
    sys.exit(main())
