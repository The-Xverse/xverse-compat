"""Owned CARLA 0.9.15 client adapters for Thesis Lite Phase 4b (thesis spec 028).

Runs under the pinned CPython 3.10 client environment, out of process from the platform. Standard
library only: this package never imports ``xverse_compat`` or ``xverse_xdl``, and it imports
``carla`` only inside ``sources.LiveSource``. Nothing here starts CARLA, the bridge or zenohd.
"""
