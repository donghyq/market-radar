"""Compatibility entry point for sourced comment labels."""

from evidence_rules import PROFILE_FIELDS, age_band, default_rules, profile_evidence


def label_comment(comment):
    labels = default_rules().evaluate({**comment, "record_type": "comment"})
    return {field: labels[field] for field in ("profile_tags", "stance", "intents", "topic_tags")}
