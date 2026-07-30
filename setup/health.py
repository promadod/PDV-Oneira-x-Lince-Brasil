from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    """Healthcheck para Docker / load balancer."""
    from django.db import connection

    db_ok = False
    try:
        connection.ensure_connection()
        db_ok = True
    except Exception:
        db_ok = False

    status = 200 if db_ok else 503
    return JsonResponse({'status': 'ok' if db_ok else 'degraded', 'database': db_ok}, status=status)
