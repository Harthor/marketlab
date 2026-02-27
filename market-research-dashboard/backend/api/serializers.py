from __future__ import annotations

from rest_framework import serializers


class RunSummarySerializer(serializers.Serializer):
    run_id = serializers.CharField()
    id = serializers.CharField()
    kind = serializers.CharField()
    run_type = serializers.CharField(required=False)
    status = serializers.CharField()
    status_ui = serializers.CharField(required=False)
    is_stale = serializers.BooleanField(required=False)
    schema_version = serializers.CharField(required=False, allow_null=True)
    name = serializers.CharField()
    dataset_hash = serializers.CharField()
    label = serializers.CharField()
    errors = serializers.ListField(child=serializers.CharField(), required=False)
    dataset = serializers.CharField(required=False)
    model_name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    top_features = serializers.IntegerField(required=False, allow_null=True)
    path = serializers.CharField()
    paths = serializers.DictField(required=False)
    error = serializers.DictField(required=False, allow_null=True)
    warnings = serializers.ListField(child=serializers.CharField(), required=False)
    created_at_utc = serializers.DateTimeField(allow_null=True)
    created_at = serializers.DateTimeField(required=False, allow_null=True)
    summary = serializers.DictField(required=False)
    table_names = serializers.ListField(child=serializers.CharField())
    plot_names = serializers.ListField(child=serializers.CharField())
    artifacts = serializers.DictField(required=False)


class RunHealthSerializer(serializers.Serializer):
    run_id = serializers.CharField()
    status = serializers.CharField()
    status_ui = serializers.CharField(required=False)
    is_stale = serializers.BooleanField(required=False)
    schema_version = serializers.CharField(required=False, allow_null=True)
    missing_artifacts = serializers.ListField(child=serializers.DictField())
    warnings = serializers.ListField(child=serializers.CharField())
    error = serializers.DictField(required=False, allow_null=True)


class DatasetSerializer(serializers.Serializer):
    name = serializers.CharField()
    run_count = serializers.IntegerField()
    source_types = serializers.ListField(child=serializers.CharField())
    last_seen = serializers.DateTimeField(allow_null=True)
    table_count = serializers.IntegerField()
    plot_count = serializers.IntegerField()


class TableQuerySerializer(serializers.Serializer):
    name = serializers.CharField(required=False)
    page = serializers.IntegerField(required=False, default=1)
    page_size = serializers.IntegerField(required=False, default=100)


class RunTableResponseSerializer(serializers.Serializer):
    run_id = serializers.CharField()
    table = serializers.CharField()
    columns = serializers.ListField(child=serializers.CharField())
    rows = serializers.ListField(child=serializers.DictField())
    row_count = serializers.IntegerField()
    page = serializers.IntegerField()
    page_size = serializers.IntegerField()
