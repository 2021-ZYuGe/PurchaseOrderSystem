# -*- coding: utf-8 -*-
"""Flask 应用：路由、静态文件、媒体、心跳与统一错误处理。

生命周期（端口、单实例、打开浏览器）在 server.py，这里不做。
"""
import time
import traceback
from pathlib import Path

from flask import (Flask, Response, abort, redirect, request, send_file,
                   send_from_directory, stream_with_context)
from werkzeug.exceptions import HTTPException

import app.config as config
from app.api import alive, runtime
from app.api.handlers import catalog, contracts, imports, setup, system
from app.api.responses import ApiError, fail
from app.infra import media
from app.infra.logging import log
from app.services import archive as archive_service

MAX_UPLOAD = 200 * 1024 * 1024


def create_app():
    app = Flask(__name__, static_folder=str(config.WEB_DIR), static_url_path='')
    app.json.ensure_ascii = False
    app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD

    def route(path, methods, view):
        app.add_url_rule(path, endpoint='%s:%s' % (view.__module__, view.__name__),
                         view_func=view, methods=methods)

    route('/api/catalog/meta', ['GET'], catalog.meta)
    route('/api/products', ['GET'], catalog.products)
    route('/api/suppliers', ['GET'], catalog.suppliers)
    route('/api/suppliers/archive', ['GET'], catalog.archive_get)
    route('/api/suppliers/archive', ['POST'], catalog.archive_save)

    route('/api/contracts/expiry', ['GET'], contracts.expiry)
    route('/api/contracts/status', ['GET'], contracts.status)
    route('/api/contracts/terms', ['POST'], contracts.save_term)
    route('/api/contracts/terms', ['DELETE'], contracts.delete_term)
    route('/api/contracts', ['POST'], contracts.generate)
    route('/api/contracts/info-sheet', ['POST'], contracts.info_sheet)

    route('/api/imports/ekuaibao/preview', ['POST'], imports.preview)
    route('/api/imports/ekuaibao', ['POST'], imports.start_ekb)
    route('/api/imports/folder', ['POST'], imports.start_folder)
    route('/api/imports/current', ['GET'], imports.current)
    route('/api/imports/history', ['GET'], imports.history)

    route('/api/setup/status', ['GET'], setup.status)
    route('/api/setup/pick-folder', ['POST'], setup.pick_folder)
    route('/api/setup/import', ['POST'], setup.import_contracts)
    route('/api/setup/restore', ['POST'], setup.restore)

    route('/api/system/info', ['GET'], system.info)
    route('/api/system/backups', ['GET'], system.backups)
    route('/api/system/backup', ['POST'], system.backup_now)
    route('/api/system/backup/download', ['GET'], system.download_backup)
    route('/api/system/export', ['GET'], system.export_package)

    # 旧页面在切换完成前继续可用
    route('/api/system/export', ['GET'], system.export_package)

    @app.get('/')
    def index():
        return send_from_directory(str(config.WEB_DIR), 'index.html')

    # 旧书签/快捷方式兼容：/contract.html → /#/contract
    for _old, _new in (('/contract.html', '/#/contract'),
                       ('/expiry.html', '/#/expiry'),
                       ('/import.html', '/#/import'),
                       ('/welcome.html', '/#/welcome')):
        def _legacy_page(target=_new):
            return redirect(target, code=302)
        app.add_url_rule(_old, endpoint='legacy:%s' % _old, view_func=_legacy_page,
                         methods=['GET'])

    @app.get('/media/<path:name>')
    @app.get('/图片/<path:name>')
    def media_file(name):
        path = media.resolve(name)
        if not path:
            abort(404)
        return send_file(path, mimetype=media.content_type(path), conditional=True)

    @app.get('/output/<path:name>')
    def output_file(name):
        base = Path(config.OUT_DIR).resolve()
        path = (base / name).resolve()
        if path.parent != base or not path.is_file():
            abort(404)
        return send_file(path, as_attachment=True, download_name=path.name)

    @app.get('/__ping')
    def ping():
        return Response('pong|%s|%s|%s' % (config.ROOT, runtime.APP_VER, runtime.APP_ID),
                        mimetype='text/plain')

    @app.get('/__stamp')
    def stamp():
        return Response(archive_service.data_stamp(), mimetype='text/plain')

    @app.get('/__arm')
    def arm():
        alive.arm()
        log('收到指令：启用关闭网页自动退出')
        return Response('armed', mimetype='text/plain')

    @app.get('/__alive')
    def alive_stream():
        client_id = (request.args.get('id') or '')[:64]
        if not client_id or not alive.register(client_id):
            return Response('', status=204)

        def stream():
            try:
                yield 'retry: 1500\n\n'
                while not runtime.STOP.is_set():
                    time.sleep(2.5)
                    yield ': on\n\n'
                    alive.touch(client_id)
            finally:
                alive.unregister(client_id)

        response = Response(stream_with_context(stream()),
                            mimetype='text/event-stream')
        response.headers['Cache-Control'] = 'no-cache'
        response.headers['Connection'] = 'keep-alive'
        response.headers['X-Accel-Buffering'] = 'no'
        return response

    @app.route('/__bye', methods=['GET', 'POST'])
    def bye():
        client_id = (request.args.get('id') or '')[:64]
        if client_id:
            alive.unregister(client_id)
        return Response('', status=204)

    @app.route('/__stop', methods=['GET', 'POST'])
    def stop():
        runtime.STOP.set()
        return Response('stopping', mimetype='text/plain')

    @app.get('/__rebuild')
    def rebuild():
        return Response('页面已改为实时查询，不再需要重建缓存。', mimetype='text/plain')

    @app.errorhandler(ApiError)
    def handle_api_error(exc):
        return fail(exc.code, exc.message, exc.status)

    @app.errorhandler(404)
    def handle_404(exc):
        if request.path.startswith('/api/'):
            return fail('not_found', '接口不存在：%s' % request.path, 404)
        return exc

    @app.errorhandler(Exception)
    def handle_error(exc):
        if isinstance(exc, HTTPException):
            if request.path.startswith('/api/'):
                return fail('http_error', exc.description or str(exc), exc.code or 500)
            return exc
        log('接口异常 %s: %r\n%s' % (request.path, exc, traceback.format_exc()))
        if request.path.startswith('/api/'):
            return fail('internal', str(exc) or '服务内部错误', 500)
        return exc

    return app
