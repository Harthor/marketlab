"""Django models for task tracking, data freshness, and alert engine."""
from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class TaskRun(models.Model):
    """Records each Celery task execution for audit and debugging."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        SUCCESS = "success", "Success"
        FAILURE = "failure", "Failure"
        SKIPPED = "skipped", "Skipped"

    task_name = models.CharField(max_length=200, db_index=True)
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    started_at = models.DateTimeField(default=timezone.now, db_index=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_s = models.FloatField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    result_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["task_name", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.task_name} [{self.status}] {self.started_at:%Y-%m-%d %H:%M}"

    def mark_success(self, summary: dict | None = None) -> None:
        self.status = self.Status.SUCCESS
        self.finished_at = timezone.now()
        if self.started_at:
            self.duration_s = (self.finished_at - self.started_at).total_seconds()
        if summary:
            self.result_summary = summary
        self.save()

    def mark_failure(self, error: str) -> None:
        self.status = self.Status.FAILURE
        self.finished_at = timezone.now()
        if self.started_at:
            self.duration_s = (self.finished_at - self.started_at).total_seconds()
        self.error_message = error[:5000]
        self.save()


class DataFreshness(models.Model):
    """Tracks when each data source was last updated successfully."""

    source = models.CharField(max_length=100, unique=True, db_index=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    row_count = models.IntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("fresh", "Fresh"),
            ("stale", "Stale"),
            ("error", "Error"),
            ("unknown", "Unknown"),
        ],
        default="unknown",
    )
    staleness_threshold_hours = models.IntegerField(
        default=36,
        help_text="Hours after which data is considered stale",
    )

    class Meta:
        verbose_name_plural = "data freshness"

    def __str__(self) -> str:
        return f"{self.source}: {self.status} (last: {self.last_success_at})"

    def update_success(self, row_count: int | None = None) -> None:
        now = timezone.now()
        self.last_success_at = now
        self.last_attempt_at = now
        self.last_error = ""
        self.status = "fresh"
        if row_count is not None:
            self.row_count = row_count
        self.save()

    def update_failure(self, error: str) -> None:
        self.last_attempt_at = timezone.now()
        self.last_error = error[:5000]
        self.status = "error"
        self.save()

    def check_staleness(self) -> str:
        """Re-evaluate staleness based on threshold."""
        if self.last_success_at is None:
            self.status = "unknown"
        else:
            elapsed = (timezone.now() - self.last_success_at).total_seconds() / 3600
            self.status = "fresh" if elapsed <= self.staleness_threshold_hours else "stale"
        self.save()
        return self.status


# ---------------------------------------------------------------------------
# Alert Engine v1
# ---------------------------------------------------------------------------


class AlertRule(models.Model):
    """User-defined rule that triggers alert events when conditions are met."""

    class AlertType(models.TextChoices):
        SIGNAL_STATE_CHANGE = "signal_state_change", "Signal State Change"
        THRESHOLD_BREACH = "threshold_breach", "Threshold Breach"
        ANOMALY = "anomaly", "Anomaly Detection"
        # Degen alert types (v2)
        WHALE_ACCUMULATION = "whale_accumulation", "Whale Accumulation"
        LIQUIDITY_EVENT = "liquidity_event", "Liquidity Event"
        RUG_RISK_DETECTED = "rug_risk_detected", "Rug Risk Detected"
        EXPLOSION_SCORE_JUMP = "explosion_score_jump", "Explosion Score Jump"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    alert_type = models.CharField(max_length=40, choices=AlertType.choices, db_index=True)
    card_key = models.CharField(
        max_length=30,
        db_index=True,
        help_text="Signal card key (e.g. trends, fng, onchain)",
    )
    enabled = models.BooleanField(default=True, db_index=True)
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Type-specific config. "
            "signal_state_change: {from_states, to_states}. "
            "threshold_breach: {metric, operator, value}. "
            "anomaly: {metric, window, sigma}."
        ),
    )
    cooldown_minutes = models.PositiveIntegerField(
        default=1440,  # 24 h
        help_text="Minimum minutes between repeated firings of the same rule",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"[{self.alert_type}] {self.name} ({self.card_key})"


class AlertEvent(models.Model):
    """A single fired alert event tied to a rule."""

    class Severity(models.TextChoices):
        INFO = "info", "Info"
        WARNING = "warning", "Warning"
        CRITICAL = "critical", "Critical"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    rule = models.ForeignKey(
        AlertRule,
        on_delete=models.CASCADE,
        related_name="events",
        db_index=True,
    )
    severity = models.CharField(
        max_length=10,
        choices=Severity.choices,
        default=Severity.INFO,
    )
    title = models.CharField(max_length=300)
    message = models.TextField(blank=True, default="")
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Snapshot of the metric values at evaluation time",
    )
    fired_at = models.DateTimeField(default=timezone.now, db_index=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-fired_at"]
        indexes = [
            models.Index(fields=["rule", "-fired_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} [{self.severity}] {self.fired_at:%Y-%m-%d %H:%M}"

    @property
    def is_dismissed(self) -> bool:
        return self.dismissed_at is not None

    def dismiss(self) -> None:
        if self.dismissed_at is None:
            self.dismissed_at = timezone.now()
            self.save(update_fields=["dismissed_at"])
