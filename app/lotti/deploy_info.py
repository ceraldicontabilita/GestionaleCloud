"""Metadati non sensibili per provare quale build serve la produzione."""

import os


def get_deploy_info(environ=None) -> dict:
    env = environ if environ is not None else os.environ
    commit = next(
        (
            str(env.get(key) or "").strip()
            for key in (
                "RENDER_GIT_COMMIT",
                "SOURCE_VERSION",
                "COMMIT_SHA",
                "GIT_COMMIT",
            )
            if str(env.get(key) or "").strip()
        ),
        "unknown",
    )
    return {
        "deploy_commit": commit,
        "deploy_commit_short": commit[:12] if commit != "unknown" else "unknown",
        "deploy_service": str(env.get("RENDER_SERVICE_NAME") or "").strip() or None,
        "deploy_service_id": str(env.get("RENDER_SERVICE_ID") or "").strip() or None,
        "runtime": "render" if env.get("RENDER") else "local",
    }
