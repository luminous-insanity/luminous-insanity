import hashlib
import json
from functools import wraps

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from .models import IdempotencyRecord


def idempotent(view):
    """Atomically cache/replay a mutation response for safe client retries.

    Clients send a fresh UUID in `Idempotency-Key` for each intended action
    and reuse it only when retrying that same request after a timeout. The
    database write and cached response commit in the same transaction.
    """
    @wraps(view)
    def wrapped(self, request, *args, **kwargs):
        key = str(request.headers.get('Idempotency-Key') or '').strip()
        if not key:
            return view(self, request, *args, **kwargs)
        if len(key) > 128:
            return Response({'detail': 'Idempotency-Key cannot exceed 128 characters.'}, status=400)

        method = request.method.upper()
        path = request.path
        request_payload = json.dumps(
            {'data': request.data, 'query': request.query_params},
            sort_keys=True, separators=(',', ':'), default=str,
        )
        request_hash = hashlib.sha256(request_payload.encode('utf-8')).hexdigest()
        existing = IdempotencyRecord.objects.filter(user=request.user, key=key).first()
        if existing:
            if existing.method != method or existing.path != path or existing.request_hash != request_hash:
                return Response({'detail': 'This Idempotency-Key was already used for a different request.'}, status=status.HTTP_409_CONFLICT)
            if existing.response_status == 0:
                return Response({'detail': 'A request with this Idempotency-Key is still processing.'}, status=status.HTTP_409_CONFLICT)
            return Response(existing.response_body, status=existing.response_status)

        try:
            with transaction.atomic():
                record = IdempotencyRecord.objects.create(
                    user=request.user, key=key, method=method, path=path,
                    request_hash=request_hash,
                )
                response = view(self, request, *args, **kwargs)
                if response.status_code >= 500:
                    record.delete()
                    return response
                rendered = JSONRenderer().render(response.data) if response.data is not None else b'null'
                record.response_status = response.status_code
                record.response_body = json.loads(rendered.decode('utf-8'))
                record.save(update_fields=['response_status', 'response_body'])
                return response
        except IntegrityError:
            # A concurrent request won the unique (user, key) insert. Its
            # transaction also commits the cached response; replay that result.
            existing = IdempotencyRecord.objects.filter(user=request.user, key=key).first()
            if not existing:
                raise
            if existing.method != method or existing.path != path or existing.request_hash != request_hash:
                return Response({'detail': 'This Idempotency-Key was already used for a different request.'}, status=409)
            if existing.response_status == 0:
                return Response({'detail': 'A request with this Idempotency-Key is still processing.'}, status=409)
            return Response(existing.response_body, status=existing.response_status)

    return wrapped
