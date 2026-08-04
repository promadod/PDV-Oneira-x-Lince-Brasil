"""Middleware de observabilidade: request_id + log JSON de duração."""
from __future__ import annotations

import logging
import time
import uuid

logger = logging.getLogger('app_pdv.request')


class RequestObservabilityMiddleware:
    """Adiciona X-Request-ID e registra cada request em JSON (via logger configurado)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.headers.get('X-Request-ID') or uuid.uuid4().hex[:16]
        request.request_id = request_id
        started = time.perf_counter()
        response = None
        try:
            response = self.get_response(request)
            return response
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            status_code = getattr(response, 'status_code', 500) if response is not None else 500
            if response is not None:
                response['X-Request-ID'] = request_id
            user = getattr(request, 'user', None)
            username = ''
            if user is not None and getattr(user, 'is_authenticated', False):
                username = getattr(user, 'username', '') or ''
            # Evita encher log com health/metrics
            path = request.path or ''
            if path not in ('/health/', '/metrics', '/metrics/'):
                logger.info(
                    'request',
                    extra={
                        'request_id': request_id,
                        'method': request.method,
                        'path': path,
                        'status_code': status_code,
                        'duration_ms': duration_ms,
                        'user': username,
                        'remote_addr': request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', '')),
                    },
                )
