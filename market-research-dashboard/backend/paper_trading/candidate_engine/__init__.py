"""Candidate generation engine — evaluates playbooks, resolves conflicts,
applies portfolio overlay, and emits candidates to the paper trade engine."""
from .generator import CandidateGenerator

__all__ = ["CandidateGenerator"]
