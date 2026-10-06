"""From the detector's handoff and a tolerance table to the screen of each band.

Reading order: :mod:`.handoff` (how the handoff files are checked),
:mod:`.interval` (the deployable set [eta_Pfa, eta_sci] and the selector
inside it), :mod:`.screening` (keep, excise or undetermined, and the
precedence) and :mod:`.archive` (the command that writes them).
"""
