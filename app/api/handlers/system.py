# -*- coding: utf-8 -*-
"""系统状态、备份与数据包。"""
import io
import shutil
import time

from flask import send_file

from app.api.responses import ok
from app.services import backup as backup_service
from app.services import system as system_service


def info():
    return ok(system_service.info())


def backups():
    items = [{'name': item['name'], 'size': item['size'], 'at': item['time']}
             for item in backup_service.list_backups()]
    return ok({'items': items})


def backup_now():
    return ok(backup_service.manual())


def download_backup():
    data = backup_service.snapshot_bytes()
    name = 'purchase-backup-%s.db' % time.strftime('%Y%m%d-%H%M')
    return send_file(io.BytesIO(data), mimetype='application/octet-stream',
                     as_attachment=True, download_name=name)


def export_package():
    path = backup_service.export_package()
    response = send_file(path, mimetype='application/zip', as_attachment=True,
                         download_name='purchase-data-%s.zip' % time.strftime('%Y%m%d'))
    response.call_on_close(lambda: shutil.rmtree(path.parent, ignore_errors=True))
    return response
