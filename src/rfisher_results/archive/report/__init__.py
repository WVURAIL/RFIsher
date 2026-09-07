"""The dissertation report of one archive run: ledger in, LaTeX table fragments
and ``numbers.json`` documents out.

Layout under ``<results>/dissertation/``::

    tables/<name>.tex               one booktabs ``tabular`` per stub table; the chapter
                                    supplies the ``table`` environment, caption and label
    numbers/<name>.numbers.json     every number the fragment prints, keyed (archive.numbers)
    export_manifest.json            schema, producing repository and commit, run identity,
                                    artifacts with SHA-256 (the dissertation's importer reads it)

Every fragment is a pure function of the ledger (:mod:`archive.ledger`): a
:class:`Fragment` names its inputs, and its numbers carry the table, row and
column they came from, so the prose never quotes a value the ledger does not
carry. Rendering conventions live in :mod:`.core`; each stub table has one
builder module beside it.
"""
from .core import (  # noqa: F401
    Channel, Fragment, Run, booktabs, fmt, fmt_int, fmt_month, load_run, tex, write_report,
)
