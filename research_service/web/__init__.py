"""HTTP layer of the research service.

``research_service.app.create_app`` builds one ``AppContext`` and mounts a
router per area; the research logic itself lives in the sibling modules
(``data``, ``engine``, ``storage``, ``reporting``).

    system    UI assets, login, settings, GPUtw and model status
    datasets  snapshots, collection tasks, FinBERT, news sources
    jobs      job validation (prepare/preflight), queue control, export
    studies   protocol-level statistics and preregistration
"""
