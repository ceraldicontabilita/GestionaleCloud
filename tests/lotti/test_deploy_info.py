from app.lotti.deploy_info import get_deploy_info


def test_render_commit_ha_precedenza_ed_e_visibile():
    info = get_deploy_info(
        {
            "RENDER": "true",
            "RENDER_GIT_COMMIT": "bd3b2b13df7a07eea54ba6ab293ab3432f4b3c81",
            "SOURCE_VERSION": "non-deve-vincere",
            "RENDER_SERVICE_NAME": "lotti-backend",
            "RENDER_SERVICE_ID": "srv-test",
        }
    )
    assert info == {
        "deploy_commit": "bd3b2b13df7a07eea54ba6ab293ab3432f4b3c81",
        "deploy_commit_short": "bd3b2b13df7a",
        "deploy_service": "lotti-backend",
        "deploy_service_id": "srv-test",
        "runtime": "render",
    }


def test_ambiente_locale_senza_commit_e_esplicito():
    info = get_deploy_info({})
    assert info["deploy_commit"] == "unknown"
    assert info["deploy_commit_short"] == "unknown"
    assert info["runtime"] == "local"
