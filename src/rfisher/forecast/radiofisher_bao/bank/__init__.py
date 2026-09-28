"""Everything that determines what a Fisher bank holds.

Every Python file in this subpackage, and nothing else, is hashed into the
``working_tree_sha256`` a bank records (``banks.BANK_SOURCE_MANIFEST``), and
a bank authenticates only against the source digest it recorded. This code
is frozen: any edit here forces a re-stamp of every bank; see
``scripts/restamp_bank_provenance.py``. CI runs that script with ``--check``
and fails on any edit.
"""
