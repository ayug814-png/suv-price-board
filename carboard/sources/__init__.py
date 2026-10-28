from . import autotrader, cargurus, carpages, kijiji

SOURCES = {module.__name__.rsplit(".", 1)[1]: module for module in (autotrader, cargurus, kijiji, carpages)}
