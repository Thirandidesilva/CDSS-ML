"""Clusters dogs into anxiety phenotypes via k-means and labels clusters by profile shape."""
from __future__ import annotations


def fit_clusters(items):
    # TODO: standardise items, k-means with k chosen by silhouette over 2..6
    raise NotImplementedError


def label_clusters_by_profile(profiles):
    # TODO: map cluster id -> Mild/Noise-specific/Generalised by shape, never by index
    raise NotImplementedError
