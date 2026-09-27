"""Research engine implementing the v3 September 5 study protocol.

``from research_service import StanceShiftResearch`` gives the Python API
(see research_service.api); it is imported lazily so the CLI and web service
start without loading it.
"""

__all__ = ["StanceShiftResearch", "ResearchRunError"]


def __getattr__(name):
    if name in __all__:
        from . import api
        return getattr(api, name)
    raise AttributeError(name)
