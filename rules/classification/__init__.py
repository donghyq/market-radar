"""Offline product and category rules, independent of evidence assessment."""

from .classifier import MarketClassifier, default_classifier

__all__ = ["MarketClassifier", "default_classifier"]
