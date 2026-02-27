from __future__ import annotations

from pathlib import Path
from typing import Optional

from django.core.exceptions import BadRequest
from django.http import FileResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
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
            try:
                health = services.get_run_health(run.run_id)
                run_payload['warnings'] = health.get('warnings', [])
            except Exception:
                run_payload['warnings'] = []
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
        except Exception as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_404_NOT_FOUND)

        payload = _to_run_payload(run)
        try:
            health = services.get_run_health(run.run_id)
            payload['warnings'] = health.get('warnings', [])
        except Exception:
            payload['warnings'] = []

        serializer = RunSummarySerializer(data=json_sanitize(payload))
        serializer.is_valid(raise_exception=True)
        return Response(json_sanitize(serializer.data))


class RunTableView(APIView):
    def get(self, request, run_id: str):
        params = TableQuerySerializer(data=request.query_params.dict())
        params.is_valid(raise_exception=True)
        name: Optional[str] = params.validated_data.get('name')
        page: int = params.validated_data.get('page', 1)
        page_size: int = params.validated_data.get('page_size', 100)

        try:
            payload = services.get_run_table(run_id=run_id, name=name, page=page, page_size=page_size)
        except BadRequest as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_400_BAD_REQUEST)
        except (FileNotFoundError, LookupError) as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:
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
        except Exception as exc:
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
        except Exception as exc:
            return Response(json_sanitize({'detail': str(exc)}), status=status.HTTP_404_NOT_FOUND)

        serializer = RunHealthSerializer(data=payload)
        serializer.is_valid(raise_exception=True)
        return Response(json_sanitize(serializer.data))
