from __future__ import annotations

from pathlib import Path

from django.core.exceptions import BadRequest
from django.http import FileResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import dashboard_service, degen_service, services
from .models import AlertEvent, AlertRule
from .serializers import (
    DatasetSerializer,
    RunHealthSerializer,
    RunSummarySerializer,
    RunTableResponseSerializer,
    TableQuerySerializer,
)
from .utils import json_sanitize


def _to_run_payload(run):
    return {
        'run_id': run.run_id,
        'id': run.run_id,
        'kind': run.kind,
        'run_type': run.kind,
        'status': run.status,
        'status_ui': run.status_ui,
        'is_stale': run.is_stale,
        'schema_version': run.schema_version,
        'name': run.name,
        'path': str(run.path),
        'dataset_hash': run.dataset_hash,
        'dataset': run.dataset_hash,
        'errors': run.errors,
        'model_name': run.model_name,
        'top_features': run.top_features,
        'label': run.label,
        'created_at_utc': run.created_at_utc,
        'created_at': run.created_at_utc,
        'error': {'message': run.error} if run.error else None,
        'paths': {
            'run': str(run.path),
            'tables': [str(artifact.path) for artifact in run.tables],
            'plots': [str(artifact.path) for artifact in run.plots],
        },
        'artifacts': {
            'tables': [{'name': artifact.name, 'path': str(artifact.path)} for artifact in run.tables],
            'plots': [{'name': artifact.name, 'path': str(artifact.path)} for artifact in run.plots],
        },
        'summary': run.summary,
        'table_names': [artifact.name for artifact in run.tables],
        'plot_names': [artifact.name for artifact in run.plots],
    }


class DatasetsView(APIView):
    def get(self, request):
        datasets = services.list_datasets()
        payload = [
            {
                'name': item.name,
                'run_count': item.run_count,
                'source_types': item.source_types,
                'last_seen': item.last_seen,
                'table_count': item.table_count,
                'plot_count': item.plot_count,
            }
            for item in datasets
        ]
        serializer = DatasetSerializer(data=payload, many=True)
        serializer.is_valid(raise_exception=True)
        return Response(json_sanitize(serializer.data))


class RunsView(APIView):
    def get(self, request):
        run_type = request.query_params.get('type') or request.query_params.get('kind')
        dataset = request.query_params.get('dataset') or request.query_params.get('dataset_hash')
        try:
            runs = services.list_runs(run_type=run_type, dataset=dataset)
        except BadRequest as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_400_BAD_REQUEST)

        payload = []
        for run in runs:
            run_payload = _to_run_payload(run)
            run_payload['warnings'] = services.health_from_run(run).get('warnings', [])
            payload.append(json_sanitize(run_payload))

        serializer = RunSummarySerializer(data=payload, many=True)
        serializer.is_valid(raise_exception=True)
        return Response(json_sanitize(serializer.data))


class RunDetailView(APIView):
    def get(self, request, run_id: str):
        try:
            run = services.get_run_summary(run_id)
        except BadRequest as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_400_BAD_REQUEST)
        except (FileNotFoundError, LookupError) as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_404_NOT_FOUND)

        payload = _to_run_payload(run)
        payload['warnings'] = services.health_from_run(run).get('warnings', [])

        serializer = RunSummarySerializer(data=json_sanitize(payload))
        serializer.is_valid(raise_exception=True)
        return Response(json_sanitize(serializer.data))


class RunTableView(APIView):
    def get(self, request, run_id: str):
        params = TableQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        name: str | None = params.validated_data.get('name')
        page: int = params.validated_data.get('page', 1)
        page_size: int = params.validated_data.get('page_size', 100)

        try:
            payload = services.get_run_table(run_id=run_id, name=name, page=page, page_size=page_size)
        except BadRequest as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_400_BAD_REQUEST)
        except (FileNotFoundError, LookupError) as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_404_NOT_FOUND)

        serializer = RunTableResponseSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(json_sanitize(serializer.data))


class RunPlotView(APIView):
    def get(self, request, run_id: str):
        name = request.query_params.get('name')
        try:
            path: Path
            content_type: str
            path, content_type = services.get_run_plot_file(run_id=run_id, name=name)
        except BadRequest as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_400_BAD_REQUEST)
        except (FileNotFoundError, LookupError) as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_404_NOT_FOUND)

        return FileResponse(
            open(path, 'rb'),
            content_type=content_type,
            headers={
                'Content-Disposition': f'inline; filename="{path.name}"',
            },
        )


class RunHealthView(APIView):
    def get(self, request, run_id: str):
        try:
            payload = services.get_run_health(run_id)
        except BadRequest as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_400_BAD_REQUEST)
        except (FileNotFoundError, LookupError) as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_404_NOT_FOUND)

        serializer = RunHealthSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(json_sanitize(serializer.data))


class DashboardView(APIView):
    """Return the complete DashboardRunData payload for the v2 frontend."""

    def get(self, request):
        try:
            data = dashboard_service.get_dashboard_data()
        except Exception as exc:
            return Response(
                json_sanitize({'detail': f'Dashboard data error: {exc}'}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(data)


class HealthView(APIView):
    """System health endpoint returning data freshness status.

    GET /api/health/
    Returns:
        {
            "status": "healthy" | "degraded" | "unhealthy",
            "sources": [
                {
                    "source": "fng",
                    "status": "fresh" | "stale" | "error" | "unknown",
                    "last_success_at": "2026-02-28T01:00:00Z",
                    "last_attempt_at": "2026-02-28T01:00:00Z",
                    "row_count": 2248,
                    "staleness_threshold_hours": 36
                }
            ],
            "recent_tasks": [
                {
                    "task_name": "ingest_fng",
                    "status": "success",
                    "started_at": "2026-02-28T01:00:00Z",
                    "duration_s": 12.5
                }
            ]
        }
    """

    def get(self, request):
        from .models import DataFreshness, TaskRun

        # Data freshness
        sources = []
        for freshness in DataFreshness.objects.all():
            freshness.check_staleness()
            sources.append({
                'source': freshness.source,
                'status': freshness.status,
                'last_success_at': (
                    freshness.last_success_at.isoformat()
                    if freshness.last_success_at else None
                ),
                'last_attempt_at': (
                    freshness.last_attempt_at.isoformat()
                    if freshness.last_attempt_at else None
                ),
                'row_count': freshness.row_count,
                'staleness_threshold_hours': freshness.staleness_threshold_hours,
                'last_error': freshness.last_error[:200] if freshness.last_error else None,
            })

        # Recent task runs (last 20)
        recent_tasks = []
        for run in TaskRun.objects.all()[:20]:
            recent_tasks.append({
                'task_name': run.task_name,
                'status': run.status,
                'started_at': run.started_at.isoformat() if run.started_at else None,
                'finished_at': run.finished_at.isoformat() if run.finished_at else None,
                'duration_s': run.duration_s,
                'error_message': run.error_message[:200] if run.error_message else None,
            })

        # Overall status
        statuses = [s['status'] for s in sources]
        if not statuses:
            overall = 'healthy'
        elif any(s == 'error' for s in statuses):
            overall = 'unhealthy'
        elif any(s == 'stale' for s in statuses):
            overall = 'degraded'
        else:
            overall = 'healthy'

        return Response({
            'status': overall,
            'sources': sources,
            'recent_tasks': recent_tasks,
        })


# ---------------------------------------------------------------------------
# Alert Engine v1 — CRUD for rules + list/dismiss events
# ---------------------------------------------------------------------------

def _rule_to_dict(rule: AlertRule) -> dict:
    return {
        'id': str(rule.id),
        'name': rule.name,
        'alertType': rule.alert_type,
        'cardKey': rule.card_key,
        'enabled': rule.enabled,
        'config': rule.config,
        'cooldownMinutes': rule.cooldown_minutes,
        'createdAt': rule.created_at.isoformat(),
        'updatedAt': rule.updated_at.isoformat(),
    }


def _event_to_dict(event: AlertEvent) -> dict:
    return {
        'id': str(event.id),
        'ruleId': str(event.rule_id),
        'severity': event.severity,
        'title': event.title,
        'message': event.message,
        'context': event.context,
        'firedAt': event.fired_at.isoformat(),
        'dismissedAt': event.dismissed_at.isoformat() if event.dismissed_at else None,
    }


class AlertRulesView(APIView):
    """GET /api/alerts/rules  — list rules.
    POST /api/alerts/rules — create a rule.
    """

    def get(self, request):
        rules = AlertRule.objects.all()
        return Response([_rule_to_dict(r) for r in rules])

    def post(self, request):
        data = request.data
        name = data.get('name', '').strip()
        if not name:
            return Response({'detail': 'name is required'}, status=status.HTTP_400_BAD_REQUEST)

        alert_type = data.get('alertType', data.get('alert_type', ''))
        valid_types = {c[0] for c in AlertRule.AlertType.choices}
        if alert_type not in valid_types:
            return Response(
                {'detail': f'alertType must be one of {sorted(valid_types)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        card_key = data.get('cardKey', data.get('card_key', ''))
        if not card_key:
            return Response({'detail': 'cardKey is required'}, status=status.HTTP_400_BAD_REQUEST)

        rule = AlertRule.objects.create(
            name=name,
            alert_type=alert_type,
            card_key=card_key,
            enabled=data.get('enabled', True),
            config=data.get('config', {}),
            cooldown_minutes=data.get('cooldownMinutes', data.get('cooldown_minutes', 1440)),
        )
        return Response(_rule_to_dict(rule), status=status.HTTP_201_CREATED)


class AlertRuleDetailView(APIView):
    """GET/PUT/DELETE /api/alerts/rules/<uuid>"""

    def get(self, request, rule_id: str):
        try:
            rule = AlertRule.objects.get(id=rule_id)
        except AlertRule.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_rule_to_dict(rule))

    def put(self, request, rule_id: str):
        try:
            rule = AlertRule.objects.get(id=rule_id)
        except AlertRule.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        data = request.data
        if 'name' in data:
            rule.name = data['name']
        if 'enabled' in data:
            rule.enabled = data['enabled']
        if 'config' in data:
            rule.config = data['config']
        if 'cooldownMinutes' in data or 'cooldown_minutes' in data:
            rule.cooldown_minutes = data.get('cooldownMinutes', data.get('cooldown_minutes', rule.cooldown_minutes))
        rule.save()
        return Response(_rule_to_dict(rule))

    def delete(self, request, rule_id: str):
        try:
            rule = AlertRule.objects.get(id=rule_id)
        except AlertRule.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        rule.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlertEventsView(APIView):
    """GET /api/alerts/events — list events (filterable by rule_id, severity, dismissed)."""

    def get(self, request):
        qs = AlertEvent.objects.select_related('rule').all()
        rule_id = request.query_params.get('ruleId') or request.query_params.get('rule_id')
        if rule_id:
            qs = qs.filter(rule_id=rule_id)
        severity = request.query_params.get('severity')
        if severity:
            qs = qs.filter(severity=severity)
        dismissed = request.query_params.get('dismissed')
        if dismissed == 'true':
            qs = qs.filter(dismissed_at__isnull=False)
        elif dismissed == 'false':
            qs = qs.filter(dismissed_at__isnull=True)
        limit = min(int(request.query_params.get('limit', 100)), 500)
        return Response([_event_to_dict(e) for e in qs[:limit]])


class AlertEventDetailView(APIView):
    """GET /api/alerts/events/<uuid> — read single event."""

    def get(self, request, event_id: str):
        try:
            event = AlertEvent.objects.select_related('rule').get(id=event_id)
        except AlertEvent.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(_event_to_dict(event))


class AlertEventDismissView(APIView):
    """POST /api/alerts/events/<uuid>/dismiss — dismiss an event."""

    def post(self, request, event_id: str):
        try:
            event = AlertEvent.objects.get(id=event_id)
        except AlertEvent.DoesNotExist:
            return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)
        event.dismiss()
        return Response(_event_to_dict(event))


# ---------------------------------------------------------------------------
# Degen Scanner — watchlist endpoint
# ---------------------------------------------------------------------------

class DegenWatchlistView(APIView):
    """GET /api/degen/watchlist — return the current degen watchlist snapshot."""

    def get(self, request):
        try:
            data = degen_service.get_watchlist()
        except Exception as exc:
            return Response(
                json_sanitize({'detail': f'Degen watchlist error: {exc}'}),
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(data)


# ---------------------------------------------------------------------------
# Trigger fetch — manual pipeline kick (protected by APITokenMiddleware)
# ---------------------------------------------------------------------------

class TriggerFetchView(APIView):
    """POST /api/trigger-fetch/ — trigger data pipeline (sync, no Celery)."""

    def post(self, request):
        import logging
        import threading

        from django.utils import timezone

        logger = logging.getLogger(__name__)

        def _run_pipeline():
            try:
                from .tasks import (
                    compute_build_dataset,
                    ingest_fng,
                    ingest_rss_crypto,
                )

                logger.info("trigger-fetch: starting pipeline")
                ingest_fng()
                ingest_rss_crypto()
                compute_build_dataset()
                logger.info("trigger-fetch: pipeline complete")
            except Exception as exc:
                logger.error("trigger-fetch: pipeline error: %s", exc)

        threading.Thread(target=_run_pipeline, daemon=True).start()

        return Response({
            'status': 'triggered',
            'ts': timezone.now().isoformat(),
        })
