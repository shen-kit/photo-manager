"""Asset service package.

Keep this package initializer intentionally empty.

Importing an asset submodule should not eagerly load unrelated runtime modules like
asset ingestion services, browse services, or repositories. Several worker task
modules import specific asset submodules (for example `assets.batching`), and eager
re-exports here widen the import graph enough to create circular-import risks during
process startup.
"""
