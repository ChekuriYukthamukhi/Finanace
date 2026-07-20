from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('add/', views.add_transaction, name='add_transaction'),
    path('edit/<int:pk>/', views.edit_transaction, name='edit_transaction'),
    path('delete/<int:pk>/', views.delete_transaction, name='delete_transaction'),
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('budgets/', views.budgets, name='budgets'),
    path('savings-goals/', views.savings_goals, name='savings_goals'),
    path('accounts/', views.accounts_view, name='accounts'),
    path('wallets/', views.wallets_view, name='wallets'),
    path('recurring/', views.recurring_transactions, name='recurring'),
    path('reports/', views.reports, name='reports'),
    path('export/', views.export_csv, name='export_csv'),
    path('pdf-report/', views.generate_pdf_report, name='pdf_report'),
    path('currency/', views.currency_converter, name='currency_converter'),
    path('patterns/', views.spending_patterns, name='spending_patterns'),
    path('budget-suggestions/', views.budget_suggestions, name='budget_suggestions'),
]