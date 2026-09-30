"""The linear parameter response of masked visibilities.

:mod:`.visibility` holds the explicit moments of masked 10-second
visibilities and a fixed, idealized science response (a quadratic statistic
and the linear response of the parameters to its bias); :mod:`.validate` is
its known-moment synthetic check, ``rfisher response visibility``. It
validates a response model; it decides nothing.
"""
