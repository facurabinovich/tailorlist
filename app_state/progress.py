"""Cluster-progress persistence for pages — thin wrappers so pages never import db/."""
from typing import Iterable


def load_cluster_progress(user_key: str) -> dict:
    """{track_id: {"status", "cluster_name"}} saved since the user's last reset."""
    from db.progress import load_cluster_progress as _load
    return _load(user_key)


def save_cluster_progress(user_key: str, track_id: str,
                          status: str, cluster_name: str = None) -> None:
    """Upsert one track's clustering progress."""
    from db.progress import save_cluster_progress as _save
    _save(user_key, track_id, status, cluster_name)


def save_cluster_progress_bulk(user_key: str, track_ids: list[str],
                               status: str, cluster_name: str = None) -> None:
    """Upsert many tracks' clustering progress in one round-trip."""
    from db.progress import save_cluster_progress_bulk as _save_bulk
    _save_bulk(user_key, track_ids, status, cluster_name)


def reset_cluster_progress(user_key: str) -> bool:
    """Reset all cluster progress for a user; True on success."""
    from db.progress import reset_cluster_progress as _reset
    return _reset(user_key)


def delete_done_progress(user_key: str, track_ids: Iterable[str]) -> None:
    """Drop 'done' rows for the given tracks (re-open clusters)."""
    from db.progress import delete_done_progress as _delete
    _delete(user_key, track_ids)


def delete_progress_for_tracks(user_key: str, track_ids: Iterable[str]) -> None:
    """Drop progress rows of any status for the given tracks."""
    from db.progress import delete_progress_for_tracks as _delete
    _delete(user_key, track_ids)
