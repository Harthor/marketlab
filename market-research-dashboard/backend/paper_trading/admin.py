"""Paper Trading admin registration."""
from django.contrib import admin

from .models import PaperEquitySnapshot, PaperPortfolio, PaperPosition, PaperTrade

admin.site.register(PaperPortfolio)
admin.site.register(PaperPosition)
admin.site.register(PaperTrade)
admin.site.register(PaperEquitySnapshot)
